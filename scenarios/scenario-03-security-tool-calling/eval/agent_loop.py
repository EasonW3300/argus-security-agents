from __future__ import annotations

from code_graders import run_code_graders
from mock_tool_server import MockToolServer
from prompt_builder import build_agent_messages
from schemas import LLMCallResult
from tool_registry import ToolRegistry
from transcript import make_event, status_from_response


def _permission_error(role, tool):
    return {"status": "error", "error_code": "PERMISSION_DENIED", "error_message": "%s 无权执行 %s" % (role, tool)}


def run_agent_case(case, client, max_turns=12):
    registry = ToolRegistry(case)
    server = MockToolServer(case)
    transcript = []
    calls = []
    messages = build_agent_messages(case, transcript)
    final_output = None
    error = None
    for _ in range(max_turns):
        call = client.generate_json(messages, "agent")
        calls.append(call)
        payload = call.parsed if isinstance(call.parsed, dict) else {}
        if payload.get("type") == "final":
            final_output = payload.get("output")
            break
        if payload.get("type") != "tool_call" or not isinstance(payload.get("tool_name"), str) or not isinstance(payload.get("params"), dict):
            error = "invalid model turn"
            break
        tool_name = payload["tool_name"]
        params = payload["params"]
        if not registry.has(tool_name):
            response = {"status": "error", "error_code": "INVALID_TOOL", "error_message": "unknown tool"}
            status = "invalid_params"
        elif not registry.allowed(case.get("user_role"), tool_name):
            response = _permission_error(case.get("user_role"), tool_name)
            status = "permission_denied"
        else:
            response = server.execute(tool_name, params)
            status = status_from_response(response)
        event = make_event(tool_name, params, response, status)
        transcript.append(event)
        messages = build_agent_messages(case, transcript)
    if final_output is None and error is None:
        error = "max_turns exceeded"
    if not isinstance(final_output, dict):
        final_output = {"summary": error or "未生成最终结果", "tools_called": [e["tool_name"] for e in transcript], "actions_taken": []}
    return {"final_output": final_output, "transcript": transcript, "calls": calls, "error": error}
