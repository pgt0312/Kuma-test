# csap-node-escape-probe-internal-full

**호스팅 플랫폼용** — Git·레지스트리 등록 방식 무관, **이미지 하나**

| 문서 | 용도 |
|------|------|
| **[`HOSTING.md`](./HOSTING.md)** | ★ 배포·Headlamp·RevisionFailed (통합) |
| [`README.md`](./README.md) | 기능·MCP 도구·K8s 프로파일 |
| [`GIT_BUILD.md`](./GIT_BUILD.md) | → HOSTING.md 로 리다이렉트 |

```bash
make verify TAG=git-build
git push origin main   # 플랫폼 Git 빌드 시
```

레포 루트 = Docker 빌드 컨텍스트 (`Dockerfile` 위치)
