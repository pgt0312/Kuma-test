# csap-node-escape-probe-internal-full

**Git 소스 빌드용** — 레포 **루트** = Docker 빌드 컨텍스트 (`Dockerfile` 위치)

| 문서 | 용도 |
|------|------|
| **[`GIT_BUILD.md`](./GIT_BUILD.md)** | ★ UI 필드·API·push 전 검증 |
| [`README.md`](./README.md) | 전체 기능 설명 |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | 배포 4층 |

```bash
docker build -t csap-node-escape-probe:git-build .
make run

make apply-is NS=<ns> MCP_NAME=csap-node-escape-probe IMAGE=<registry>/...:tag
```

기본(v2) 원본: [`../csap-node-escape-probe-internal/`](../csap-node-escape-probe-internal/)
