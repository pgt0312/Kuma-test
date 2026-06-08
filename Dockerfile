# 호스팅 플랫폼 공통 MCP 이미지 (Git 빌드 / 레지스트리 동일)
# - 등록 방식은 플랫폼 결정 — 개발자는 이 Dockerfile 하나만 유지
# - PORT는 런타임 주입만 사용 (8080·8000 클러스터 모두 entrypoint가 따름)
# - Streamable HTTP :${PORT}/mcp , GET /health
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="csap-node-escape-probe" \
      org.opencontainers.image.description="MCP + container escape surface probe (read-only)" \
      mcp.transport="streamablehttp" \
      mcp.port="auto" \
      mcp.path="/mcp"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_SERVER_NAME=csap-node-escape-probe \
    MCP_SERVER_VERSION=2.2.0-hosting \
    PROBE_REPORT_DIR=/data/reports \
    ENABLE_ACTIVE_TESTS=0 \
    ENABLE_SAFE_NET_CHECKS=0 \
    PROBE_MIN_INTERVAL_SEC=60 \
    RUN_PROBE_ON_START=0 \
    ENV_PROFILE=hosted \
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

EXPOSE 8080 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-8080}/health" || exit 1'

ENTRYPOINT ["/opt/app/probe/entrypoint.sh"]
