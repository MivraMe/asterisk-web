FROM python:3.11-slim

# curl for health check; no sudo needed when running as root
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/backups

EXPOSE 8080

# Run as root so Docker volume mounts (/etc/asterisk, /var/www/html/polycom)
# are always writable regardless of host ownership. This is an internal-network
# admin tool — not exposed to the internet.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
