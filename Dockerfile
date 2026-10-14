# ---------- Stage 1: build the React frontend ----------
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# -> produit frontend/dist (Vite)

# ---------- Stage 2: backend Python + frontend statique ----------
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 -r requirements.txt

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini .
COPY backend/tests ./tests
COPY backend/pytest.ini .

# Frontend buildé, servi par FastAPI
COPY --from=frontend-build /frontend/dist ./static

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]