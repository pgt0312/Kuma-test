"""
서비스 영향을 최소화한 읽기 전용 취약성·설정 검증.

- 파일/프로세스 읽기, 짧은 타임아웃의 TCP 연결 시도만 사용 (쓰기·익스플로잇 없음)
- ENABLE_SAFE_NET_CHECKS=1 일 때만 메타데이터·K8s API TCP 프로브 (기본 꺼짐)
"""
from __future__ import annotations

import os
import re
import socket
import stat
import subprocess
from pathlib import Path
from typing import Any

_SENSITIVE_ENV_RE = re.compile(
    r"(PASSWORD|SECRET|TOKEN|PRIVATE[_-]?KEY|API[_-]?KEY|CREDENTIAL|AUTH)",
    re.IGNORECASE,
)
_SENSITIVE_MOUNT_POINTS = {
    "/",
    "/host",
    "/hostfs",
    "/var/lib/kubelet",
    "/var/run",
    "/run",
    "/etc",
    "/root",
}
_EXTRA_SOCKETS = (
    "/var/run/docker.sock",
    "/run/containerd/containerd.sock",
    "/run/k3s/containerd/containerd.sock",
    "/run/crio/crio.sock",
    "/var/run/cri-dockerd.sock",
)
_RISKY_CAP_SUBSTRINGS = (
    "cap_sys_ptrace",
    "cap_sys_module",
    "cap_net_raw",
    "cap_dac_override",
    "cap_sys_chroot",
    "cap_mknod",
)


def _read(path: str, limit: int = 16_000) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return None


def _proc_status() -> dict[str, str]:
    out: dict[str, str] = {}
    text = _read("/proc/self/status") or ""
    for line in text.splitlines():
        for key in (
            "NoNewPrivs",
            "Seccomp",
            "Seccomp_filters",
            "CapEff",
            "CapPrm",
            "CapBnd",
        ):
            if line.startswith(f"{key}:"):
                out[key] = line.split(":", 1)[1].strip()
    return out


def _lsm_context() -> dict[str, Any]:
    current = _read("/proc/self/attr/current", 256)
    prev = _read("/proc/self/attr/prev", 256)
    return {
        "attr_current": current,
        "attr_prev": prev,
        "apparmor_enforced": bool(current and "enforce" in current.lower()),
        "unconfined": bool(current and "unconfined" in current.lower()),
    }


def _mount_rw_flags() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (_read("/proc/self/mountinfo") or "").splitlines()[:120]:
        parts = line.split()
        if len(parts) < 6:
            continue
        mount_point = parts[4]
        opts = parts[5] if len(parts) > 5 else ""
        rw = "rw" in opts.split(",")
        sensitive = mount_point in _SENSITIVE_MOUNT_POINTS or any(
            x in line for x in ("kubelet", "docker.sock", "containerd.sock")
        )
        if rw and (sensitive or mount_point == "/"):
            rows.append(
                {
                    "mount_point": mount_point,
                    "rw": True,
                    "sensitive": sensitive,
                }
            )
    return rows[:25]


def _sensitive_env_key_names() -> list[str]:
    return sorted(k for k in os.environ if _SENSITIVE_ENV_RE.search(k))


def _sa_token_stat() -> dict[str, Any]:
    path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    if not path.is_file():
        return {"present": False}
    try:
        st = path.stat()
        mode = stat.S_IMODE(st.st_mode)
        return {
            "present": True,
            "mode_octal": oct(mode),
            "world_readable": bool(mode & 0o004),
            "group_readable": bool(mode & 0o040),
        }
    except OSError as exc:
        return {"present": True, "stat_error": str(exc)}


def _namespace_inodes() -> dict[str, Any]:
    def ino(pid: str, ns: str) -> str | None:
        link = _read(f"/proc/{pid}/ns/{ns}", 64)
        return link.strip() if link else None

    self_pid = str(os.getpid())
    result: dict[str, Any] = {"self_pid": self_pid}
    for ns in ("mnt", "pid", "ipc", "uts", "net"):
        s = ino(self_pid, ns)
        h = ino("1", ns)
        result[ns] = {"self": s, "pid1": h, "shared_with_host": bool(s and h and s == h)}
    return result


def _listen_snapshot() -> dict[str, Any]:
    for cmd in (
        ["ss", "-ltn"],
        ["netstat", "-ltn"],
    ):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if proc.returncode != 0 and not proc.stdout:
                continue
            lines = (proc.stdout or "").splitlines()[:40]
            wildcard = [ln for ln in lines if "0.0.0.0:" in ln or "*:" in ln or "[::]:" in ln]
            return {
                "cmd": cmd,
                "line_count": len(lines),
                "wildcard_bind_lines": wildcard[:15],
                "sample": lines[:20],
            }
        except (OSError, subprocess.TimeoutExpired):
            continue
    return {"error": "ss/netstat unavailable"}


def _tcp_reachable(host: str, port: int, timeout: float = 0.8) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"host": host, "port": port, "reachable": True}
    except OSError as exc:
        return {"host": host, "port": port, "reachable": False, "error": str(exc)}


def _optional_net_checks() -> dict[str, Any]:
    results: dict[str, Any] = {}
    results["metadata_169"] = _tcp_reachable("169.254.169.254", 80)
    try:
        infos = socket.getaddrinfo(
            "kubernetes.default.svc.cluster.local",
            443,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        ip = infos[0][4][0]
        results["kubernetes_api"] = _tcp_reachable(ip, 443)
        results["kubernetes_resolved_ip"] = ip
    except OSError as exc:
        results["kubernetes_api"] = {"reachable": False, "error": str(exc)}
    return results


def _findings_from_data(data: dict[str, Any], enable_net: bool) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    proc = data.get("proc_status") or {}

    if proc.get("NoNewPrivs") == "0":
        findings.append(
            {
                "id": "V-NONEW-PRIVS",
                "severity": "medium",
                "title": "NoNewPrivs 미적용 (allowPrivilegeEscalation 가능성)",
                "hint": "securityContext.allowPrivilegeEscalation: false 권장",
            }
        )

    seccomp = proc.get("Seccomp", "")
    if seccomp == "0":
        findings.append(
            {
                "id": "V-SECCOMP-DISABLED",
                "severity": "medium",
                "title": "Seccomp 필터 미적용",
                "hint": "seccompProfile.type: RuntimeDefault 또는 Localhost",
            }
        )

    lsm = data.get("lsm") or {}
    if lsm.get("unconfined"):
        findings.append(
            {
                "id": "V-LSM-UNCONFINED",
                "severity": "medium",
                "title": "LSM(AppArmor/SELinux) unconfined 프로파일",
                "hint": "Pod security / AppArmor profile 적용 검토",
            }
        )

    if data.get("root_writable"):
        findings.append(
            {
                "id": "V-ROOT-WRITABLE",
                "severity": "medium",
                "title": "컨테이너 루트(/) 파일시스템에 쓰기 가능",
                "hint": "readOnlyRootFilesystem: true 검토",
            }
        )

    for m in data.get("mount_rw_sensitive") or []:
        if m.get("sensitive"):
            findings.append(
                {
                    "id": "V-MOUNT-RW-SENSITIVE",
                    "severity": "high",
                    "title": f"민감 경로 RW 마운트: {m.get('mount_point')}",
                    "hint": "hostPath readOnly: true 및 마운트 최소화",
                }
            )
            break

    caps_blob = (proc.get("CapEff", "") + proc.get("CapPrm", "")).lower()
    for cap in _RISKY_CAP_SUBSTRINGS:
        if cap in caps_blob:
            findings.append(
                {
                    "id": f"V-CAP-{cap.upper().replace('CAP_', '')}",
                    "severity": "high",
                    "title": f"위험 capability 후보: {cap}",
                    "hint": "capabilities.drop=ALL 및 add 최소화",
                }
            )
            break

    env_keys = data.get("sensitive_env_key_names") or []
    if env_keys:
        findings.append(
            {
                "id": "V-ENV-SENSITIVE-KEYS",
                "severity": "info",
                "title": f"민감 이름 환경 변수 키 {len(env_keys)}개 (값은 수집 안 함)",
                "hint": "Secret/ConfigMap·external secret 사용 권장",
            }
        )

    tok = data.get("sa_token_stat") or {}
    if tok.get("world_readable"):
        findings.append(
            {
                "id": "V-K8S-TOKEN-WORLD-READ",
                "severity": "high",
                "title": "ServiceAccount 토큰 파일이 world-readable",
                "hint": "토큰 권한·projected volume 설정 점검",
            }
        )

    for sock in data.get("extra_sockets") or []:
        if sock.get("exists"):
            findings.append(
                {
                    "id": "V-RUNTIME-SOCK",
                    "severity": "critical",
                    "title": f"런타임 소켓 노출: {sock.get('path')}",
                    "hint": "volume 마운트 제거",
                }
            )
            break

    ns = data.get("namespaces") or {}
    for ns_name in ("pid", "ipc", "net", "mnt"):
        if (ns.get(ns_name) or {}).get("shared_with_host"):
            findings.append(
                {
                    "id": f"V-NS-SHARE-{ns_name.upper()}",
                    "severity": "high" if ns_name in ("pid", "mnt") else "medium",
                    "title": f"호스트와 {ns_name} 네임스페이스 공유 가능",
                    "hint": "hostPID/hostIPC/hostNetwork/hostPath 정책 점검",
                }
            )
            break

    listen = data.get("listen_snapshot") or {}
    if listen.get("wildcard_bind_lines"):
        findings.append(
            {
                "id": "V-LISTEN-WILDCARD",
                "severity": "info",
                "title": "0.0.0.0/::* 바인드 리스너 감지",
                "hint": "불필요한 포트 노출·NetworkPolicy 검토",
            }
        )

    if enable_net:
        net = data.get("optional_net") or {}
        if (net.get("metadata_169") or {}).get("reachable"):
            findings.append(
                {
                    "id": "V-NET-CLOUD-METADATA",
                    "severity": "info",
                    "title": "링크 로컬 메타데이터(169.254.169.254) TCP 도달 가능",
                    "hint": "IMDS hop limit·네트워크 정책으로 차단 여부 확인",
                }
            )
        if (net.get("kubernetes_api") or {}).get("reachable"):
            findings.append(
                {
                    "id": "V-NET-K8S-API",
                    "severity": "info",
                    "title": "Kubernetes API(443) TCP 도달 가능",
                    "hint": "RBAC·NetworkPolicy로 API 남용 경로 점검",
                }
            )

    return findings


def collect_safe_verification(enable_net: bool | None = None) -> dict[str, Any]:
    if enable_net is None:
        enable_net = os.environ.get("ENABLE_SAFE_NET_CHECKS", "0") == "1"

    extra_sockets = [{"path": p, "exists": Path(p).exists()} for p in _EXTRA_SOCKETS]

    data: dict[str, Any] = {
        "mode": "read_only",
        "network_checks_enabled": enable_net,
        "proc_status": _proc_status(),
        "lsm": _lsm_context(),
        "root_writable": os.access("/", os.W_OK),
        "mount_rw_sensitive": _mount_rw_flags(),
        "sensitive_env_key_names": _sensitive_env_key_names(),
        "sa_token_stat": _sa_token_stat(),
        "namespaces": _namespace_inodes(),
        "extra_sockets": extra_sockets,
        "listen_snapshot": _listen_snapshot(),
    }
    if enable_net:
        data["optional_net"] = _optional_net_checks()

    findings = _findings_from_data(data, enable_net)
    return {
        "data": data,
        "findings": findings,
        "finding_count": len(findings),
    }
