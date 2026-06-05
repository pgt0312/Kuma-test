#!/usr/bin/env sh
set -eu

PORT="${PORT:-8000}"
echo "[entrypoint] ${MCP_SERVER_NAME:-csap-node-escape-probe} — MCP :${PORT}/mcp + escape probe"
echo "[entrypoint] Streamable HTTP MCP at http://0.0.0.0:${PORT}/mcp"
echo "[entrypoint] REST: /health /probe/latest POST /probe/run POST /probe/safe-verify"
echo "[entrypoint] PlayMCP: register via Git build — see PLAYMCP_GIT_BUILD.md"

cd /opt/app
exec uvicorn server:app --host 0.0.0.0 --port "${PORT}"
