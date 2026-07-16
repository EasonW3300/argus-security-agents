from __future__ import annotations

from typing import Any, Dict, List, Tuple

from prompt_builder import build_judge_messages
from schemas import HallucinationResult, LLMCallResult, QualityScore


DIMENSIONS = (
    "severity_rationality",
    "remediation_actionability",
    "evidence_completeness",
)


def run_model_graders(
    judge_client: Any,
    test_case: dict,
    agent_output: dict,
    call_sink: List[LLMCallResult] = None,
) -> Tuple[Dict[str, QualityScore], HallucinationResult, List[LLMCallResult]]:
    scores = {}
    calls = []

    for dimension in DIMENSIONS:
        call = judge_client.generate_json(
            build_judge_messages(test_case, agent_output, dimension),
            QualityScore,
            dimension,
        )
        calls.append(call)
        if call_sink is not None:
            call_sink.append(call)
        scores[dimension] = QualityScore.model_validate(call.parsed)

    call = judge_client.generate_json(
        build_judge_messages(test_case, agent_output, "hallucination_check"),
        HallucinationResult,
        "hallucination_check",
    )
    calls.append(call)
    if call_sink is not None:
        call_sink.append(call)
    hallucination = HallucinationResult.model_validate(call.parsed)
    return scores, hallucination, calls
