FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Build-time metadata, baked into the image so the running app can show
# which commit/timestamp is live. CI passes these via --build-arg.
ARG COMMIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV COMMIT_SHA=${COMMIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

# /data is the persistent volume mount point (set in fly.toml).
# DATABASE_PATH points there so SQLite survives deploys/restarts.
ENV DATABASE_PATH=/data/whoop.db \
    USE_SAMPLE_DATA=false \
    PORT=8080

EXPOSE 8080

# --threads + longer timeout so SSE streaming sync can stay open up to 5
# minutes per chunk without gunicorn killing the worker.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", \
     "--timeout", "300", "--worker-class", "gthread", "app:app"]
