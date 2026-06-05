#!/usr/bin/env sh
# PlayMCP Git 빌드 후 모니터링 오류 해결:
#   「클러스터에 해당 InferenceService가 없습니다. Istio 메트릭 라벨을 확인할 수 없습니다.」
#
# PlayMCP는 Git 빌드 시 이미지만 만들고 Deployment만 둘 수 있음 → IS를 별도 생성.
#
# Usage:
#   MCP_NAME=csap-node-escape-probe NS=<user-namespace> \
#   IMAGE=<registry>/csap-node-escape-probe:tag \
#   ./scripts/apply-inferenceservice-for-playmcp.sh
#
# IMAGE 생략 시 동일 NS의 Deployment/Pod에서 이미지 자동 추출 시도.
# --remove-playmcp-deployment: IS 생성 전 PlayMCP가 만든 동일 이름 Deployment 삭제(중복 Pod 방지).
set -eu

MCP_NAME="${MCP_NAME:-}"
NS="${NS:-${NAMESPACE:-}}"
IMAGE="${IMAGE:-${CONTAINER_IMAGE:-}}"
REMOVE_DEPLOY="${REMOVE_DEPLOY:-0}"
KUBECTL="${KUBECTL:-kubectl}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="${REPO_ROOT}/k8s/inference-service-playmcp.yaml"

usage() {
  cat <<'EOF' >&2
Usage:
  MCP_NAME=<playmcp-mcp-server-name> NS=<namespace> [IMAGE=<full-image-ref>] \
    ./scripts/apply-inferenceservice-for-playmcp.sh

Options (env):
  REMOVE_DEPLOY=1     PlayMCP Deployment(이름에 MCP_NAME 포함) 삭제 후 IS 적용
  SERVICE_ACCOUNT_NAME=default  predictor serviceAccount (빈 문자열이면 필드 생략)

After apply:
  1) PlayMCP 상세 → endpoint_name == MCP_NAME 확인
  2) Playground에서 echo 20회 → 모니터링 탭 새로고침
EOF
  exit 1
}

log() { printf '[apply-is] %s\n' "$1"; }
warn() { printf '[apply-is] WARN: %s\n' "$1" >&2; }
die() { printf '[apply-is] ERROR: %s\n' "$1" >&2; exit 1; }

[ -n "$MCP_NAME" ] && [ -n "$NS" ] || usage
[ -f "$TEMPLATE" ] || die "missing template: $TEMPLATE"

# --- KServe API version ---
KSERVE_API_VERSION=""
if $KUBECTL get crd inferenceservices.serving.kserve.io >/dev/null 2>&1; then
  KSERVE_API_VERSION="serving.kserve.io/v1beta1"
elif $KUBECTL get crd inferenceservices.serving.kubeflow.org >/dev/null 2>&1; then
  KSERVE_API_VERSION="serving.kubeflow.org/v1beta1"
else
  die "no InferenceService CRD (KServe not installed?). Install KServe or ask platform team."
fi
log "using apiVersion=$KSERVE_API_VERSION"

# --- Already exists? ---
if $KUBECTL get inferenceservice -n "$NS" "$MCP_NAME" >/dev/null 2>&1; then
  log "InferenceService/$MCP_NAME already exists in $NS"
  $KUBECTL get inferenceservice -n "$NS" "$MCP_NAME" -o wide 2>/dev/null || true
  log "If monitoring still fails: check Istio sidecar, Prometheus, endpoint_name in PlayMCP API."
  exit 0
fi

# --- Discover image ---
if [ -z "$IMAGE" ]; then
  log "IMAGE not set — discovering from namespace $NS ..."
  for dep in "$MCP_NAME" "${MCP_NAME}-mcp" "csap-escape-probe" "csap-node-escape-probe"; do
    img="$($KUBECTL get deploy -n "$NS" "$dep" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
    if [ -n "$img" ]; then
      IMAGE="$img"
      log "found image from Deployment/$dep: $IMAGE"
      break
    fi
  done
fi
if [ -z "$IMAGE" ]; then
  POD="$($KUBECTL get pods -n "$NS" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep -F "$MCP_NAME" | head -1 || true)"
  if [ -n "$POD" ]; then
    IMAGE="$($KUBECTL get pod -n "$NS" "$POD" -o jsonpath='{.spec.containers[?(@.name!="istio-proxy")].image}' 2>/dev/null | awk 'NR==1{print;exit}')"
    [ -n "$IMAGE" ] && log "found image from Pod/$POD: $IMAGE"
  fi
fi
[ -n "$IMAGE" ] || die "set IMAGE=<registry>/csap-node-escape-probe:tag (could not auto-detect)"

# --- Optional: remove duplicate PlayMCP Deployment ---
if [ "$REMOVE_DEPLOY" = "1" ]; then
  for dep in "$MCP_NAME" "${MCP_NAME}-mcp"; do
    if $KUBECTL get deploy -n "$NS" "$dep" >/dev/null 2>&1; then
      warn "deleting Deployment/$dep (avoid duplicate MCP pods with InferenceService)"
      $KUBECTL delete deploy -n "$NS" "$dep" --wait=true
    fi
  done
else
  if $KUBECTL get deploy -n "$NS" -o name 2>/dev/null | grep -qF "$MCP_NAME"; then
    warn "Deployment matching '$MCP_NAME' exists. MCP Pod may be duplicated after IS apply."
    warn "Re-run with REMOVE_DEPLOY=1 to delete PlayMCP Deployment first (downtime ~1–2 min)."
  fi
fi

# --- Render & apply ---
export MCP_NAME NS NAMESPACE="$NS" CONTAINER_IMAGE="$IMAGE" KSERVE_API_VERSION
export SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-default}"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT INT HUP TERM

if command -v envsubst >/dev/null 2>&1; then
  envsubst <"$TEMPLATE" >"$TMP"
else
  die "envsubst required (gettext package)"
fi

log "applying InferenceService/$MCP_NAME in $NS ..."
$KUBECTL apply -f "$TMP"

log "waiting for Ready (up to 180s) ..."
deadline=$(( $(date +%s) + 180 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  ready="$($KUBECTL get inferenceservice -n "$NS" "$MCP_NAME" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)"
  if [ "$ready" = "True" ]; then
    log "InferenceService is Ready"
    $KUBECTL get inferenceservice -n "$NS" "$MCP_NAME" -o wide
    $KUBECTL get pods -n "$NS" -l "serving.kserve.io/inferenceservice=$MCP_NAME" -o wide 2>/dev/null || true
    log "Next: PlayMCP 모니터링 탭 새로고침 + Playground echo 트래픽"
    exit 0
  fi
  sleep 5
done

warn "InferenceService not Ready within 180s — check events:"
$KUBECTL describe inferenceservice -n "$NS" "$MCP_NAME" 2>/dev/null | tail -30 || true
exit 2
