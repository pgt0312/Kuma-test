#!/usr/bin/env sh
set -eu

echo "[entrypoint] ${MCP_SERVER_NAME:-csap-node-escape-probe} — MCP :8080/mcp + escape probe"

PORT="${PORT:-8080}"
echo "[entrypoint] Streamable HTTP MCP at http://0.0.0.0:${PORT}/mcp"
echo "[entrypoint] REST: /health /probe/latest POST /probe/run"

cd /opt/app
exec uvicorn server:app --host 0.0.0.0 --port "${PORT}"
