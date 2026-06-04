# PlayMCP「Git 소스 빌드」등록 가이드

이 저장소 **루트**가 PlayMCP Git clone·`docker build` 컨텍스트입니다.  
(`repo/` 하위가 아님 — **이 디렉터리 전체**를 Git remote에 push)

---

## 1. UI 입력값 (복사용)

| 필드 | 값 |
|------|-----|
| **MCP 서버 이름** | `csap-node-escape-probe` |
| **설명** | PlayMCP 호환 MCP(8080/mcp). Pod 내 컨테이너 이스케이프·보안설정 읽기 전용 진단(R-*, V-*). 자동 익스플로잇 없음. CSAP 점검용. |
| **Git URL** | 이 저장소 HTTPS URL (예: `https://github.com/<org>/csap-node-escape-probe-internal-full.git`) |
| **브랜치 / ref** | `main` (실제 default branch) |
| **Personal Access Token** | 비공개 HTTPS 저장소일 때만 |
| **Dockerfile** (고급·기본) | `Dockerfile` |

배포 후 플랫폼 설정(이미지 등록 경로와 동일):

| 항목 | 값 |
|------|-----|
| 컨테이너 포트 | **8080** |
| Transport | **streamablehttp** |
| MCP URL | `http://<svc>:8080/mcp` |

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
  entrypoint.sh     ← uvicorn :8080
  run_probe.py
  safe_verification.py
  ...
```

---

## 4. push 전 로컬 검증

```bash
docker build -t csap-node-escape-probe:playmcp-git .
docker run --rm -p 8080:8080 \
  -e MCP_SERVER_NAME=csap-node-escape-probe \
  csap-node-escape-probe:playmcp-git

curl -s http://127.0.0.1:8080/health
curl -s -X POST http://127.0.0.1:8080/probe/run | python3 -m json.tool | head -40
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

## 6. 주의

- **kubelet 10250** 은 이 이미지와 무관 (노드 설정).
- 모니터링 RPS 차트는 PlayMCP **InferenceService + Istio** 필요 → [`../24_playmcp_istio_inference_service.md`](../24_playmcp_istio_inference_service.md)
- `ENABLE_ACTIVE_TESTS=1` · lab K8s는 격리 환경만.

---

상세 기능: [`README.md`](./README.md)
