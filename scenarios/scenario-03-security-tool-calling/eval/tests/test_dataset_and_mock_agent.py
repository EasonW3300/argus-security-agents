import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mock_agent import run_mock_case
from run_eval import load_cases


class DatasetAndMockAgentTests(unittest.TestCase):
    def test_dataset_loads_and_mock_agent_completes_all_cases(self):
        cases = load_cases(ROOT / "../Eval-data_v0/Eval_scen_03.json")
        self.assertEqual(len(cases), 20)
        for case in cases:
            result = run_mock_case(case)
            self.assertEqual(result["status"], "completed", case["test_case_id"])
            self.assertTrue(result["final_output"], case["test_case_id"])
            if case["is_positive"]:
                self.assertTrue(result["transcript"], case["test_case_id"])

    def test_s0313_selects_production_branch(self):
        cases = load_cases(ROOT / "../Eval-data_v0/Eval_scen_03.json")
        case = next(item for item in cases if item["test_case_id"] == "S03-013")
        result = run_mock_case(case)
        self.assertEqual(result["branch_id"], "production")
        self.assertEqual(result["tools_called"], ["scan_ports", "query_asset", "create_ticket"])


if __name__ == "__main__":
    unittest.main()
