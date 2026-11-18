# SHEM Backend — Railway / Container Dockerfile
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered streaming logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install system utilities & CA certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY . .

# Ensure storage directories exist
RUN mkdir -p /app/certs /app/uploads/bills

# Expose default port (Railway automatically overrides $PORT at runtime)
EXPOSE 8000

# Start backend through run.py (handles uvicorn with proxy headers and host binding)
CMD ["python", "run.py"]
