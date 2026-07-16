import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_graders import DIMENSIONS, run_model_graders
from prompt_builder import build_judge_messages
from schemas import HallucinationResult, LLMCallResult, QualityScore


TEST_CASE = {"mock_api_responses": {"query_alert_detail": {"id": "A01"}}}
AGENT_OUTPUT = {"judgment": {"evidence_chain": ["证据"]}}


def make_call(label, parsed):
    return LLMCallResult(
        label=label,
        parsed=parsed,
        raw_text="{}",
        provider="fake",
        model="fake-model",
        response_mode="json_object",
        latency_ms=1,
        attempts=1,
    )


class FakeJudge:
    def __init__(self):
        self.requests = []
        self.results = []

    def generate_json(self, messages, schema, label):
        self.requests.append((messages, schema, label))
        if label == "hallucination_check":
            parsed = {
                "total_statements": 1,
                "verifiable": 1,
                "hallucinations": 0,
                "uncertain": 0,
                "details": [
                    {
                        "statement": "证据",
                        "verdict": "verifiable",
                        "reason": "输入可追溯",
                    }
                ],
            }
        else:
            parsed = {
                "score": None if label == "evidence_completeness" else 4,
                "reason": "依据充分",
                "evidence_quotes": ["证据"],
            }
        result = make_call(label, parsed)
        self.results.append(result)
        return result


class ModelGradersTest(unittest.TestCase):
    def test_runs_each_dimension_then_hallucination_with_expected_contract(self):
        judge = FakeJudge()

        scores, hallucination, calls = run_model_graders(
            judge, TEST_CASE, AGENT_OUTPUT
        )

        expected_labels = list(DIMENSIONS) + ["hallucination_check"]
        self.assertEqual(
            DIMENSIONS,
            (
                "severity_rationality",
                "remediation_actionability",
                "evidence_completeness",
            ),
        )
        self.assertEqual(
            [request[2] for request in judge.requests], expected_labels
        )
        self.assertEqual(
            [request[1] for request in judge.requests],
            [QualityScore, QualityScore, QualityScore, HallucinationResult],
        )
        self.assertEqual(
            [request[0] for request in judge.requests],
            [
                build_judge_messages(TEST_CASE, AGENT_OUTPUT, label)
                for label in expected_labels
            ],
        )
        self.assertEqual(list(scores), list(DIMENSIONS))
        self.assertTrue(
            all(isinstance(score, QualityScore) for score in scores.values())
        )
        self.assertIsInstance(hallucination, HallucinationResult)
        self.assertEqual(hallucination.ratio(), 0)
        self.assertEqual(len(calls), 4)
        self.assertTrue(
            all(actual is expected for actual, expected in zip(calls, judge.results))
        )

    def test_preserves_uncertain_quality_score(self):
        scores, _, _ = run_model_graders(FakeJudge(), TEST_CASE, AGENT_OUTPUT)

        self.assertIsNone(scores["evidence_completeness"].score)

    def test_external_call_sink_keeps_successes_before_later_failure(self):
        class FailingSecondJudge(FakeJudge):
            def generate_json(self, messages, schema, label):
                if len(self.requests) == 1:
                    raise RuntimeError("second judge failed")
                return super().generate_json(messages, schema, label)

        judge = FailingSecondJudge()
        sink = []

        with self.assertRaisesRegex(RuntimeError, "second judge failed"):
            run_model_graders(judge, TEST_CASE, AGENT_OUTPUT, call_sink=sink)

        self.assertEqual([item.label for item in sink], ["severity_rationality"])


if __name__ == "__main__":
    unittest.main()
