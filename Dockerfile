FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# /data is the persistent volume mount point (set in fly.toml).
# DATABASE_PATH points there so SQLite survives deploys/restarts.
ENV DATABASE_PATH=/data/whoop.db \
    USE_SAMPLE_DATA=false \
    PORT=8080

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "app:app"]
