from __future__ import annotations

from prompt_builder import build_agent_messages
from schemas import ReportOutput


def _serialize_call(call):
    if hasattr(call, "to_dict"):
        return call.to_dict()
    if hasattr(call, "__dict__"):
        return dict(call.__dict__)
    return call


def run_agent_case(case: dict, client) -> dict:
    """Run the single-turn report-generation protocol and retain an audit trail."""
    messages = build_agent_messages(case)
    call = client.generate_json(messages, "agent")
    payload = call.parsed if hasattr(call, "parsed") else call
    if isinstance(payload, dict) and isinstance(payload.get("final_output"), dict):
        payload = payload["final_output"]
    final_output = ReportOutput.validate(
        payload, expected_section_ids=case["ground_truth"]["expected_sections"]
    )
    transcript = [{"role": "assistant", "content": getattr(call, "raw_text", None), "parsed": final_output}]
    return {"final_output": final_output, "transcript": transcript, "calls": [_serialize_call(call)]}
