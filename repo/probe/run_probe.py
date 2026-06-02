#!/usr/bin/env python3
"""
컨테이너 내부에서 노드 이스케이프 관련 misconfiguration·노출 지표를 수집합니다.
자동 익스플로잇은 수행하지 않습니다.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from probe.safe_verification import collect_safe_verification

REPORT_DIR = Path(os.environ.get("PROBE_REPORT_DIR", "/data/reports"))
_LAST_PROBE_MONO: float = 0.0


def _run(cmd: list[str], timeout: int = 10) -> dict[str, Any]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "cmd": cmd,
            "exit_code": p.returncode,
            "stdout": (p.stdout or "")[:8000],
            "stderr": (p.stderr or "")[:2000],
        }
    except Exception as exc:  # noqa: BLE001
        return {"cmd": cmd, "error": str(exc)}


def _read(path: str, limit: int = 64_000) -> str | None:
    try:
        data = Path(path).read_text(encoding="utf-8", errors="replace")
        return data[:limit]
    except OSError:
        return None


def _file_exists(path: str) -> bool:
    return Path(path).exists()


def _list_dir(path: str, max_entries: int = 40) -> list[str] | None:
    try:
        entries = sorted(os.listdir(path))[:max_entries]
        return entries
    except OSError:
        return None


def _caps() -> dict[str, Any]:
    capsh = _run(["capsh", "--print"])
    caps = _run(["cat", "/proc/self/status"])
    cap_line = ""
    if caps.get("stdout"):
        for line in caps["stdout"].splitlines():
            if line.startswith("CapEff:") or line.startswith("CapPrm:"):
                cap_line += line + "\n"
    return {"capsh": capsh, "proc_caps": cap_line.strip()}


def _mounts() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    content = _read("/proc/self/mountinfo") or ""
    for line in content.splitlines()[:80]:
        parts = line.split()
        if len(parts) < 5:
            continue
        mount_point = parts[4]
        rows.append(
            {
                "mount_point": mount_point,
                "line": line[:500],
                "host_suspect": mount_point in {
                    "/",
                    "/host",
                    "/hostfs",
                    "/var/lib/kubelet",
                    "/var/run",
                    "/run",
                }
                or "kubelet" in line
                or "docker.sock" in line
                or "containerd.sock" in line,
            }
        )
    return rows


def _likely_host_pid_namespace() -> bool:
    try:
        proc_entries = [x for x in os.listdir("/proc") if x.isdigit()]
        if len(proc_entries) > 40:
            return True
        cmdline = _read("/proc/1/cmdline", 500) or ""
        if "systemd" in cmdline or "kubelet" in cmdline or "containerd" in cmdline:
            return True
    except OSError:
        pass
    return False


def _risk_findings(report: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    if report.get("identity", {}).get("uid") == 0:
        findings.append(
            {
                "id": "R-UID0",
                "severity": "high",
                "title": "컨테이너가 root(UID 0)로 실행 중",
                "hint": "securityContext.runAsNonRoot 및 runAsUser 점검",
            }
        )

    caps_text = (report.get("capabilities") or {}).get("proc_caps") or ""
    if "0000003fffffffff" in caps_text.replace(" ", "").lower() or "cap_sys_admin" in caps_text.lower():
        findings.append(
            {
                "id": "R-CAP-SYS-ADMIN",
                "severity": "high",
                "title": "CAP_SYS_ADMIN 또는 전체 capability 가능성",
                "hint": "privileged / capabilities.drop=ALL 미적용 여부 확인",
            }
        )

    for m in report.get("mounts") or []:
        if m.get("host_suspect"):
            findings.append(
                {
                    "id": "R-MOUNT-HOST",
                    "severity": "high",
                    "title": f"호스트 의심 마운트: {m.get('mount_point')}",
                    "hint": "hostPath·kubelet·소켓 마운트 정책 점검",
                }
            )
            break

    if report.get("host_paths", {}).get("proc_1_root_listable"):
        findings.append(
            {
                "id": "R-PROC1-ROOT",
                "severity": "critical",
                "title": "/proc/1/root (호스트 init) 디렉터리 열람 가능",
                "hint": "privileged Pod — 수동 chroot/nsenter 검증 대상 (승인 점검만)",
            }
        )

    if _file_exists("/var/run/docker.sock"):
        findings.append(
            {
                "id": "R-DOCKER-SOCK",
                "severity": "critical",
                "title": "docker.sock 마운트 감지",
                "hint": "소켓 경유 호스트/컨테이너 탈출 가능성 — 즉시 격리 검토",
            }
        )

    if _file_exists("/run/containerd/containerd.sock") or _file_exists(
        "/run/k3s/containerd/containerd.sock"
    ):
        findings.append(
            {
                "id": "R-CONTAINERD-SOCK",
                "severity": "critical",
                "title": "containerd.sock 마운트 감지",
                "hint": "호스트 런타임 제어 가능성",
            }
        )

    if report.get("kubernetes", {}).get("service_account_token_present"):
        findings.append(
            {
                "id": "R-K8S-SA",
                "severity": "info",
                "title": "ServiceAccount 토큰 마운트됨",
                "hint": "RBAC·토큰 권한으로 API/노드 lateral 이동 여부 별도 점검",
            }
        )

    if report.get("environment", {}).get("host_pid_likely"):
        findings.append(
            {
                "id": "R-HOST-PID",
                "severity": "high",
                "title": "hostPID 네임스페이스 공유 가능성",
                "hint": "hostPID: true — nsenter·호스트 프로세스 접근 수동 검증",
            }
        )

    host_net = (report.get("environment", {}).get("host_network_env") or "").lower()
    if host_net in ("1", "true", "yes"):
        findings.append(
            {
                "id": "R-HOST-NET",
                "severity": "medium",
                "title": "hostNetwork 사용 가능성",
                "hint": "노드 네트워크 스택 직접 노출",
            }
        )

    return findings


def build_report() -> dict[str, Any]:
    hostname = socket.gethostname()
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image": os.environ.get("PROBE_IMAGE_TAG", "csap-node-escape-probe"),
        "identity": {
            "uid": os.getuid(),
            "gid": os.getgid(),
            "user": _run(["id"])["stdout"].strip(),
            "hostname": hostname,
        },
        "environment": {
            "host_pid_likely": _likely_host_pid_namespace(),
            "host_pid_env": os.environ.get("HOST_PID", ""),
            "host_network_env": os.environ.get("HOST_NETWORK", ""),
            "enable_active_tests": os.environ.get("ENABLE_ACTIVE_TESTS", "0"),
            "proc_count": len([x for x in os.listdir("/proc") if x.isdigit()])
            if os.access("/proc", os.R_OK)
            else None,
        },
        "capabilities": _caps(),
        "mounts": _mounts(),
        "host_paths": {
            "proc_1_root_listable": _list_dir("/proc/1/root") is not None,
            "proc_1_root_sample": _list_dir("/proc/1/root"),
            "host_path_exists": {
                "/host": _file_exists("/host"),
                "/hostfs": _file_exists("/hostfs"),
                "/var/lib/kubelet": _file_exists("/var/lib/kubelet"),
            },
        },
        "kubernetes": {
            "service_account_token_present": _file_exists(
                "/var/run/secrets/kubernetes.io/serviceaccount/token"
            ),
            "namespace": _read(
                "/var/run/secrets/kubernetes.io/serviceaccount/namespace", 200
            ),
            "ca_present": _file_exists(
                "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
            ),
        },
        "sockets": {
            "docker_sock": _file_exists("/var/run/docker.sock"),
            "containerd_sock": _file_exists("/run/containerd/containerd.sock"),
        },
        "commands": {
            "mount": _run(["findmnt", "-J"], timeout=15),
            "nsenter_version": _run(["nsenter", "--version"]),
        },
    }
    escape_findings = _risk_findings(report)
    safe = collect_safe_verification()
    report["safe_verification"] = safe["data"]
    report["risk_findings"] = escape_findings + safe["findings"]
    report["summary"] = {
        "finding_count": len(report["risk_findings"]),
        "escape_finding_count": len(escape_findings),
        "safe_verification_finding_count": len(safe["findings"]),
        "max_severity": _max_severity(report["risk_findings"]),
    }
    return report


def build_safe_verification_report() -> dict[str, Any]:
    """가벼운 읽기 전용 검증만 수행 (이스케이프 프로브 생략)."""
    safe = collect_safe_verification()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "safe_verification_only",
        "safe_verification": safe["data"],
        "risk_findings": safe["findings"],
        "summary": {
            "finding_count": len(safe["findings"]),
            "max_severity": _max_severity(safe["findings"]),
        },
    }


def _max_severity(findings: list[dict[str, str]]) -> str:
    order = {"info": 0, "medium": 1, "high": 2, "critical": 3}
    best = "info"
    for f in findings:
        sev = f.get("severity", "info")
        if order.get(sev, 0) >= order.get(best, 0):
            best = sev
    return best if findings else "none"


def save_report(report: dict[str, Any] | None = None) -> dict[str, Any]:
    """리포트를 /data/reports 에 저장하고 dict 반환."""
    global _LAST_PROBE_MONO
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if report is None:
        min_interval = float(os.environ.get("PROBE_MIN_INTERVAL_SEC", "0") or "0")
        if min_interval > 0:
            elapsed = time.monotonic() - _LAST_PROBE_MONO
            if _LAST_PROBE_MONO > 0 and elapsed < min_interval:
                cached = load_latest_report()
                if cached is not None:
                    cached = dict(cached)
                    cached["probe_throttled"] = {
                        "skipped": True,
                        "min_interval_sec": min_interval,
                        "retry_after_sec": round(min_interval - elapsed, 1),
                    }
                    return cached
        data = build_report()
        _LAST_PROBE_MONO = time.monotonic()
    else:
        data = report
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = REPORT_DIR / f"escape-probe-{ts}.json"
    latest = REPORT_DIR / "latest.json"
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    out.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    return data


def load_latest_report() -> dict[str, Any] | None:
    latest = REPORT_DIR / "latest.json"
    if not latest.is_file():
        return None
    return json.loads(latest.read_text(encoding="utf-8"))


def main() -> int:
    report = save_report()
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    print(payload)
    return 0 if report["summary"]["max_severity"] not in ("critical",) else 2


if __name__ == "__main__":
    sys.exit(main())
