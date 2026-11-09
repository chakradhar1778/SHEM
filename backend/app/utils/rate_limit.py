"""
SHEM Backend — Rate limiting (slowapi)

Behind a Cloudflare tunnel every request reaches FastAPI from 127.0.0.1, so
limiting by socket address would put all users in one bucket. When
TRUST_PROXY_HEADERS is true the client IP is taken from CF-Connecting-IP or
the first X-Forwarded-For hop. Bind the server to 127.0.0.1 (HOST) so these
headers can only come from the local tunnel.
"""

from __future__ import annotations

from slowapi import Limiter
from starlette.requests import Request

from app.config import get_settings

settings = get_settings()


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        cf = request.headers.get("cf-connecting-ip")
        if cf:
            return cf.strip()
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip, enabled=settings.rate_limit_enabled)
