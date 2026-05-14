FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends sudo curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser && \
    echo "appuser ALL=(ALL) NOPASSWD: /usr/bin/asterisk, /usr/sbin/asterisk" >> /etc/sudoers

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/backups && chown -R appuser:appuser /data

USER appuser

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
