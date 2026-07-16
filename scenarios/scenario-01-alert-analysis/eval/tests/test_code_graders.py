import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from code_graders import run_code_graders


CASE = {
    "expected_severity": "critical",
    "ground_truth": {
        "expected_tools_minimum": [
            "query_alert_detail",
            "query_threat_intel",
        ]
    },
}

OUTPUT = {
    "alert_id": "A01",
    "judgment": {
        "severity": "critical",
        "attack_type": "brute_force",
        "confidence": 0.9,
        "summary": "x",
        "evidence_chain": [],
        "iocs": [],
    },
    "remediation": ["立即隔离目标主机并完成取证分析"],
    "metadata": {
        "tools_called": [
            "query_alert_detail",
            "query_threat_intel",
        ]
    },
}

GRADER_NAMES = {
    "tools_called_minimum",
    "output_schema",
    "severity_enum",
    "severity_match",
    "confidence_range",
    "remediation_not_empty",
}


class CodeGradersTest(unittest.TestCase):
    def test_all_six_pass(self):
        results = run_code_graders(OUTPUT, CASE)

        self.assertEqual(len(results), 6)
        self.assertTrue(all(result.passed for result in results.values()))

    def test_severity_match_is_independent(self):
        output = {
            **OUTPUT,
            "judgment": {**OUTPUT["judgment"], "severity": "high"},
        }

        results = run_code_graders(output, CASE)

        self.assertTrue(results["severity_enum"].passed)
        self.assertFalse(results["severity_match"].passed)

    def test_missing_output_returns_six_failures(self):
        results = run_code_graders({}, {})

        self.assertEqual(set(results), GRADER_NAMES)
        self.assertTrue(all(not result.passed for result in results.values()))
        self.assertFalse(results["severity_match"].passed)

    def test_matching_unknown_severity_is_independent_from_enum(self):
        output = {
            **OUTPUT,
            "judgment": {**OUTPUT["judgment"], "severity": "unknown"},
        }
        case = {**CASE, "expected_severity": "unknown"}

        results = run_code_graders(output, case)

        self.assertFalse(results["severity_enum"].passed)
        self.assertTrue(results["severity_match"].passed)

    def test_malformed_output_returns_six_results_without_raising(self):
        results = run_code_graders(
            {"judgment": None, "metadata": "invalid", "remediation": {}},
            {"expected_severity": "critical", "ground_truth": None},
        )

        self.assertEqual(len(results), 6)
        self.assertFalse(all(result.passed for result in results.values()))

    def test_boolean_confidence_is_not_a_number(self):
        for confidence in (True, False):
            with self.subTest(confidence=confidence):
                output = {
                    **OUTPUT,
                    "judgment": {
                        **OUTPUT["judgment"],
                        "confidence": confidence,
                    },
                }

                results = run_code_graders(output, CASE)

                self.assertFalse(results["confidence_range"].passed)

    def test_unhashable_severity_returns_six_results_without_raising(self):
        output = {
            **OUTPUT,
            "judgment": {**OUTPUT["judgment"], "severity": ["critical"]},
        }

        results = run_code_graders(output, CASE)

        self.assertEqual(len(results), 6)
        self.assertFalse(results["severity_enum"].passed)
        self.assertFalse(results["severity_match"].passed)


if __name__ == "__main__":
    unittest.main()
