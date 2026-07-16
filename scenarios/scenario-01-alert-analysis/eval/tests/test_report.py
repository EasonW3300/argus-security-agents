import csv
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import PricingConfig
from report import atomic_write_json, summarize, write_reports
from schemas import CaseResult


CODE_CHECKS = (
    "tools_called_minimum",
    "output_schema",
    "severity_enum",
    "severity_match",
    "confidence_range",
    "remediation_not_empty",
)


def case_row(
    case_id="A01",
    expected="critical",
    actual="critical",
    match=True,
    latency_ms=10,
    quality_scores=None,
    status="completed",
):
    graders = {
        name: {"passed": match if name == "severity_match" else True, "reason": "r"}
        for name in CODE_CHECKS
    }
    if quality_scores is None:
        quality_scores = {
            "severity_rationality": {
                "score": 4,
                "reason": "r",
                "evidence_quotes": [],
            },
            "remediation_actionability": {
                "score": 4,
                "reason": "r",
                "evidence_quotes": [],
            },
            "evidence_completeness": {
                "score": 4,
                "reason": "r",
                "evidence_quotes": [],
            },
        }
    return {
        "test_case_id": case_id,
        "scenario": "中文场景",
        "difficulty": "easy",
        "is_positive": expected != "false_positive",
        "expected_severity": expected,
        "status": status,
        "agent_output": (
            {
                "alert_id": case_id,
                "judgment": {
                    "severity": actual,
                    "attack_type": "none" if actual == "false_positive" else "x",
                    "confidence": 0.8,
                    "summary": "摘要",
                    "evidence_chain": [],
                    "iocs": [],
                },
                "remediation": ["处置"],
                "metadata": {"tools_called": []},
            }
            if status == "completed"
            else None
        ),
        "code_graders": graders if status == "completed" else {},
        "quality_scores": quality_scores if status == "completed" else None,
        "hallucination": (
            {
                "total_statements": 2,
                "verifiable": 1,
                "hallucinations": 1,
                "uncertain": 0,
                "details": [],
            }
            if status == "completed" and quality_scores is not None
            else None
        ),
        "calls": [
            {
                "label": "agent",
                "parsed": {},
                "raw_text": "{}",
                "provider": "fake-agent",
                "model": "agent-model",
                "response_mode": "json_object",
                "input_tokens": 100,
                "output_tokens": 20,
                "latency_ms": latency_ms,
                "attempts": 1,
            },
            {
                "label": "severity_rationality",
                "parsed": {},
                "raw_text": "{}",
                "provider": "fake-judge",
                "model": "judge-model",
                "response_mode": "json_object",
                "input_tokens": 50,
                "output_tokens": 10,
                "latency_ms": 5,
                "attempts": 1,
            },
        ],
        "overall_pass": True if status == "completed" else "not_evaluated",
        "error_type": "RuntimeError" if status == "error" else None,
        "error_message": "失败" if status == "error" else None,
    }


class ReportTest(unittest.TestCase):
    def test_summary_uses_severity_match_and_false_positive_formula(self):
        results = [
            case_row("A01", "critical", "critical", False),
            case_row("A02", "false_positive", "critical", True),
            case_row("A03", "false_positive", "false_positive", True),
        ]

        summary = summarize(results)

        self.assertEqual(summary["severity_accuracy"], 2 / 3)
        self.assertEqual(summary["false_positive_recall"], 0.5)

    def test_six_grader_rates_and_overall_case_pass_rate(self):
        first = case_row("A01")
        second = case_row("A02")
        second["code_graders"]["confidence_range"]["passed"] = False

        summary = summarize([first, second])

        self.assertEqual(summary["code_grader_pass_rates"]["confidence_range"], 0.5)
        self.assertEqual(summary["code_grader_pass_rates"]["severity_enum"], 1.0)
        self.assertEqual(summary["code_grader_overall_pass_rate"], 0.5)

    def test_quality_average_requires_all_dimensions_and_counts_uncertain(self):
        missing = case_row("A01")
        missing["quality_scores"]["evidence_completeness"]["score"] = None
        complete = case_row("A02")
        complete["quality_scores"]["severity_rationality"]["score"] = 2

        summary = summarize([missing, complete])

        self.assertIsNone(summary["case_rows"][0]["quality_average"])
        self.assertEqual(summary["case_rows"][1]["quality_average"], 10 / 3)
        self.assertEqual(summary["quality_averages"]["severity_rationality"], 3.0)
        self.assertEqual(summary["judge_uncertain_count"], 1)

    def test_nearest_rank_p95_latency_tokens_hallucinations_and_cost(self):
        results = [case_row("A%02d" % index, latency_ms=index) for index in range(1, 21)]
        pricing = PricingConfig(
            agent_input_per_1m=1,
            agent_output_per_1m=2,
            judge_input_per_1m=3,
            judge_output_per_1m=4,
        )

        summary = summarize(results, pricing)

        self.assertEqual(summary["average_latency_ms"], 15.5)
        self.assertEqual(summary["p95_latency_ms"], 24)
        self.assertEqual(summary["input_tokens"], 3000)
        self.assertEqual(summary["output_tokens"], 600)
        self.assertEqual(summary["hallucination_ratio"], 0.5)
        self.assertTrue(math.isclose(summary["estimated_cost_usd"], 0.0066))

    def test_any_required_price_missing_makes_cost_none(self):
        pricing = PricingConfig(
            agent_input_per_1m=1,
            agent_output_per_1m=2,
            judge_input_per_1m=3,
        )

        summary = summarize([case_row()], pricing)

        self.assertIsNone(summary["estimated_cost_usd"])
        self.assertIsNone(summary["case_rows"][0]["estimated_cost_usd"])

    def test_accepts_pydantic_case_results_and_preserves_overall_pass(self):
        value = CaseResult.model_validate(case_row())

        summary = summarize([value])

        self.assertEqual(summary["case_rows"][0]["test_case_id"], "A01")
        self.assertIs(summary["case_rows"][0]["overall_pass"], True)

    def test_zero_cases_error_case_and_missing_judge_data_do_not_crash(self):
        empty = summarize([])
        error = case_row("A99", status="error")
        missing_judge = case_row("A98")
        missing_judge["quality_scores"] = None
        missing_judge["hallucination"] = None

        summary = summarize([error, missing_judge])

        self.assertEqual(empty["total"], 0)
        self.assertIsNone(empty["severity_accuracy"])
        self.assertEqual(summary["completed"], 1)
        self.assertIsNone(summary["case_rows"][0]["actual_severity"])
        self.assertIsNone(summary["case_rows"][1]["quality_average"])

    def test_write_reports_keeps_json_and_csv_case_rows_consistent_utf8(self):
        results = [case_row("A01"), CaseResult.model_validate(case_row("A02"))]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "nested"
            write_reports(run_dir, {"run_id": "中文运行"}, results)
            payload = json.loads(
                (run_dir / "eval_results.json").read_text(encoding="utf-8")
            )
            with (run_dir / "eval_summary.csv").open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                csv_rows = list(csv.DictReader(handle))

        self.assertEqual(payload["manifest"]["run_id"], "中文运行")
        self.assertEqual(len(payload["results"]), len(csv_rows))
        self.assertEqual(
            [row["test_case_id"] for row in payload["results"]],
            [row["test_case_id"] for row in csv_rows],
        )
        self.assertEqual(csv_rows[0]["scenario"], "中文场景")
        self.assertIn("hallucination_ratio", csv_rows[0])
        self.assertIn("quality_average", csv_rows[0])

    def test_atomic_write_json_uses_replace_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            real_replace = os.replace
            replacements = []

            def recording_replace(source, destination):
                replacements.append((Path(source), Path(destination)))
                real_replace(source, destination)

            with patch("report.os.replace", side_effect=recording_replace):
                atomic_write_json(path, {"value": "中文"})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"value": "中文"})
            self.assertEqual(len(replacements), 1)
            self.assertEqual(replacements[0][1], path)
            self.assertFalse(replacements[0][0].exists())

    def test_atomic_write_json_rejects_nan_without_creating_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"

            with self.assertRaises(ValueError):
                atomic_write_json(path, {"value": math.nan})

            self.assertFalse(path.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_atomic_write_json_rejects_nan_without_damaging_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            path.write_text('{"original": true}\n', encoding="utf-8")

            with self.assertRaises(ValueError):
                atomic_write_json(path, {"value": math.nan})

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")), {"original": True}
            )
            self.assertEqual(list(Path(tmp).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
