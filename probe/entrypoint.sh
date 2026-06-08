#!/usr/bin/env sh
# 호스팅 플랫폼 공통 entrypoint (Git 빌드 / 레지스트리 이미지 동일)
# - 등록 방식은 플랫폼(mcp-server-builder)이 결정 — 이미지는 PORT만 따름
# - Dockerfile에 PORT 고정 금지 (readiness TCP user-port 와 listen 불일치 방지)
set -eu

resolve_port() {
  if [ -n "${PORT:-}" ]; then
    printf '%s' "$PORT"
    return
  fi
  # 일부 클러스터 KServe 런타임 별칭 (있으면 사용)
  if [ -n "${KMP_PORT:-}" ]; then
    printf '%s' "$KMP_PORT"
    return
  fi
  # PORT 미주입 시: kserve-mcpserver 관례 8080 (PlayMCP 호환)
  printf '%s' "8080"
}

PORT="$(resolve_port)"
export PORT

echo "[entrypoint] ${MCP_SERVER_NAME:-csap-node-escape-probe} v${MCP_SERVER_VERSION:-?}"
echo "[entrypoint] hosting mode — listen 0.0.0.0:${PORT} (platform may inject 8080 or 8000)"
echo "[entrypoint] MCP http://0.0.0.0:${PORT}/mcp  health GET /health"
echo "[entrypoint] RUN_PROBE_ON_START=${RUN_PROBE_ON_START:-0}"

cd /opt/app
exec uvicorn server:app --host 0.0.0.0 --port "${PORT}"
