"""LLM-based quality graders for Scenario 4 security briefings."""
from __future__ import annotations

import json


DIMENSIONS = ("language_quality", "insight_quality")


def build_judge_messages(case, final_output, dimension):
    grader = next(
        (item for item in case.get("graders", []) if item.get("type") == "model" and item.get("check") == dimension),
        {},
    )
    payload = {
        "dimension": dimension,
        "rubric": grader.get("rubric", "Score the supplied security briefing."),
        "target_audience": case.get("target_audience"),
        "briefing": final_output,
        "response_contract": {"score": "integer 1-5 or null when uncertain", "reason": "concise explanation", "errors": "list of strings"},
    }
    return [
        {"role": "system", "content": "You are an impartial security-briefing evaluator. Return one JSON object only."},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def run_model_graders(client, case, final_output, call_sink=None):
    """Return score records without converting a low score into an execution error."""
    scores = {}
    for dimension in DIMENSIONS:
        call = client.generate_json(build_judge_messages(case, final_output, dimension), "judge:" + dimension)
        if call_sink is not None:
            call_sink.append(call)
        parsed = call.parsed if isinstance(getattr(call, "parsed", None), dict) else {}
        score = parsed.get("score")
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
            score = None
        scores[dimension] = {
            "score": score,
            "reason": str(parsed.get("reason", "")),
            "errors": parsed.get("errors", []) if isinstance(parsed.get("errors"), list) else [],
        }
    return scores
