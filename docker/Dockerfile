FROM node:22-trixie AS runtime-builder
WORKDIR /app/wot_runtime
COPY wot_runtime/package*.json ./
RUN npm install
COPY wot_runtime/tsconfig.json ./
COPY wot_runtime/src ./src
COPY proto /app/proto
RUN npm run build

FROM node:22-trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    valkey-server \
    curl \
    xz-utils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG S6_OVERLAY_VERSION=3.2.0.2
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz

WORKDIR /app
COPY backend /app/backend
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir /app/backend
ENV PYTHONPATH=/app/backend/src

COPY --from=runtime-builder /app/wot_runtime /app/wot_runtime
COPY --from=runtime-builder /app/proto /app/proto

COPY docker/rootfs/ /
RUN chmod +x /etc/s6-overlay/s6-rc.d/*/run

ENV REDIS_URL=redis://127.0.0.1:6379 \
    REGISTRY_URL=http://localhost:8000 \
    REGISTRY_DATABASE_URL=sqlite:////data/registry/wot_registry.db \
    REGISTRY_PUBLIC_URL=http://localhost:8000 \
    CONTENT_STORE_DIR=/data/content \
    WOT_RUNTIME_STREAM=wot_runtime_events

RUN mkdir -p /data/registry /data/content
VOLUME ["/data"]

EXPOSE 8000
ENTRYPOINT ["/init"]
