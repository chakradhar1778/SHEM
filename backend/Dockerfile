# SHEM Backend — container image (Render / Railway / any Docker host)
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered streaming logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    SQLITE_PATH=/app/data/shem.db

WORKDIR /app

# Install system utilities & CA certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Litestream: streams the SQLite database to object storage and restores it on
# start, so data survives restarts on an ephemeral disk (see start.sh).
ARG LITESTREAM_VERSION=v0.3.13
RUN arch="$(dpkg --print-architecture)" \
    && curl -fsSL "https://github.com/benbjohnson/litestream/releases/download/${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-${arch}.tar.gz" \
       | tar -xz -C /usr/local/bin litestream \
    && litestream version

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY . .

# Ensure storage directories exist; strip Windows line endings from the entrypoint
RUN mkdir -p /app/certs /app/uploads/bills /app/data \
    && sed -i 's/\r$//' /app/start.sh \
    && chmod +x /app/start.sh

# Expose default port (the host overrides $PORT at runtime)
EXPOSE 8000

# Restores the DB from the Litestream replica (if configured), then runs run.py
CMD ["/app/start.sh"]
