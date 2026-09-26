# --- Stage 1: build the exported Next.js frontend -----------------------------
FROM node:22-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin in production: the API is served by FastAPI from the same host.
ENV NEXT_PUBLIC_API_URL=
RUN npm run build

# --- Stage 2: Python runtime with FastAPI, git, and the demo repo -------------
FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY scripts/create-demo-repo.sh ./scripts/
COPY --from=frontend-build /build/out ./frontend/out

# Bake in the demo repo so a fresh deployment is demo-ready immediately.
RUN bash scripts/create-demo-repo.sh /app/target-repo

ENV TARGET_REPO_PATH=/app/target-repo \
    FRONTEND_EXPORT=/app/frontend/out \
    PORT=7860 \
    AGENT_TIMEOUT_SECONDS=240 \
    GEMINI_TIMEOUT_SECONDS=60

EXPOSE 7860
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
