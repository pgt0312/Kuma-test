#!/usr/bin/env sh
# 승인된 점검 환경에서만 ENABLE_ACTIVE_TESTS=1 로 실행.
# 호스트 파일시스템에 쓰기·프로세스 조작은 하지 않고 읽기·존재 여부만 확인합니다.
set -eu

echo "[active_checks] read-only host surface checks"

for p in /proc/1/root /host /hostfs /var/lib/kubelet /var/run/docker.sock \
  /run/containerd/containerd.sock /run/crio/crio.sock; do
  if [ -e "$p" ]; then
    echo "EXISTS: $p"
    if [ -d "$p" ] && [ -r "$p" ]; then
      echo "LISTABLE (first 15):"
      ls -la "$p" 2>/dev/null | head -15 || true
    fi
  fi
done

echo "[active_checks] namespace inode compare (self vs PID 1)"
SPID=$$
for ns in mnt pid ipc uts net; do
  SP="/proc/$SPID/ns/$ns"
  HP="/proc/1/ns/$ns"
  if [ -e "$SP" ] && [ -e "$HP" ]; then
    S=$(readlink "$SP" 2>/dev/null || echo "?")
    H=$(readlink "$HP" 2>/dev/null || echo "?")
    echo "NS $ns: self=$S pid1=$H"
    if [ "$S" = "$H" ]; then
      echo "  SHARED_WITH_HOST: $ns"
    fi
  fi
done

if command -v nsenter >/dev/null 2>&1 && [ -r /proc/1/ns/mnt ]; then
  echo "[active_checks] nsenter mount namespace probe (read-only ls on PID 1)"
  nsenter --target 1 --mount -- ls -la / 2>/dev/null | head -20 || echo "nsenter failed (expected if confined)"
fi

echo "[active_checks] done"
