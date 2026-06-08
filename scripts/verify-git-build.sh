#!/usr/bin/env sh
# Git push / UI 등록 전 로컬 검증
set -eu

IMAGE="${IMAGE:-csap-node-escape-probe:git-build}"
PORT="${PORT:-8080}"
CID=""

cleanup() {
  if [ -n "$CID" ]; then
    docker rm -f "$CID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[verify] build $IMAGE"
docker build -t "$IMAGE" .

echo "[verify] run :$PORT (platform PORT simulation)"
CID=$(docker run -d --rm -p "${PORT}:${PORT}" -e PORT="$PORT" -e RUN_PROBE_ON_START=0 "$IMAGE")
sleep 3

echo "[verify] GET /health"
curl -fsS "http://127.0.0.1:${PORT}/health" | python3 -m json.tool

echo "[verify] POST /mcp (expect HTTP 200)"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:${PORT}/mcp")
echo "POST /mcp -> HTTP $code"
[ "$code" = "200" ] || { echo "[verify] FAIL: expected 200"; exit 1; }

echo "[verify] container still running"
docker ps --filter "id=$CID" --format '{{.Status}}' | grep -qi up

echo "[verify] OK — push Git then re-register (delete old MCP first)"
