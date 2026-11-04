# Stage 1: build the frontend
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the API, serving the built frontend
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY backend/app ./app
COPY --from=web /web/dist ./static
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data
USER app
ENV APP_ENV=production \
    DATABASE_URL=sqlite:////app/data/gold_ledger.db \
    AUTO_SEED=true
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]