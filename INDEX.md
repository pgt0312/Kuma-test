# csap-node-escape-probe-internal-full

**PlayMCP Git 소스 빌드용** — 레포 **루트** = Docker 빌드 컨텍스트 (`Dockerfile` 위치)

| 문서 | 용도 |
|------|------|
| **[`PLAYMCP_GIT_BUILD.md`](./PLAYMCP_GIT_BUILD.md)** | ★ UI 필드·API·push 전 검증 |
| [`README.md`](./README.md) | 전체 기능 설명 |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | 배포 4층 |

```bash
# 이 디렉터리 = Git remote 루트
docker build -t csap-node-escape-probe:playmcp-git .
make run

# Git 등록 후 모니터링 오류(1번) — InferenceService 생성
make apply-is NS=<ns> MCP_NAME=csap-node-escape-probe IMAGE=<registry>/...:tag
```

기본(v2) 원본: [`../csap-node-escape-probe-internal/`](../csap-node-escape-probe-internal/)
