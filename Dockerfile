FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 (psycopg2 빌드용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
