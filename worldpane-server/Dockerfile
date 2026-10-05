# WorldPane backend image. Build from the repository root (it needs worldpane-core too):
#   docker build -f worldpane-server/Dockerfile -t worldpane-server .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY worldpane-core/pyproject.toml worldpane-core/README.md worldpane-core/
COPY worldpane-core/src worldpane-core/src
COPY worldpane-server/pyproject.toml worldpane-server/README.md worldpane-server/
COPY worldpane-server/src worldpane-server/src
RUN pip install ./worldpane-core ./worldpane-server

COPY worldpane-server/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN useradd --system --uid 10001 --home-dir /var/lib/worldpane worldpane \
    && mkdir -p /var/lib/worldpane && chown worldpane /var/lib/worldpane \
    && chmod 0755 /usr/local/bin/docker-entrypoint.sh
USER worldpane
# Holds the generated pairing-code secret when WORLDPANE_PAIRING_CODE_SECRET is not set.
VOLUME ["/var/lib/worldpane"]

ENV WORLDPANE_ENV=prod \
    WORLDPANE_REPOSITORY=postgres \
    WORLDPANE_SEED_DEMO_WORLD=false
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "worldpane_server.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
