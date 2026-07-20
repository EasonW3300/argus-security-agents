from __future__ import annotations

from datetime import datetime, timezone


def make_event(tool_name, params, response, execution_status):
    return {
        "tool_name": tool_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "execution_status": execution_status,
        "params": params,
        "response": response,
    }


def status_from_response(response):
    if response.get("status") == "success":
        return "executed"
    mapping = {
        "PERMISSION_DENIED": "permission_denied",
        "TIMEOUT": "timeout",
        "SERVICE_UNAVAILABLE": "service_unavailable",
        "INVALID_PARAMS": "invalid_params",
    }
    return mapping.get(response.get("error_code"), "failed")
