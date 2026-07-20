from __future__ import annotations

import json

from code_graders import _branch
from mock_tool_server import MockToolServer
from transcript import make_event, status_from_response


def _matches(params, check):
    for key, expected in (check or {}).items():
        if key.endswith("_must_contain"):
            base = key[:-13]
            value = params.get(base)
            if not isinstance(value, (str, list)) or not all(str(item) in value for item in expected):
                return False
        elif key.endswith("_must_be"):
            if params.get(key[:-8]) != expected:
                return False
        elif params.get(key) != expected:
            return False
    return True


def _find_params(case, step, used):
    tool = step.get("tool")
    check = step.get("params_check") or {}
    for index, item in enumerate((case.get("mock_tool_responses") or {}).values()):
        if index not in used and item.get("tool") == tool and _matches(item.get("params") or {}, check):
            used.add(index)
            return item.get("params") or {}
    return {}


def _summary(case, branch=None):
    gt = case.get("ground_truth") or {}
    values = list(gt.get("expected_output_must_include") or [])
    if branch:
        values.extend(branch.get("expected_output_must_include") or [])
    return "；".join(dict.fromkeys(values)) or "已完成请求。"


def run_mock_case(case):
    gt = case.get("ground_truth") or {}
    server = MockToolServer(case)
    transcript = []
    used = set()
    steps = list(gt.get("expected_tool_sequence") or [])
    if case.get("is_positive", True):
        for step in steps:
            params = _find_params(case, step, used)
            response = server.execute(step["tool"], params)
            transcript.append(make_event(step["tool"], params, response, status_from_response(response)))
        branch, count = _branch(case, transcript)
        if branch and count == 1:
            for step in branch.get("expected_tool_sequence") or []:
                params = _find_params(case, step, used)
                response = server.execute(step["tool"], params)
                transcript.append(make_event(step["tool"], params, response, status_from_response(response)))
        branch_id = branch.get("branch_id") if branch and count == 1 else None
    else:
        branch_id = None

    final = {
        "summary": _summary(case, branch if 'branch' in locals() and branch_id else None),
        "tools_called": [event["tool_name"] for event in transcript],
        "actions_taken": [
            {"tool_name": event["tool_name"], "status": event["response"].get("status"), "key_result": event["response"].get("data", event["response"].get("error_code"))}
            for event in transcript
            if event["execution_status"] == "executed"
        ],
    }
    return {
        "status": "completed",
        "final_output": final,
        "transcript": transcript,
        "tools_called": final["tools_called"],
        "branch_id": branch_id,
    }


def generate_mock_turn(case, transcript, planned):
    """Return a JSON-protocol turn for optional manual Agent-loop tests."""
    if planned:
        item = planned[0]
        return {"type": "tool_call", "tool_name": item["tool"], "params": item.get("params", {})}
    return {"type": "final", "output": {"summary": "已完成请求。", "tools_called": [], "actions_taken": []}}
