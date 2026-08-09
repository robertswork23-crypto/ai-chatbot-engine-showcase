# ---- Frontend: build the React SPA ----
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- Backend: FastAPI runtime serving the API + the built frontend ----
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --retries 10 --timeout 100 -r requirements.txt

COPY app/ ./app/

COPY --from=frontend-build /app/frontend/dist ./frontend_dist

EXPOSE 8000

# Shell form so Railway's injected $PORT overrides the local-dev default of 8000.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
