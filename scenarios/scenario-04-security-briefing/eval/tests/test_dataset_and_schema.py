import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT.parent / "EvalsData.json"
sys.path.insert(0, str(ROOT))

from schemas import CaseResult, ReportOutput, load_cases


class DatasetAndSchemaTests(unittest.TestCase):
    def test_dataset_has_twenty_ordered_cases(self):
        cases = load_cases(DATA_PATH)

        self.assertEqual(len(cases), 20)
        self.assertEqual(
            [case["test_case_id"] for case in cases],
            [f"S04-{index:03d}" for index in range(1, 21)],
        )

    def test_cases_contain_report_inputs_and_grader_contract(self):
        case = load_cases(DATA_PATH)[0]

        self.assertIn("mock_source_data", case)
        self.assertIn("template_definition", case)
        self.assertIn("push_config", case)
        self.assertIn("expected_sections", case["ground_truth"])

    def test_report_output_validates_contract_and_template_section_ids(self):
        case = load_cases(DATA_PATH)[0]
        output = {
            "report_title": "安全态势日报 —— 2026-07-16",
            "report_type": "daily",
            "target_audience": "security_lead",
            "target_channel": "email",
            "target_recipients": ["security-lead@company.com"],
            "content": {
                "sections": [
                    {
                        "section_id": section_id,
                        "title": section_id,
                        "body": "内容",
                        "data_source_mapping": {},
                    }
                    for section_id in case["ground_truth"]["expected_sections"]
                ]
            },
            "masking_applied": [],
            "metadata": {
                "generated_at": "2026-07-16T09:00:00+00:00",
                "data_sources_used": ["alert_stats"],
                "push_status": "sent",
            },
        }

        validated = ReportOutput.validate(
            output, expected_section_ids=case["ground_truth"]["expected_sections"]
        )

        self.assertEqual(validated["report_type"], "daily")

    def test_report_output_rejects_unknown_enum_and_missing_section(self):
        output = {
            "report_title": "日报",
            "report_type": "invalid",
            "target_audience": "security_lead",
            "target_channel": "email",
            "target_recipients": ["security-lead@company.com"],
            "content": {"sections": []},
            "masking_applied": [],
            "metadata": {
                "generated_at": "2026-07-16T09:00:00+00:00",
                "data_sources_used": [],
                "push_status": "draft",
            },
        }

        with self.assertRaisesRegex(ValueError, "report_type"):
            ReportOutput.validate(output, expected_section_ids=["summary"])

    def test_case_result_serializes_completed_and_error_records(self):
        completed = CaseResult(
            test_case_id="S04-001",
            scenario="日报",
            type="daily_report",
            difficulty="easy",
            is_positive=True,
            status="completed",
            final_output={"report_title": "日报"},
        )
        error = CaseResult(
            test_case_id="S04-002",
            scenario="日报",
            type="daily_report",
            difficulty="easy",
            is_positive=True,
            status="error",
            error_type="ValueError",
            error_message="invalid output",
        )

        self.assertEqual(completed.to_dict()["status"], "completed")
        self.assertEqual(error.to_dict()["error_type"], "ValueError")


if __name__ == "__main__":
    unittest.main()
