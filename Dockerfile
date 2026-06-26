FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV ENV=production
ENV DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/uploads/videos /data/uploads/images /data/db

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD /bin/sh -c 'curl -f http://127.0.0.1:${PORT:-8080}/api/health || exit 1'

CMD ["python", "run.py"]
