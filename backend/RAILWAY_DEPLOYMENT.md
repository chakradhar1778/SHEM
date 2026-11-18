# SHEM Backend — Railway & Turso Deployment Guide

## 1. Will Bill Upload Work on Railway?

- **AI Bill Scanner (`POST /api/bills/scan`)**: **YES (100%)**. It operates completely in memory, sending the image or PDF bytes to Gemini / Groq Vision API. No disk storage is required.
- **Bill Document Storage (`/api/bills/{id}/document`)**: Railway containers run on an **ephemeral disk**. 
  - All bill metadata (amount, units, dates, status) is stored safely in **Turso Cloud**.
  - Without a volume, uploaded image files are lost on container restart or redeploy.
  - To keep uploaded bill documents permanently, attach a **Railway Volume** mounted to `/app/uploads`.

> **Note on Railway Free Tier**: Railway offers a **$5 one-time trial credit** for new accounts. For continuous 24/7 uptime after the trial, the Railway Hobby tier ($5/month) is used. Turso has a generous permanent free tier (9 GB storage, 500 DBs).

---

## 2. Set Up Turso Cloud Database

1. Install the Turso CLI (or use the [Turso Web Dashboard](https://turso.tech)):
   ```bash
   # Using brew / curl / scoop:
   curl -sSfL https://get.tur.so/install.sh | bash
   ```
2. Log in and create your database:
   ```bash
   turso auth signup   # or turso auth login
   turso db create shem-db
   ```
3. Get the database URL and create an auth token:
   ```bash
   turso db show shem-db --url
   # Example output: libsql://shem-db-[your-username].turso.io

   turso db tokens create shem-db
   # Example output: eyJhbGciOi... (long JWT token)
   ```

---

## 3. Deploy on Railway

### A. Create Project & Connect Repo
1. Go to [railway.com](https://railway.com) and click **"New Project"**.
2. Select **"Deploy from GitHub repo"** and choose your `SHEM` repository.

### B. Configure Service Settings
1. In your Railway dashboard, click on the newly created service and open **Settings**:
   - **Root Directory**: Set to `backend`
   - **Build**: Railway will automatically detect `Dockerfile` or use Nixpacks.
2. Under **Networking**:
   - Click **"Generate Domain"** to get your public HTTPS URL (e.g. `https://shem-backend-production.up.railway.app`).

### C. (Optional) Attach Volume for Bill Images
If you want uploaded bill images/PDFs to persist across container restarts:
1. In Railway project canvas, right-click or click **"+ New"** -> **"Volume"**.
2. Connect it to your backend service and set Mount Path to:
   ```
   /app/uploads
   ```

---

## 4. Set Railway Environment Variables

In the **Variables** tab of your service, add the following:

| Variable | Description / Value |
|---|---|
| `HOST` | `0.0.0.0` (Already defaulted in Dockerfile) |
| `API_KEY` | Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `TURSO_DATABASE_URL` | `libsql://shem-db-[your-username].turso.io` |
| `TURSO_AUTH_TOKEN` | Your Turso JWT auth token |
| `MQTT_HOST` | `xf061010.ala.asia-southeast1.emqxsl.com` |
| `MQTT_PORT` | `8883` |
| `MQTT_USERNAME` | `shem_backend` |
| `MQTT_PASSWORD` | Your EMQX Cloud MQTT password |
| `MQTT_CA_CERT_PATH` | `/app/certs/emqxsl-ca.crt` (or `./certs/emqxsl-ca.crt`) |
| `AI_PRIMARY_PROVIDER` | `gemini` (or `groq`) |
| `GEMINI_API_KEY` | Your Google AI Studio API key |
| `GROQ_API_KEY` | Your Groq API key |
| `ALLOWED_ORIGINS` | `http://localhost:5173,https://your-frontend-domain.vercel.app` |
| `TIMEZONE` | `Asia/Kolkata` |

---

## 5. Verify Deployment

Once deployed, test your public URL:
```bash
curl https://your-railway-url.up.railway.app/api/health
```
Expected response:
```json
{
  "status": "ok",
  "version": "0.2.0",
  "db_ok": true,
  "mqtt_connected": true,
  "timestamp": "2026-..."
}
```
All tables will be auto-created in Turso upon first startup.
