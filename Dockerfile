# KBTU App: one image — the built web app plus the Python server that serves it, the API and the bot
# (server/kbtu/app.py). Coolify builds it from the repository root.

# 1. the frontend
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
# the npm cache lives on the builder, not in a layer: a lockfile change re-downloads only what changed
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund --prefer-offline
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
# Keep apt downloads on the builder and restore Debian's cleanup hooks for the runtime image.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    set -e; \
    docker_clean=/etc/apt/apt.conf.d/docker-clean; \
    if [ -f "$docker_clean" ]; then mv "$docker_clean" /tmp/docker-clean; fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends -o APT::Keep-Downloaded-Packages=true \
        curl tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz ffmpeg age; \
    if [ -f /tmp/docker-clean ]; then mv /tmp/docker-clean "$docker_clean"; fi
WORKDIR /app/server
COPY server/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY server/kbtu ./kbtu
COPY --from=web /web/dist /app/web/dist
# the map's room list: the assistant gives a room's floor only from it (logic/assistant.py MAP_ROOMS)
COPY web/src/assets/map/uniq-rooms.json /app/web/src/assets/map/uniq-rooms.json

# the database is the only state; it must survive image updates (back it up: SPEC §9)
VOLUME /var/lib/kbtu
# DB_MUST_EXIST: refuse to start on a missing database (config.py); SQLite's temp files (big sorts) stay next to the
# data instead of the container's /tmp on the plain disk
ENV DB_PATH=/var/lib/kbtu/kbtu.db DB_MUST_EXIST=1 SQLITE_TMPDIR=/var/lib/kbtu WEB_DIST=/app/web/dist PYTHONUNBUFFERED=1
# the student forum open to every student (owner, Oct 30); the one policy covers it, no new consent.
# BOARD set on the server (Coolify) wins: BOARD=staff to try a change, BOARD=0 to close it
ENV BOARD=1
EXPOSE 8080
# --start-period: nothing listens until create() has run db.init, and a start that migrates first copies the whole
# database (VACUUM INTO) and then runs the migrations. Was: no grace, so three failed looks (~90 s) read as unhealthy
# and the deploy could be rolled back mid-start; now failures in the first 2 min don't count, the first "ok" is healthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s CMD curl -fs http://127.0.0.1:8080/healthz || exit 1
# secrets come from the environment (Coolify): BOT_TOKEN, TOKEN_KEY, ADMIN_TG_IDS, DOMAIN
# workers: WEB_CONCURRENCY if the host sets it, else one per core, the whole server (owner: use it to the max; the app is
# multi-worker safe; one was the bottleneck at 300 people opening at once). exec keeps uvicorn PID 1 for the stop signal
CMD ["sh", "-c", "export WEB_CONCURRENCY=${WEB_CONCURRENCY:-$(nproc)}; exec uvicorn kbtu.app:create --factory --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips '*' --no-access-log"]
