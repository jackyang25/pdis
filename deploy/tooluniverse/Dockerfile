# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

ARG TOOLUNIVERSE_VERSION=1.4.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install "tooluniverse==${TOOLUNIVERSE_VERSION}"

FROM python:3.11-slim

COPY --from=builder /install/ /usr/local/

COPY healthcheck.py /opt/pdis/healthcheck.py

ENV PORT=8080 \
    TOOLUNIVERSE_CACHE_PERSIST=false \
    TOOLUNIVERSE_LOG_LEVEL=INFO

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD ["python", "/opt/pdis/healthcheck.py"]

CMD ["sh", "-c", "exec tooluniverse-http-api --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
