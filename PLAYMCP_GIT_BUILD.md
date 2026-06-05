# PlayMCP「Git 소스 빌드」등록 가이드

이 저장소 **루트**가 PlayMCP Git clone·`docker build` 컨텍스트입니다.  
(`repo/` 하위가 아님 — **이 디렉터리 전체**를 Git remote에 push)

---

## 1. UI 입력값 (복사용)

| 필드 | 값 |
|------|-----|
| **MCP 서버 이름** | `csap-node-escape-probe` |
| **설명** | PlayMCP 호환 MCP(8000/mcp, KServe kserve-mcpserver). Pod 내 컨테이너 이스케이프·보안설정 읽기 전용 진단(R-*, V-*). 자동 익스플로잇 없음. CSAP 점검용. |
| **Git URL** | 이 저장소 HTTPS URL (예: `https://github.com/<org>/csap-node-escape-probe-internal-full.git`) |
| **브랜치 / ref** | `main` (실제 default branch) |
| **Personal Access Token** | 비공개 HTTPS 저장소일 때만 |
| **Dockerfile** (고급·기본) | `Dockerfile` |

배포 후 플랫폼 설정(이미지 등록 경로와 동일):

| 항목 | 값 |
|------|-----|
| 컨테이너 포트 | **8000** (플랫폼이 `PORT=8000` 주입·TCP readiness) |
| Transport | **streamablehttp** |
| MCP URL | `http://<svc>:8000/mcp` |

---

## 2. API 본문 예시 (`image_build_mode: git`)

PlayMCP가 전송하는 JSON 형태(참고):

```json
{
  "image_build_mode": "git",
  "dockerfile": "Dockerfile",
  "server_name": "csap-node-escape-probe",
  "description": "PlayMCP 호환 MCP + read-only escape/safe verification probe",
  "category": "security",
  "git_url": "https://github.com/<org>/<repo>.git",
  "git_ref": "main",
  "git_pat": "<비공개일 때만>"
}
```

---

## 3. 레포 루트 필수 파일

```text
Dockerfile          ← PlayMCP 빌드 필수
server.py
requirements.txt
probe/
  entrypoint.sh     ← uvicorn :8000 (PORT env)
  run_probe.py
  safe_verification.py
  ...
```

---

## 4. push 전 로컬 검증

```bash
docker build -t csap-node-escape-probe:playmcp-git .
docker run --rm -p 8000:8000 \
  -e MCP_SERVER_NAME=csap-node-escape-probe \
  csap-node-escape-probe:playmcp-git

curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/probe/run | python3 -m json.tool | head -40
```

---

## 5. Playground에서 호출할 MCP 도구

| 도구 | 용도 |
|------|------|
| `echo` | 연결 확인 |
| `server_info` | 메타 + PlayMCP 모니터링 힌트 |
| `run_escape_probe` | 전체 진단 (R-* + V-*) |
| `run_safe_verification` | 저영향 검증만 |
| `playmcp_monitoring_checklist` | InferenceService/Istio UI 오류 대응 |

---

## 6. KServe 배포 정합성 (InProgress 장기화 방지)

PlayMCP `mcp-server-builder`는 **KServe `kserve-mcpserver`** 런타임으로 배포합니다.

| 플랫폼 | 이미지 기본 (v2.1.1+) |
|--------|------------------------|
| `PORT=8000` | `ENV PORT=8000` |
| TCP readiness `:8000` | `RUN_PROBE_ON_START=0` (포트 즉시 오픈) |
| `serving.kserve.io/inferenceservice=<MCP이름>` | MCP 서버 이름 = `endpoint_name` |

**8080으로 등록하면** TCP 프로브(8000)와 불일치해 **InProgress**가 길어질 수 있습니다.

---

## 7. 모니터링 오류 해결 (1번: InferenceService 없음)

Git 소스 빌드만 하면 **Pod/Deployment는 생기지만 `InferenceService` CR은 자동 생성되지 않습니다.**  
모니터링 탭 오류:

> 클러스터에 해당 InferenceService가 없습니다. Istio 메트릭 라벨을 확인할 수 없습니다.

### 7.1 등록 직후 한 번 실행 (권장)

PlayMCP에서 MCP가 **Active** 이고 Playground가 동작한 뒤:

```bash
# PlayMCP UI의 MCP 서버 이름·워크그룹 NS와 동일하게
export MCP_NAME='csap-node-escape-probe'
export NS='<your-kubeflow-namespace>'

# PlayMCP가 빌드·배포한 이미지 (UI 또는 kubectl get deploy ... -o jsonpath=...image)
export IMAGE='<registry>/csap-node-escape-probe:<tag>'

chmod +x scripts/apply-inferenceservice-for-playmcp.sh

# IS 생성 (기존 PlayMCP Deployment와 Pod 중복 시 아래처럼)
./scripts/apply-inferenceservice-for-playmcp.sh

# 중복 Pod 방지: PlayMCP Deployment 삭제 후 IS만 사용 (짧은 재기동)
# REMOVE_DEPLOY=1 ./scripts/apply-inferenceservice-for-playmcp.sh
```

또는 Makefile:

```bash
make apply-is NS="$NS" MCP_NAME="$MCP_NAME" IMAGE="$IMAGE"
# make apply-is NS="$NS" MCP_NAME="$MCP_NAME" IMAGE="$IMAGE" REMOVE_DEPLOY=1
```

### 7.2 확인

```bash
kubectl get inferenceservice -n "$NS" "$MCP_NAME"
make check-is NS="$NS" MCP_NAME="$MCP_NAME"
```

PlayMCP에서:

1. MCP 상세 API `endpoint_name` == `csap-node-escape-probe` 인지 확인  
2. Playground `echo` 20회 → **모니터링** 탭 새로고침  

### 7.3 한계

- 이 스크립트는 **PlayMCP 백엔드 대체**가 아니라, Git 빌드 후 **수동/운영 보완**입니다.
- 플랫폼이 Git 빌드 시 IS를 자동 생성하도록 바뀌면 이 단계는 불필요해집니다.
- KServe·Istio·Prometheus가 없는 클러스터에서는 IS만으로 모니터링이 안 될 수 있습니다.

매니페스트: [`k8s/inference-service-playmcp.yaml`](./k8s/inference-service-playmcp.yaml)

---

## 8. 주의

- **kubelet 10250** 은 이 이미지와 무관 (노드 설정).
- 상세 원인: [`../24_playmcp_istio_inference_service.md`](../24_playmcp_istio_inference_service.md)
- `ENABLE_ACTIVE_TESTS=1` · lab K8s는 격리 환경만.

---

상세 기능: [`README.md`](./README.md)
