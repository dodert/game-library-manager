FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data \
    PORT=8000 \
    PUID=99 \
    PGID=100 \
    UMASK=022 \
    TZ=Etc/UTC

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ARG VERSION=dev
LABEL org.opencontainers.image.title="Game Library Manager" \
      org.opencontainers.image.description="Self-hosted video game collection manager with cover art" \
      org.opencontainers.image.source="https://github.com/dodert/game-library-manager" \
      org.opencontainers.image.version="${VERSION}"

VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*'"]
