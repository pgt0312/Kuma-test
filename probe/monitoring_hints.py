"""모니터링 탭(InferenceService / Istio) 점검용 메타 — 비밀 없음."""
from __future__ import annotations

import os
import socket
from typing import Any


def _listen_port() -> int:
    for key in ("PORT", "KMP_PORT"):
        val = os.environ.get(key, "").strip()
        if val.isdigit():
            return int(val)
    return 8080


def monitoring_info() -> dict[str, Any]:
    mcp_name = os.environ.get("MCP_SERVER_NAME", "")
    ns = os.environ.get("POD_NAMESPACE", "")
    port = _listen_port()
    return {
        "mcp_server_name_for_isvc": mcp_name,
        "hint": (
            "Hosting UI monitoring expects a Kubeflow/KServe InferenceService with "
            "metadata.name == MCP registration name (endpoint_name). "
            "Plain Deployment-only workloads do not populate the Istio metrics chart."
        ),
        "kserve_runtime": {
            "cluster_serving_runtime": "kserve-mcpserver",
            "container_port": port,
            "readiness": "tcpSocket on user-port (must match PORT env listen port)",
            "env_port": "PORT injected by platform — do not hardcode in image Dockerfile",
        },
        "revision_failed_hint": (
            "RevisionFailed / Initial scale was never achieved: "
            "Pod logs listen port must match platform PORT (8080 or 8000). "
            "Image must not bake ENV PORT in Dockerfile — see HOSTING.md."
        ),
        "hosting_doc": "HOSTING.md",
        "common_ui_error": (
            "클러스터에 해당 InferenceService가 없습니다. "
            "Istio 메트릭 라벨을 확인할 수 없습니다."
        ),
        "checks": [
            f"kubectl get inferenceservice -n {ns or '<ns>'} {mcp_name or '<mcp-name>'}",
            "kubectl get clusterservingruntime kserve-mcpserver -o yaml | grep -E containerPort|PORT",
            f"Pod logs: Streamable HTTP MCP at http://0.0.0.0:{port}/mcp",
            "If missing IS: scripts/apply-inferenceservice.sh (see HOSTING.md)",
            "GET /api/v2/mcp/my-mcp-servers/{id}/istio-traffic?range=1h",
            "Generate Playground traffic then re-open monitoring tab",
        ],
        "fix_script": "scripts/apply-inferenceservice.sh",
        "fix_example": (
            "MCP_NAME=csap-node-escape-probe NS=<ns> IMAGE=<built-image> "
            "./scripts/apply-inferenceservice.sh"
        ),
        "doc": "24_istio_inference_service_monitoring.md",
        "runtime": {
            "hostname": socket.gethostname(),
            "pod_name": os.environ.get("POD_NAME", ""),
            "pod_namespace": ns,
            "node_name": os.environ.get("NODE_NAME", ""),
            "listen_port": port,
        },
    }
