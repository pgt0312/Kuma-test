"""
Read-only network reachability checks for private 192.168.0.0/16 ranges.

This module intentionally does not perform broad port scanning. It only tries
short TCP connects against a bounded set of hosts and ports, and it is disabled
unless ENABLE_SAFE_NET_CHECKS=1 is set.
"""
from __future__ import annotations

import ipaddress
import os
import socket
import time
from datetime import datetime, timezone
from typing import Any

_ALLOWED_192_168 = ipaddress.ip_network("192.168.0.0/16")
_DEFAULT_PORTS = (80, 443, 8000, 8080)
_DEFAULT_CANDIDATE_LAST_OCTETS = (1, 10, 20, 50, 100, 200, 254)
_DEFAULT_CANDIDATE_THIRD_OCTETS = (0, 1, 10, 20, 50, 100, 168)
_MAX_HOSTS_HARD_LIMIT = 128
_MAX_PORTS_HARD_LIMIT = 16


def _enabled() -> bool:
    return os.environ.get("ENABLE_SAFE_NET_CHECKS", "0").strip().lower() in {"1", "true", "yes", "on"}


def _parse_ports(ports: list[int] | str | None) -> list[int]:
    if ports is None:
        raw = os.environ.get("NET_CHECK_192_168_PORTS", "")
        items: list[str | int] = raw.split(",") if raw else list(_DEFAULT_PORTS)
    elif isinstance(ports, str):
        items = ports.split(",")
    else:
        items = ports

    parsed: list[int] = []
    for item in items:
        try:
            port = int(str(item).strip())
        except ValueError:
            continue
        if 1 <= port <= 65535 and port not in parsed:
            parsed.append(port)
        if len(parsed) >= _MAX_PORTS_HARD_LIMIT:
            break
    return parsed or list(_DEFAULT_PORTS)


def _parse_hosts(hosts: list[str] | str | None, max_hosts: int) -> list[str]:
    if hosts is None:
        raw = os.environ.get("NET_CHECK_192_168_TARGETS", "")
        if raw:
            host_items = [x.strip() for x in raw.split(",") if x.strip()]
        else:
            host_items = _default_192_168_candidates()
    elif isinstance(hosts, str):
        host_items = [x.strip() for x in hosts.split(",") if x.strip()]
    else:
        host_items = [str(x).strip() for x in hosts if str(x).strip()]

    selected: list[str] = []
    for item in host_items:
        for ip in _expand_host_item(item, max_hosts=max_hosts - len(selected)):
            if ip not in selected:
                selected.append(ip)
            if len(selected) >= max_hosts:
                return selected
    return selected


def _default_192_168_candidates() -> list[str]:
    candidates: list[str] = []
    for third in _DEFAULT_CANDIDATE_THIRD_OCTETS:
        for last in _DEFAULT_CANDIDATE_LAST_OCTETS:
            candidates.append(f"192.168.{third}.{last}")
    return candidates


def _expand_host_item(item: str, max_hosts: int) -> list[str]:
    if max_hosts <= 0:
        return []
    try:
        if "/" in item:
            net = ipaddress.ip_network(item, strict=False)
            if not net.subnet_of(_ALLOWED_192_168):
                return []
            return [str(ip) for ip in net.hosts()][:max_hosts]
        ip = ipaddress.ip_address(item)
        if ip in _ALLOWED_192_168:
            return [str(ip)]
    except ValueError:
        return []
    return []


def _tcp_connect(host: str, port: int, timeout: float) -> dict[str, Any]:
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {
                "host": host,
                "port": port,
                "reachable": True,
                "latency_ms": elapsed_ms,
            }
    except OSError as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "host": host,
            "port": port,
            "reachable": False,
            "latency_ms": elapsed_ms,
            "error": exc.__class__.__name__,
        }


def check_192_168_connectivity(
    hosts: list[str] | str | None = None,
    ports: list[int] | str | None = None,
    timeout_sec: float | None = None,
    max_hosts: int | None = None,
) -> dict[str, Any]:
    """Check bounded TCP reachability to 192.168.0.0/16 addresses."""
    if not _enabled():
        return {
            "enabled": False,
            "message": "Set ENABLE_SAFE_NET_CHECKS=1 to allow bounded 192.168.0.0/16 TCP checks.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    if timeout_sec is None:
        timeout_sec = float(os.environ.get("NET_CHECK_TIMEOUT_SEC", "0.7"))
    timeout_sec = min(max(float(timeout_sec), 0.1), 3.0)

    if max_hosts is None:
        max_hosts = int(os.environ.get("NET_CHECK_MAX_HOSTS", "32"))
    max_hosts = min(max(int(max_hosts), 1), _MAX_HOSTS_HARD_LIMIT)

    selected_hosts = _parse_hosts(hosts, max_hosts=max_hosts)
    selected_ports = _parse_ports(ports)

    results: list[dict[str, Any]] = []
    for host in selected_hosts:
        for port in selected_ports:
            results.append(_tcp_connect(host, port, timeout=timeout_sec))

    reachable = [row for row in results if row.get("reachable")]
    reachable_hosts = sorted({row["host"] for row in reachable})

    return {
        "enabled": True,
        "mode": "bounded_tcp_connect",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "allowed_cidr": str(_ALLOWED_192_168),
        "hosts_checked": selected_hosts,
        "ports_checked": selected_ports,
        "timeout_sec": timeout_sec,
        "max_hosts": max_hosts,
        "summary": {
            "target_count": len(selected_hosts),
            "probe_count": len(results),
            "reachable_count": len(reachable),
            "reachable_hosts": reachable_hosts,
            "any_reachable": bool(reachable),
        },
        "results": results,
    }
