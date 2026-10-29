# KBTU App: one image — the built web app plus the Python server that serves it, the API and the bot
# (server/kbtu/app.py). Coolify builds it from the repository root.

# 1. the frontend
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# npm run build: vite, then the check that no bundle uses regex lookbehind (Safari < 16.4 fails at start on it)
RUN npm run build

# 2. the server
FROM python:3.14-slim
# curl isn't for the app but for Coolify's healthcheck: the slim image has no curl or wget, and without one
# the container reads as unhealthy and the deploy rolls back. Tesseract reads Kaspi receipts (server/kbtu/receipt.py):
# Debian's rus and kaz models are the "fast" ones the reading was tested with (Oct 11). ffmpeg compresses event videos
# (server/kbtu/video.py; Debian's build has x264 and zimg for the HDR tone mapping). age encrypts the off-site backups
# (server/kbtu/offsite.py)
RUN apt-get update && apt-get install -y --no-install-recommends curl tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz ffmpeg age \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/server
COPY server/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server/kbtu ./kbtu
COPY --from=web /web/dist /app/web/dist

# the database is the only state; it must survive image updates (back it up: SPEC §9)
VOLUME /var/lib/kbtu
# DB_MUST_EXIST: refuse to start on a missing database (config.py); SQLite's temp files (big sorts) stay next to the
# data instead of the container's /tmp on the plain disk
ENV DB_PATH=/var/lib/kbtu/kbtu.db DB_MUST_EXIST=1 SQLITE_TMPDIR=/var/lib/kbtu WEB_DIST=/app/web/dist PYTHONUNBUFFERED=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://127.0.0.1:8080/healthz || exit 1
# secrets come from the environment (Coolify): BOT_TOKEN, TOKEN_KEY, ADMIN_TG_IDS, DOMAIN
CMD ["uvicorn", "kbtu.app:create", "--factory", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
