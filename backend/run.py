"""
SHEM Backend — entry point:  python run.py
(equivalent: uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers)
"""

from __future__ import annotations

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.dev_reload,
        proxy_headers=True,                 # honour X-Forwarded-Proto / X-Forwarded-For from proxies (Railway, Cloudflare)
        forwarded_allow_ips=settings.forwarded_allow_ips,
        log_level="info",
    )
