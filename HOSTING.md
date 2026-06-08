# 호스팅 배포 가이드 (통합)

> **등록 방식(Git 빌드 / 레지스트리 이미지)은 플랫폼·운영이 결정합니다.**  
> 개발자는 **이 레포(`internal-full` 루트) 이미지 하나**만 맞추면 됩니다.

---

## 1. 한 줄 요약

| 항목 | 값 |
|------|-----|
| 레포 루트 | `internal-full/` 전체 (`Dockerfile` 위치) |
| 런타임 | KServe `kserve-mcpserver` (플랫폼 `mcp-server-builder`) |
| 프로토콜 | Streamable HTTP **`/mcp`** |
| 포트 | **플랫폼이 `PORT` env 주입** — 이미지는 **8080·8000 둘 다 동작** (고정 금지) |
| 기동 | `exec uvicorn` — Predictor Pod는 **Running** 이어야 함 |

---

## 2. 개발자가 할 일 (3단계만)

```bash
cd playmcp/csap-node-escape-probe-internal-full

# 1) 검증 (8080·8000 모두)
make verify

# 2) Git push (플랫폼 Git 빌드 시)
git add -A && git commit -m "..." && git push origin main

# 3) 플랫폼 배포 결과 확인 (Headlamp / UI)
#    — 재등록·삭제는 운영 절차. 개발자는 이미지·push만 담당.
```

---

## 3. 플랫폼이 하는 일 (참고)

```
등록 트리거 (Git 또는 레지스트리 — 플랫폼 선택)
  → mcp-build-apply Job Pod (Completed = 정상, 일회성)
  → 이미지 빌드·push
  → InferenceService + Revision
  → Predictor Pod (Running 1/1 = 성공)
  → mcp_tools 동기화 → UI Active·Tools
```

**개발자가 Headlamp에서 `mcp-build-apply-*` 만 보고 Completed인 것은 정상입니다.**  
확인 대상은 **`csap-node-escape-probe-predictor-*` Running 1/1** 입니다.

---

## 4. 이미지 설계 원칙 (v2.2.0+)

| 원칙 | 이유 |
|------|------|
| Dockerfile에 **`ENV PORT` 없음** | 플랫폼 주입값과 충돌 시 `RevisionFailed` |
| `entrypoint.sh`가 **`PORT` env만** listen | 8080·8000 클러스터 모두 대응 |
| `RUN_PROBE_ON_START=0` | TCP readiness 전 포트 즉시 오픈 |
| `exec uvicorn` | Job처럼 Completed로 끝나지 않음 |

---

## 5. Headlamp 확인 (운영·점검 공통)

| 대상 | 기대 |
|------|------|
| Pod `mcp-build-apply-*` | **Completed** |
| Pod `*-predictor-*` | **Running 1/1** |
| InferenceService | **READY: True** |
| Pod 로그 | `listen 0.0.0.0:8080` 또는 `:8000` |
| `/health` JSON | `"listen_port"` = 로그 포트 |

### 실패 패턴

| 증상 | 원인 |
|------|------|
| `RevisionFailed` / Initial scale was never achieved | PORT 불일치 또는 예전 이미지(`ENV PORT=8000` bake) |
| Predictor **Completed** | entrypoint 덮어쓰기·즉시 종료 |
| `mcp-build`만 있고 predictor 없음 | Revision 실패 |
| UI InProgress·Tools 없음 | Predictor 미Ready → mcp_tools `/health` 실패 |

---

## 6. Git remote (예시)

| 필드 | 값 |
|------|-----|
| Git URL | `https://github.com/pgt0312/Kuma-test.git` |
| branch | `main` |
| Dockerfile | `Dockerfile` |

레지스트리 직접 등록 시에도 **동일 이미지** (`ENTRYPOINT`·`PORT` 동작 동일).

---

## 7. 모니터링 (별도)

MCP Active 후에도 Istio 차트가 비면 [`../24_istio_inference_service_monitoring.md`](../24_istio_inference_service_monitoring.md) 참고.

---

기능 상세: [`README.md`](./README.md)  
레거시 Git 빌드 문서: [`GIT_BUILD.md`](./GIT_BUILD.md) → 본 문서로 통합
