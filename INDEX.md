# csap-node-escape-probe-internal-full — 확장 기능 복제본

| 경로 | 용도 |
|------|------|
| [`README.md`](./README.md) | **전체 기능 설명** (MCP·REST·R-*·V-*·PlayMCP·K8s) |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | 배포 4층 다이어그램 |
| [`repo/`](./repo/) | 확장 소스 (`safe_verification`, `playmcp_monitoring` 포함) |

원본(v2 기본): [`../csap-node-escape-probe-internal/`](../csap-node-escape-probe-internal/)

```bash
cd playmcp/csap-node-escape-probe-internal-full/repo
make build TAG=v2-mcp-full
make run
curl -s http://127.0.0.1:8080/probe/safe-verify | python3 -m json.tool
```
