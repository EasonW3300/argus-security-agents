from __future__ import annotations

from prompt_builder import build_judge_messages
from schemas import LLMCallResult


DIMENSIONS = ("orchestration_quality", "safety_check")


def run_model_graders(client, case, final_output, transcript, call_sink=None):
    scores = {}
    for dimension in DIMENSIONS:
        call = client.generate_json(build_judge_messages(case, final_output, transcript, dimension), "judge:" + dimension)
        if call_sink is not None:
            call_sink.append(call)
        parsed = call.parsed if isinstance(call.parsed, dict) else {}
        score = parsed.get("score")
        if not isinstance(score, int) or not 1 <= score <= 5:
            score = None
        scores[dimension] = {
            "score": score,
            "reason": str(parsed.get("reason", "")),
            "errors": parsed.get("errors", []) if isinstance(parsed.get("errors", []), list) else [],
        }
    return scores
