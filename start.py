"""
SHEM — one command to run the whole app for your phone, over HTTPS.

    python start.py

What it does, every time:
  1. Finds this PC's Wi-Fi/LAN address.
  2. Makes (once) a private certificate authority, and a certificate for the
     current address — re-issued automatically if the address changes.
  3. Builds the frontend if anything changed since the last build.
  4. Serves the app + API + live data on  https://<pc-ip>:8443  (the backend
     serves the built frontend, so it is one process).
  5. Serves a one-time phone setup page on  http://<pc-ip>:8080  that hands the
     phone the certificate to trust and walks through installing the app.

Stop with Ctrl+C.  Options: --port 8443  --setup-port 8080  --no-build
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import ipaddress
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
CERT_DIR = BACKEND / ".https"           # git-ignored; the CA private key never leaves this PC
CA_KEY, CA_CRT = CERT_DIR / "shem-ca.key", CERT_DIR / "shem-ca.crt"
SRV_KEY, SRV_CRT = CERT_DIR / "server.key", CERT_DIR / "server.crt"


# ── 1. Network ──────────────────────────────────────────────────────────────
def lan_ips() -> list[str]:
    """IPv4 addresses other devices can reach, the default-route one first."""
    ips: list[str] = []
    try:  # no packet is sent; this just asks the OS which interface routes outward
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except OSError:
        pass
    seen: list[str] = []
    for ip in ips:
        if ip not in seen and not ip.startswith(("127.", "169.254.")):
            seen.append(ip)
    return seen


# ── 2. Certificates ─────────────────────────────────────────────────────────
def ensure_certs(ips: list[str]) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    CERT_DIR.mkdir(exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)

    def write_key(path: Path, key) -> None:
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))

    if CA_KEY.is_file() and CA_CRT.is_file():
        ca_key = serialization.load_pem_private_key(CA_KEY.read_bytes(), None)
        ca_crt = x509.load_pem_x509_certificate(CA_CRT.read_bytes())
    else:
        print("• Creating SHEM's private certificate authority (one time)…")
        ca_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SHEM Local CA")])
        ca_crt = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                         content_commitment=False, key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        write_key(CA_KEY, ca_key)
        CA_CRT.write_bytes(ca_crt.public_bytes(serialization.Encoding.PEM))
        SRV_CRT.unlink(missing_ok=True)  # old server cert was signed by a different CA

    wanted_ips = {"127.0.0.1", *ips}
    host = socket.gethostname().lower()
    # Hostnames can hold anything (even emoji); only a valid DNS name can go in a certificate.
    wanted_dns = {"localhost"} | ({host} if re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?", host) else set())
    if SRV_CRT.is_file() and SRV_KEY.is_file():
        crt = x509.load_pem_x509_certificate(SRV_CRT.read_bytes())
        san = crt.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        have_ips = {str(i) for i in san.get_values_for_type(x509.IPAddress)}
        fresh = crt.not_valid_after_utc - now > dt.timedelta(days=30)
        if wanted_ips <= have_ips and fresh:
            return

    print("• Issuing an HTTPS certificate for", ", ".join(sorted(wanted_ips - {"127.0.0.1"})) or "localhost")
    key = ec.generate_private_key(ec.SECP256R1())
    alt = [x509.DNSName(d) for d in sorted(wanted_dns)] + [x509.IPAddress(ipaddress.ip_address(i)) for i in sorted(wanted_ips)]
    crt = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SHEM")]))
        .issuer_name(ca_crt.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
        # ≤ 397 days: the longest lifetime Apple and Chrome accept for a server certificate
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=397))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    write_key(SRV_KEY, key)
    SRV_CRT.write_bytes(crt.public_bytes(serialization.Encoding.PEM))


# ── 3. Frontend build ───────────────────────────────────────────────────────
def build_frontend_if_needed() -> None:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("✗ npm not found — install Node.js from https://nodejs.org and run again.")
    built = FRONTEND / "dist" / "index.html"
    sources = [FRONTEND / p for p in ("src", "public", "index.html", "vite.config.ts", "package.json", ".env", ".env.local")]
    newest = 0.0
    for src in sources:
        if src.is_file():
            newest = max(newest, src.stat().st_mtime)
        elif src.is_dir():
            newest = max([newest, *(f.stat().st_mtime for f in src.rglob("*") if f.is_file())])
    if built.is_file() and built.stat().st_mtime >= newest:
        print("• Frontend build is up to date")
        return
    if not (FRONTEND / "node_modules").is_dir():
        print("• Installing frontend packages (first run)…")
        subprocess.run([npm, "install"], cwd=FRONTEND, check=True)
    print("• Building the frontend…")
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)


# ── 5. Phone setup page (plain HTTP — the phone does not trust us yet) ──────
def setup_page(app_url: str, user_agent: str) -> bytes:
    ua = user_agent.lower()
    ios = any(k in ua for k in ("iphone", "ipad", "macintosh")) and "android" not in ua
    a = html.escape(app_url)
    android_steps = """
      <li>Tap <b>Download certificate</b> above.</li>
      <li>Open <b>Settings</b> and search for <b>“CA certificate”</b>
          (usually Security → More security settings → Encryption &amp; credentials → Install a certificate → CA certificate).</li>
      <li>Tap <b>Install anyway</b>, then pick <b>shem-ca.crt</b> from Downloads.</li>
      <li>Come back here and tap <b>Open SHEM</b>. In Chrome: ⋮ menu → <b>Install app</b>.</li>"""
    ios_steps = """
      <li>Tap <b>Download certificate</b> above (in <b>Safari</b>) → <b>Allow</b>.</li>
      <li>Open <b>Settings</b> → <b>Profile Downloaded</b> → <b>Install</b>.</li>
      <li>Then <b>Settings → General → About → Certificate Trust Settings</b> → turn on <b>SHEM Local CA</b>.</li>
      <li>Come back here and tap <b>Open SHEM</b>, then Share → <b>Add to Home Screen</b>.</li>"""
    first, second = (("iPhone / iPad", ios_steps), ("Android", android_steps)) if ios else (("Android", android_steps), ("iPhone / iPad", ios_steps))
    return _render(a, first, second)


def _render(a: str, first: tuple[str, str], second: tuple[str, str]) -> bytes:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Set up SHEM</title>
<style>
 body{{margin:0;font:16px/1.5 system-ui,sans-serif;background:#EEF4FA;color:#122448}}
 main{{max-width:460px;margin:0 auto;padding:24px 16px 48px}}
 h1{{font-size:22px;margin:0 0 4px}} p{{margin:0 0 16px;color:#475569}}
 .btn{{display:block;text-align:center;padding:14px;border-radius:14px;font-weight:600;text-decoration:none;margin:10px 0}}
 .primary{{background:#122448;color:#fff}} .soft{{background:#fff;color:#122448;box-shadow:0 2px 10px rgba(18,36,72,.1)}}
 section{{background:#fff;border-radius:18px;padding:4px 16px 8px;margin-top:16px}}
 h2{{font-size:16px}} li{{margin:6px 0}} summary{{cursor:pointer;font-weight:600;padding:12px 0}}
</style></head><body><main>
 <h1>⚡ Set up SHEM on this phone</h1>
 <p>One time only. Trust SHEM's certificate so the app runs securely (needed for voice and installing it), then add it to your home screen.</p>
 <a class="btn soft" href="/shem-ca.crt">1 · Download certificate</a>
 <a class="btn primary" href="{a}">2 · Open SHEM</a>
 <section><h2>{first[0]}</h2><ol>{first[1]}</ol></section>
 <section><details><summary>{second[0]}</summary><ol>{second[1]}</ol></details></section>
 <p style="margin-top:16px">Already set up? Just open the SHEM icon on your home screen.</p>
</main></body></html>""".encode()


def start_setup_server(port: int, app_url: str) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?")[0] == "/shem-ca.crt":
                body, ctype = CA_CRT.read_bytes(), "application/x-x509-ca-cert"
                extra = {"Content-Disposition": 'attachment; filename="shem-ca.crt"'}
            else:
                body, ctype, extra = setup_page(app_url, self.headers.get("User-Agent", "")), "text/html; charset=utf-8", {}
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in extra.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Run SHEM over HTTPS for phones on this Wi-Fi.")
    ap.add_argument("--port", type=int, default=8443, help="HTTPS port for the app (default 8443)")
    ap.add_argument("--setup-port", type=int, default=8080, help="HTTP port for the phone setup page (default 8080)")
    ap.add_argument("--no-build", action="store_true", help="skip the frontend build check")
    args = ap.parse_args()

    ips = lan_ips()
    if not ips:
        print("! No Wi-Fi/LAN address found — is this PC connected? Continuing with localhost only.")
    ensure_certs(ips)
    if not args.no_build:
        build_frontend_if_needed()

    host = ips[0] if ips else "localhost"
    app_url = f"https://{host}:{args.port}/"
    start_setup_server(args.setup_port, app_url)

    line = "─" * 58
    print(f"\n{line}\n  SHEM is starting\n")
    print(f"  Phone, first time : http://{host}:{args.setup_port}   (set-up page)")
    print(f"  Phone, after that : {app_url}  (or the home-screen icon)")
    print(f"  This PC           : https://localhost:{args.port}/")
    if len(ips) > 1:
        print("  Other addresses   : " + ", ".join(ips[1:]))
    print(f"\n  Phone and PC must be on the same Wi-Fi. Ctrl+C to stop.\n{line}\n")

    # Run the backend from its own folder so .env, the database and uploads resolve as usual.
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    os.environ["FRONTEND_DIST_PATH"] = str(FRONTEND / "dist")
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=args.port,
        ssl_certfile=str(SRV_CRT),
        ssl_keyfile=str(SRV_KEY),
        log_level="info",
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
