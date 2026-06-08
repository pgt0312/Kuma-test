#!/usr/bin/env python3
"""
Streamable HTTP MCP 서버 + 컨테이너→노드 이스케이프 진단.

- MCP (streamablehttp): http://<host>:${PORT}/mcp (KServe kserve-mcpserver 가 PORT 주입, 보통 8080)
- 헬스: GET /health, /healthz
- REST (호환): GET /probe/latest, POST /probe/run
"""
from __future__ import annotations

import contextlib
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from probe.monitoring_hints import monitoring_info
from probe.network_checks import check_192_168_connectivity as run_192_168_connectivity_check
from probe.run_probe import build_safe_verification_report, load_latest_report, save_report

SERVICE_NAME = os.environ.get("MCP_SERVER_NAME", "csap-node-escape-probe")
SERVICE_VERSION = os.environ.get("MCP_SERVER_VERSION", "2.3.0-network")

mcp = FastMCP(
    SERVICE_NAME,
    json_response=True,
    instructions=(
        "CSAP 점검용 MCP 서버입니다. "
        "echo/add/server_info 로 연결을 확인하고, "
        "run_escape_probe 로 컨테이너→노드 이스케이프 표면을 진단하세요. "
        "check_192_168_connectivity 로 승인된 사설망 TCP 도달성을 확인할 수 있습니다. "
        "자동 익스플로잇은 수행하지 않습니다."
    ),
)


@mcp.tool()
def echo(message: str) -> str:
    """연결·지연 테스트용 에코."""
    return message


@mcp.tool()
def add(a: float, b: float) -> float:
    """간단 연산 smoke test."""
    return a + b


@mcp.tool()
def server_info() -> dict[str, Any]:
    """서비스·런타임 메타 (비밀값 없음)."""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "env_profile": os.environ.get("ENV_PROFILE", "test"),
        "transport": "streamable-http",
        "mcp_path": "/mcp",
        "modes": ["mcp", "escape_probe", "bounded_network_check"],
        "monitoring_hints": monitoring_info(),
    }


@mcp.tool()
def monitoring_checklist() -> dict[str, Any]:
    """모니터링(InferenceService/Istio) 실패 시 점검 체크리스트."""
    return monitoring_info()


@mcp.tool()
def run_escape_probe() -> dict[str, Any]:
    """컨테이너 이스케이프 위험 지표를 수집해 JSON으로 반환합니다 (저장 포함)."""
    return save_report()


@mcp.tool()
def run_safe_verification() -> dict[str, Any]:
    """읽기 전용 강화·설정 검증만 수행 (이스케이프 전체 스캔 생략, 서비스 부하 최소)."""
    return build_safe_verification_report()


@mcp.tool()
def check_192_168_connectivity(
    hosts: str | None = None,
    ports: str | None = None,
    timeout_sec: float | None = None,
    max_hosts: int | None = None,
) -> dict[str, Any]:
    """ENABLE_SAFE_NET_CHECKS=1 일 때만 192.168.0.0/16 TCP 도달성을 제한적으로 확인."""
    return run_192_168_connectivity_check(
        hosts=hosts,
        ports=ports,
        timeout_sec=timeout_sec,
        max_hosts=max_hosts,
    )


@mcp.tool()
def get_escape_probe_summary() -> str:
    """마지막 이스케이프 프로브 요약(텍스트). 없으면 새로 실행."""
    report = load_latest_report() or save_report()
    findings = report.get("risk_findings") or []
    lines = [
        f"service={SERVICE_NAME} max_severity={report.get('summary', {}).get('max_severity')}",
        f"finding_count={report.get('summary', {}).get('finding_count')}",
    ]
    for item in findings[:12]:
        lines.append(f"- [{item.get('severity')}] {item.get('id')}: {item.get('title')}")
    return "\n".join(lines)


@mcp.tool()
def run_active_escape_checks() -> str:
    """ENABLE_ACTIVE_TESTS=1 일 때만 읽기 전용 active_checks.sh 실행."""
    if os.environ.get("ENABLE_ACTIVE_TESTS", "0") != "1":
        return (
            "ENABLE_ACTIVE_TESTS is not set. "
            "Set env ENABLE_ACTIVE_TESTS=1 on the Pod for read-only active checks."
        )
    script = "/opt/app/probe/active_checks.sh"
    if not os.path.isfile(script):
        script = "/opt/probe/active_checks.sh"
    proc = subprocess.run(
        ["/bin/sh", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def _listen_port() -> int:
    for key in ("PORT", "KMP_PORT"):
        val = os.environ.get(key, "").strip()
        if val.isdigit():
            return int(val)
    return 8080


async def health(_request: Request) -> JSONResponse:
    latest = load_latest_report()
    return JSONResponse(
        {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "listen_port": _listen_port(),
            "mcp_endpoint": "/mcp",
            "probe_ready": latest is not None,
            "probe_max_severity": (latest or {}).get("summary", {}).get("max_severity"),
        }
    )


async def rest_probe_run(_request: Request) -> JSONResponse:
    report = save_report()
    return JSONResponse(report)


async def rest_safe_verify(_request: Request) -> JSONResponse:
    return JSONResponse(build_safe_verification_report())


async def rest_192_168_check(request: Request) -> JSONResponse:
    body: dict[str, Any] = {}
    if request.method == "POST":
        try:
            parsed = await request.json()
            if isinstance(parsed, dict):
                body = parsed
        except Exception:  # noqa: BLE001
            body = {}
    return JSONResponse(
        run_192_168_connectivity_check(
            hosts=body.get("hosts"),
            ports=body.get("ports"),
            timeout_sec=body.get("timeout_sec"),
            max_hosts=body.get("max_hosts"),
        )
    )


async def rest_probe_latest(_request: Request) -> JSONResponse:
    report = load_latest_report()
    if report is None:
        return JSONResponse({"error": "no report; POST /probe/run or call MCP tool run_escape_probe"}, status_code=404)
    return JSONResponse(report)


async def rest_manual(_request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        "KServe kserve-mcpserver: use platform-injected PORT (usually 8080), path /mcp. "
        "MCP tools: echo, add, server_info, run_escape_probe, run_safe_verification, "
        "check_192_168_connectivity, monitoring_checklist. "
        "POST /probe/safe-verify = read-only checks only. "
        "POST /network/192-168/check = bounded 192.168 TCP checks. "
        "Monitoring: GET /monitoring/hints — see HOSTING.md / 24_istio_inference_service_monitoring.md"
    )


async def rest_monitoring_hints(_request: Request) -> JSONResponse:
    return JSONResponse(monitoring_info())


def _probe_on_start_background() -> None:
    try:
        save_report()
    except OSError:
        pass


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette):
    if os.environ.get("RUN_PROBE_ON_START", "0") == "1":
        import threading

        threading.Thread(target=_probe_on_start_background, daemon=True).start()
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/healthz", health, methods=["GET"]),
        Route("/probe/run", rest_probe_run, methods=["POST"]),
        Route("/probe/safe-verify", rest_safe_verify, methods=["POST", "GET"]),
        Route("/network/192-168/check", rest_192_168_check, methods=["POST", "GET"]),
        Route("/probe/latest", rest_probe_latest, methods=["GET"]),
        Route("/probe/manual", rest_manual, methods=["GET"]),
        Route("/monitoring/hints", rest_monitoring_hints, methods=["GET"]),
        *mcp.streamable_http_app().routes,
    ],
    lifespan=lifespan,
)


if __name__ == "__main__":
    import uvicorn

    port = _listen_port()
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
