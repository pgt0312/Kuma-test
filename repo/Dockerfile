# PlayMCP MCP (8080/mcp) + escape probe — push to registry before UI registration
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    MCP_SERVER_NAME=csap-node-escape-probe \
    MCP_SERVER_VERSION=2.0.0-mcp \
    PROBE_REPORT_DIR=/data/reports \
    ENABLE_ACTIVE_TESTS=0 \
    RUN_PROBE_ON_START=1 \
    ENV_PROFILE=test

WORKDIR /opt/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        iproute2 \
        util-linux \
        procps \
        mount \
        libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY probe/ ./probe/
RUN chmod +x ./probe/entrypoint.sh ./probe/active_checks.sh \
    && mkdir -p /data/reports \
    && useradd --create-home --uid 10001 probeuser \
    && chown -R probeuser:probeuser /data /opt/app

USER probeuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/opt/app/probe/entrypoint.sh"]
