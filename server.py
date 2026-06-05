#!/usr/bin/env python3
"""
Streamable HTTP MCP 서버 + 컨테이너→노드 이스케이프 진단.

- MCP (streamablehttp): http://<host>:${PORT}/mcp (KServe 기본 PORT=8000)
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
from starlette.routing import Mount, Route

from probe.monitoring_hints import monitoring_info
from probe.run_probe import build_safe_verification_report, load_latest_report, save_report

SERVICE_NAME = os.environ.get("MCP_SERVER_NAME", "csap-node-escape-probe")
SERVICE_VERSION = os.environ.get("MCP_SERVER_VERSION", "2.1.1-git")

mcp = FastMCP(
    SERVICE_NAME,
    json_response=True,
    instructions=(
        "CSAP 점검용 MCP 서버입니다. "
        "echo/add/server_info 로 연결을 확인하고, "
        "run_escape_probe 로 컨테이너→노드 이스케이프 표면을 진단하세요. "
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
        "modes": ["mcp", "escape_probe"],
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


async def health(_request: Request) -> JSONResponse:
    latest = load_latest_report()
    return JSONResponse(
        {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
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


async def rest_probe_latest(_request: Request) -> JSONResponse:
    report = load_latest_report()
    if report is None:
        return JSONResponse({"error": "no report; POST /probe/run or call MCP tool run_escape_probe"}, status_code=404)
    return JSONResponse(report)


async def rest_manual(_request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        "Register with port 8000 (KServe kserve-mcpserver), path /mcp. "
        "MCP tools: echo, add, server_info, run_escape_probe, run_safe_verification, "
        "monitoring_checklist. POST /probe/safe-verify = read-only checks only. "
        "Monitoring: GET /monitoring/hints — see GIT_BUILD.md / 24_istio_inference_service_monitoring.md"
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
        Route("/probe/latest", rest_probe_latest, methods=["GET"]),
        Route("/probe/manual", rest_manual, methods=["GET"]),
        Route("/monitoring/hints", rest_monitoring_hints, methods=["GET"]),
        Mount("/mcp", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
