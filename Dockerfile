# PlayMCP「Git 소스 빌드」용 MCP 서버 이미지
# - 레포 루트에 Dockerfile 필수 (PlayMCP 기본: dockerfile=Dockerfile)
# - KServe kserve-mcpserver 런타임: PORT=8000, TCP readiness (PlayMCP UI 포트도 8000)
# - Streamable HTTP :${PORT}/mcp, GET /health
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="csap-node-escape-probe" \
      org.opencontainers.image.description="PlayMCP MCP + container escape surface probe (read-only)" \
      playmcp.transport="streamablehttp" \
      playmcp.port="8000" \
      playmcp.path="/mcp"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    MCP_SERVER_NAME=csap-node-escape-probe \
    MCP_SERVER_VERSION=2.1.1-playmcp-git \
    PROBE_REPORT_DIR=/data/reports \
    ENABLE_ACTIVE_TESTS=0 \
    ENABLE_SAFE_NET_CHECKS=0 \
    PROBE_MIN_INTERVAL_SEC=60 \
    RUN_PROBE_ON_START=0 \
    ENV_PROFILE=playmcp \
    LOG_LEVEL=info

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

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/opt/app/probe/entrypoint.sh"]
