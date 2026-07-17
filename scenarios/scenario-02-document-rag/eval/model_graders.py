from __future__ import annotations

from prompt_builder import build_judge_messages
from schemas import JudgeScore


DIMENSIONS = ("faithfulness", "coverage", "compliance_accuracy")


def run_model_graders(judge_client, test_case, agent_output, call_sink=None):
    scores = {}
    calls = []
    for dimension in DIMENSIONS:
        call = judge_client.generate_json(
            build_judge_messages(test_case, agent_output, dimension),
            JudgeScore,
            dimension,
        )
        calls.append(call)
        if call_sink is not None:
            call_sink.append(call)
        scores[dimension] = JudgeScore.model_validate(call.parsed)
    return scores, calls

