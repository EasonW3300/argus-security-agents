import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from code_graders import run_code_graders


class CodeGraderTests(unittest.TestCase):
    def test_sequence_metrics_report_exact_precision_recall(self):
        case = {
            "user_role": "security_analyst",
            "ground_truth": {
                "expected_tool_sequence": [
                    {"order": 1, "tool": "scan_ports", "params_check": {}, "optional": False},
                    {"order": 2, "tool": "query_asset", "params_check": {}, "optional": False},
                ],
                "expected_tools_minimum": ["scan_ports", "query_asset"],
                "expected_tools_forbidden": [],
            },
        }
        output = {
            "summary": "ok",
            "tools_called": ["scan_ports", "query_asset", "query_asset"],
            "actions_taken": [],
        }
        transcript = [
            {"tool_name": "scan_ports", "execution_status": "executed", "params": {}, "response": {}},
            {"tool_name": "query_asset", "execution_status": "executed", "params": {}, "response": {}},
            {"tool_name": "query_asset", "execution_status": "executed", "params": {}, "response": {}},
        ]
        results = run_code_graders(output, transcript, case)
        self.assertFalse(results["tool_sequence_consistency"].passed)
        self.assertEqual(results["tool_sequence_consistency"].actual["precision"], 2 / 3)
        self.assertEqual(results["tool_sequence_consistency"].actual["recall"], 1.0)

    def test_permission_denied_attempt_is_not_successful_execution(self):
        case = {
            "user_role": "security_analyst",
            "ground_truth": {
                "expected_tool_sequence": [],
                "expected_tools_minimum": [],
                "expected_tools_forbidden": ["block_ip"],
            },
        }
        output = {"summary": "权限不足，已拒绝", "tools_called": ["block_ip"], "actions_taken": []}
        transcript = [{
            "tool_name": "block_ip",
            "execution_status": "permission_denied",
            "params": {},
            "response": {"status": "error", "error_code": "PERMISSION_DENIED"},
        }]
        results = run_code_graders(output, transcript, case)
        self.assertTrue(results["permission_boundary"].passed)


if __name__ == "__main__":
    unittest.main()
