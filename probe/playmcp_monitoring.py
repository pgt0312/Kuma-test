"""PlayMCP 모니터링 탭(InferenceService / Istio) 점검용 메타 — 비밀 없음."""
from __future__ import annotations

import os
import socket
from typing import Any


def playmcp_monitoring_info() -> dict[str, Any]:
    mcp_name = os.environ.get("MCP_SERVER_NAME", "")
    ns = os.environ.get("POD_NAMESPACE", "")
    return {
        "mcp_server_name_for_isvc": mcp_name,
        "hint": (
            "PlayMCP monitoring expects a Kubeflow/KServe InferenceService with "
            "metadata.name == MCP registration name (endpoint_name). "
            "Plain Deployment-only workloads do not populate the Istio metrics chart."
        ),
        "kserve_runtime": {
            "cluster_serving_runtime": "kserve-mcpserver",
            "container_port": 8000,
            "readiness": "tcpSocket on user-port (not HTTP /health)",
            "env_port": "PORT=8000 injected by platform",
        },
        "common_ui_error": (
            "클러스터에 해당 InferenceService가 없습니다. "
            "Istio 메트릭 라벨을 확인할 수 없습니다."
        ),
        "checks": [
            f"kubectl get inferenceservice -n {ns or '<ns>'} {mcp_name or '<mcp-name>'}",
            "If missing: scripts/apply-inferenceservice-for-playmcp.sh (see PLAYMCP_GIT_BUILD.md)",
            "Confirm PlayMCP detail API endpoint_name matches InferenceService name",
            "GET /api/v2/mcp/my-mcp-servers/{id}/istio-traffic?range=1h",
            "Generate Playground traffic then re-open monitoring tab",
        ],
        "fix_script": "scripts/apply-inferenceservice-for-playmcp.sh",
        "fix_example": (
            "MCP_NAME=csap-node-escape-probe NS=<ns> IMAGE=<playmcp-image> "
            "./scripts/apply-inferenceservice-for-playmcp.sh"
        ),
        "doc": "playmcp/24_playmcp_istio_inference_service.md",
        "runtime": {
            "hostname": socket.gethostname(),
            "pod_name": os.environ.get("POD_NAME", ""),
            "pod_namespace": ns,
            "node_name": os.environ.get("NODE_NAME", ""),
        },
    }
