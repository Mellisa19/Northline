# Northline — one container, one origin.
#
# Builds the React interface, installs the API, and bakes the demonstration book
# into the image so the first request after a cold start is instant rather than
# waiting on a thirty-second seed.
#
#   docker build -t northline .
#   docker run -p 8000:8000 -e DEMO_MODE=true northline
#
# Google sign-in is configured with environment variables at run time, never baked
# in. See backend/.env.example for the full list.

# ---------------------------------------------------------------------------
# Stage 1 — build the interface
# ---------------------------------------------------------------------------
FROM node:22-slim AS web

WORKDIR /web

# Copy the manifests first so a source-only change does not reinstall everything.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — the application
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=web /web/dist ./frontend/dist

# Generate the portfolio now, so the running container does not have to.
RUN cd backend && python seed.py --force

EXPOSE 8000
WORKDIR /app/backend

# A single worker: the application keeps a small in-process cache of the scored
# book, and SQLite is a single file. That is the right shape for a demonstration.
CMD ["python", "serve.py"]
