import json
import unittest
from collections import Counter
from pathlib import Path


EVAL_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = EVAL_DIR / "Eval-data_v1.json"


class EvalDataV1ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = None
        if DATA_PATH.exists():
            cls.cases = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    def require_cases(self):
        self.assertIsNotNone(
            self.cases,
            "Eval-data_v1.json must be generated before validation",
        )
        return self.cases

    def test_contains_30_unique_sequential_cases(self):
        cases = self.require_cases()
        ids = [case["test_case_id"] for case in cases]
        self.assertEqual(len(cases), 30)
        self.assertEqual(len(set(ids)), 30)
        self.assertEqual(ids, [f"A{i:02d}" for i in range(1, 31)])

    def test_top_level_ground_truth_labels_are_consistent(self):
        for case in self.require_cases():
            with self.subTest(test_case_id=case["test_case_id"]):
                expected = case["ground_truth"]["expected_judgment"]
                self.assertEqual(case["expected_severity"], expected["severity"])
                self.assertEqual(case["expected_attack_type"], expected["attack_type"])

    def test_false_positive_cases_use_none_attack_type(self):
        false_positives = [
            case
            for case in self.require_cases()
            if case["expected_severity"] == "false_positive"
        ]
        self.assertEqual(len(false_positives), 8)
        for case in false_positives:
            with self.subTest(test_case_id=case["test_case_id"]):
                self.assertFalse(case["is_positive"])
                self.assertEqual(case["expected_attack_type"], "none")
                self.assertEqual(
                    case["ground_truth"]["expected_judgment"]["attack_type"],
                    "none",
                )

    def test_a01_is_critical(self):
        case = self.case_by_id("A01")
        self.assertEqual(case["expected_severity"], "critical")
        self.assertEqual(
            case["ground_truth"]["expected_judgment"]["severity"],
            "critical",
        )

    def test_calibrated_difficulties_and_distribution(self):
        expected_overrides = {
            "A03": "medium",
            "A09": "medium",
            "A10": "hard",
            "A14": "hard",
        }
        for test_case_id, difficulty in expected_overrides.items():
            with self.subTest(test_case_id=test_case_id):
                self.assertEqual(self.case_by_id(test_case_id)["difficulty"], difficulty)

        distribution = Counter(case["difficulty"] for case in self.require_cases())
        self.assertEqual(
            distribution,
            {"easy": 7, "medium": 13, "hard": 8, "expert": 2},
        )

    def test_each_case_has_six_code_graders(self):
        expected_code_checks = {
            "tools_called_minimum",
            "output_schema",
            "severity_enum",
            "severity_match",
            "confidence_range",
            "remediation_not_empty",
        }
        for case in self.require_cases():
            with self.subTest(test_case_id=case["test_case_id"]):
                code_checks = [
                    grader["check"]
                    for grader in case["graders"]
                    if grader["type"] == "code"
                ]
                self.assertEqual(len(code_checks), 6)
                self.assertEqual(set(code_checks), expected_code_checks)
                self.assertEqual(
                    len([g for g in case["graders"] if g["type"] == "model"]),
                    2,
                )
                self.assertEqual(
                    len([g for g in case["graders"] if g["type"] == "human"]),
                    1,
                )

    def case_by_id(self, test_case_id):
        cases = self.require_cases()
        return next(case for case in cases if case["test_case_id"] == test_case_id)


if __name__ == "__main__":
    unittest.main()
