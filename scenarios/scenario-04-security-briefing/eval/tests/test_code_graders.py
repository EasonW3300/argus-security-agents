import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT.parent / "EvalsData.json"
sys.path.insert(0, str(ROOT))

from code_graders import CODE_CHECKS, run_code_graders
from mock_agent import run_mock_case
from schemas import load_cases


class CodeGraderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases(DATA_PATH)

    def test_mock_positive_case_passes_all_code_graders(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]

        results = run_code_graders(output, case)

        self.assertEqual(tuple(results), CODE_CHECKS)
        self.assertTrue(all(item.passed for item in results.values()))
        self.assertTrue(all(section["body"].startswith("# ") for section in output["content"]["sections"]))

    def test_data_accuracy_rejects_unmapped_contradictory_number(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]
        output["content"]["sections"][0]["body"] += "\n告警总数：999"

        self.assertFalse(run_code_graders(output, case)["data_accuracy"].passed)

    def test_data_accuracy_rejects_mapping_with_correct_and_contradictory_numbers(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]
        output["content"]["sections"][0]["data_source_mapping"]["alert_stats.total"] = "156 999"

        self.assertFalse(run_code_graders(output, case)["data_accuracy"].passed)

    def test_data_accuracy_rejects_missing_list_length_mapping(self):
        case = self.cases[2]
        output = run_mock_case(case)["final_output"]
        for section in output["content"]["sections"]:
            section["data_source_mapping"].pop("incident_list.length", None)

        self.assertFalse(run_code_graders(output, case)["data_accuracy"].passed)

    def test_data_accuracy_rejects_missing_indexed_string_mapping(self):
        case = self.cases[4]
        output = run_mock_case(case)["final_output"]
        for section in output["content"]["sections"]:
            section["data_source_mapping"].pop("hw_daily_stats.top_attack_sources[0].ip", None)

        self.assertFalse(run_code_graders(output, case)["data_accuracy"].passed)

    def test_data_accuracy_accepts_ground_truth_string_declared_with_punctuation(self):
        case = self.cases[15]
        output = run_mock_case(case)["final_output"]

        self.assertTrue(run_code_graders(output, case)["data_accuracy"].passed)

    def test_required_template_data_must_remain_in_its_section_mapping(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]
        section = next(item for item in output["content"]["sections"] if item["section_id"] == "summary")
        for path in ("alert_stats.by_severity", "alert_stats.disposal_rate"):
            section["data_source_mapping"].pop(path, None)
            section["data_values"].pop(path, None)

        results = run_code_graders(output, case)

        self.assertFalse(results["data_accuracy"].passed)
        self.assertFalse(results["template_completeness"].passed)

    def test_required_container_data_must_render_top_rule_leaf_values(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]
        section = next(item for item in output["content"]["sections"] if item["section_id"] == "top_rules")
        section["body"] = "# TOP 3 告警规则\n\n- alert_stats.top_rules：已生成。"

        results = run_code_graders(output, case)

        self.assertFalse(results["data_accuracy"].passed)
        self.assertFalse(results["template_completeness"].passed)

    def test_security_lead_cannot_replace_top_rule_leaf_with_forged_masking_record(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]
        section = next(item for item in output["content"]["sections"] if item["section_id"] == "top_rules")
        section["body"] = section["body"].replace("Multiple Failed Logins from Same Source", "暴力破解检测")
        output["masking_applied"] = [{
            "original": "Multiple Failed Logins from Same Source",
            "masked": "暴力破解检测",
            "rule": "Multiple Failed Logins from Same Source",
        }]

        results = run_code_graders(output, case)

        self.assertFalse(results["data_accuracy"].passed)
        self.assertFalse(results["template_completeness"].passed)

    def test_management_masking_record_requires_matching_sensitive_rule(self):
        case = self.cases[8]
        output = run_mock_case(case)["final_output"]
        output["masking_applied"][0]["rule"] = "not-a-sensitive-pattern"

        results = run_code_graders(output, case)

        self.assertFalse(results["data_accuracy"].passed)
        self.assertFalse(results["template_completeness"].passed)

    def test_management_masking_cannot_replace_an_entire_leaf_for_one_sensitive_fragment(self):
        case = self.cases[12]
        output = run_mock_case(case)["final_output"]
        section = next(item for item in output["content"]["sections"] if item["section_id"] == "remediation_matrix")
        section["body"] = section["body"].replace("部门 A服务器存在未修复高危漏洞", "HIDDEN")
        output["masking_applied"].insert(0, {
            "original": "核心业务部服务器存在未修复高危漏洞",
            "masked": "HIDDEN",
            "rule": "核心业务部",
        })

        results = run_code_graders(output, case)

        self.assertFalse(results["data_accuracy"].passed)
        self.assertFalse(results["template_completeness"].passed)

    def test_data_accuracy_binds_body_mapping_and_actual_value_to_the_same_path(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]
        section = next(item for item in output["content"]["sections"] if item["section_id"] == "summary")
        section["data_source_mapping"]["alert_stats.total"] = "alert_stats.avg_disposal_minutes"
        section["data_values"]["alert_stats.total"] = 23
        section["body"] = section["body"].replace("alert_stats.total：156", "alert_stats.total：23")

        results = run_code_graders(output, case)

        self.assertFalse(results["data_accuracy"].passed)
        self.assertFalse(results["template_completeness"].passed)

    def test_management_sensitive_leak_fails_masking_check(self):
        case = self.cases[18]
        output = run_mock_case(case)["final_output"]

        result = run_code_graders(output, case)["masking_check"]

        self.assertFalse(result.passed)
        self.assertIn("203.0.113.88", result.actual["leaks"])

    def test_wrong_recipient_fails_push_target(self):
        case = self.cases[19]
        output = run_mock_case(case)["final_output"]

        result = run_code_graders(output, case)["push_target"]

        self.assertFalse(result.passed)
        self.assertEqual(result.expected["recipients"], ["security-lead@company.com"])
        self.assertEqual(result.actual["recipients"], ["all-staff@company.com"])

    def test_derived_percentage_accepts_point_one_percent_tolerance(self):
        case = self.cases[3]
        output = run_mock_case(case)["final_output"]
        section = next(item for item in output["content"]["sections"] if item["section_id"] == "derived_metric")
        section["body"] = section["body"].replace("21.8%", "21.7%")

        self.assertTrue(run_code_graders(output, case)["data_accuracy"].passed)

    def test_security_lead_required_technical_value_cannot_be_removed(self):
        case = self.cases[4]
        output = run_mock_case(case)["final_output"]
        rendered = str(output["content"])
        self.assertIn("203.0.113.77", rendered)
        for section in output["content"]["sections"]:
            section["body"] = section["body"].replace("203.0.113.77", "外部攻击源")
            section["data_source_mapping"] = {
                key: value.replace("203.0.113.77", "外部攻击源")
                for key, value in section["data_source_mapping"].items()
            }

        self.assertFalse(run_code_graders(output, case)["masking_check"].passed)

    def test_schema_and_markdown_defects_are_reported(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]
        output["content"]["sections"][1]["body"] = "| a | b |\n| --- | --- |\n| 1 |"
        del output["metadata"]["push_status"]

        results = run_code_graders(output, case)

        self.assertFalse(results["format_compliance"].passed)
        self.assertFalse(results["output_schema"].passed)

    def test_schema_rejects_invalid_nested_mappings_masking_and_metadata(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]
        output["content"]["sections"][0]["data_source_mapping"] = {"metric": 123}
        output["content"]["sections"][0]["data_values"] = []
        output["masking_applied"] = ["not an audit object"]
        output["metadata"]["generated_at"] = "not-a-date"
        output["metadata"]["data_sources_used"] = [123]

        self.assertFalse(run_code_graders(output, case)["output_schema"].passed)

    def test_section_body_requires_markdown_heading(self):
        case = self.cases[0]
        output = run_mock_case(case)["final_output"]
        output["content"]["sections"][0]["body"] = output["content"]["sections"][0]["body"].removeprefix("# 总体摘要\n\n")

        self.assertFalse(run_code_graders(output, case)["format_compliance"].passed)


if __name__ == "__main__":
    unittest.main()
