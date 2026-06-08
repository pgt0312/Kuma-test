#!/usr/bin/env sh
# 호스팅용 이미지 검증 — Git/레지스트리 등록 방식 무관, PORT 8080·8000 모두 확인
set -eu

IMAGE="${IMAGE:-csap-node-escape-probe:git-build}"

cleanup() {
  [ -n "${CID:-}" ] && docker rm -f "$CID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

test_port() {
  PORT="$1"
  HOST_PORT="$2"
  CID=""
  echo ""
  echo "[verify] === PORT=${PORT} (host ${HOST_PORT}) ==="
  CID=$(docker run -d --rm -p "${HOST_PORT}:${PORT}" -e PORT="$PORT" -e RUN_PROBE_ON_START=0 "$IMAGE")
  sleep 3

  curl --noproxy "*" -fsS "http://127.0.0.1:${HOST_PORT}/health" | python3 -m json.tool
  lp=$(curl --noproxy "*" -fsS "http://127.0.0.1:${HOST_PORT}/health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('listen_port','?'))")
  [ "$lp" = "$PORT" ] || { echo "[verify] FAIL: listen_port=$lp expected $PORT"; exit 1; }
  curl --noproxy "*" -fsS "http://127.0.0.1:${HOST_PORT}/probe/safe-verify" >/dev/null
  curl --noproxy "*" -fsS "http://127.0.0.1:${HOST_PORT}/network/192-168/check" | python3 -c "import sys,json; print('network_check_enabled=', json.load(sys.stdin).get('enabled'))"

  code=$(curl --noproxy "*" -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:${HOST_PORT}/mcp")
  echo "POST /mcp -> HTTP $code"
  [ "$code" != "000" ] && [ "$code" != "404" ] || { echo "[verify] FAIL: /mcp route not reachable"; exit 1; }

  docker ps --filter "id=$CID" --format '{{.Status}}' | grep -qi up || { echo "[verify] FAIL: not running"; exit 1; }
  docker rm -f "$CID" >/dev/null
  CID=""
  echo "[verify] PORT=${PORT} OK"
}

echo "[verify] build $IMAGE"
docker build -t "$IMAGE" .

test_port 8080 "${HOST_PORT_8080:-18080}"
test_port 8000 "${HOST_PORT_8000:-18000}"

echo ""
echo "[verify] ALL OK — push 후 플랫폼이 빌드·배포하면 됨 (등록 방식은 플랫폼 결정)"
