# Git 소스 빌드

> **등록·배포 통합 가이드는 [`HOSTING.md`](./HOSTING.md) 를 보세요.**  
> Git 빌드도 레지스트리 이미지도 **동일 `Dockerfile`·entrypoint** 를 씁니다.

플랫폼이 Git 모드를 쓸 때만 추가로 필요한 것:

| 항목 | 값 |
|------|-----|
| 레포 루트 | 이 디렉터리 전체 push |
| Dockerfile | `Dockerfile` (루트) |
| PAT | 비공개 HTTPS 저장소일 때 |

```bash
make verify && git push origin main
```

상세·Headlamp·RevisionFailed: [`HOSTING.md`](./HOSTING.md)
