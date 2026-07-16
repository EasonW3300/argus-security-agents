import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_builder import (
    PREFIXES,
    PROMPT_VERSION,
    build_agent_messages,
    build_judge_messages,
)


class PromptBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = Path(__file__).resolve().parents[1] / "Eval-data_v1.json"
        cls.a01 = json.loads(data.read_text(encoding="utf-8"))[0]

    def test_prompt_contains_json_and_all_sections(self):
        messages = build_agent_messages(self.a01)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("JSON", messages[0]["content"])
        for field in [
            '"alert_id"',
            '"judgment"',
            '"severity"',
            '"attack_type"',
            '"confidence"',
            '"summary"',
            '"evidence_chain"',
            '"iocs"',
            '"type"',
            '"value"',
            '"malicious"',
            '"context"',
            '"remediation"',
            '"metadata"',
            '"tools_called"',
        ]:
            self.assertIn(field, messages[0]["content"])
        for title in ["告警详情", "资产信息", "威胁情报", "关联告警"]:
            self.assertIn(title, messages[1]["content"])
        self.assertIn("192.0.2.35", messages[1]["content"])
        self.assertTrue(PROMPT_VERSION.startswith("route-a-"))

    def test_prompt_is_stable_for_reversed_response_mapping(self):
        responses = dict(self.a01["mock_api_responses"])
        responses["query_threat_intel_z"] = {"marker": "z"}
        responses["query_threat_intel_a"] = {"marker": "a"}
        forward = dict(self.a01)
        forward["mock_api_responses"] = responses
        reversed_case = dict(self.a01)
        reversed_case["mock_api_responses"] = dict(
            reversed(list(responses.items()))
        )

        forward_messages = build_agent_messages(forward)
        reversed_messages = build_agent_messages(reversed_case)

        self.assertEqual(forward_messages, reversed_messages)
        user_prompt = forward_messages[1]["content"]
        section_positions = [
            user_prompt.index(title)
            for title in ["告警详情", "资产信息", "威胁情报", "关联告警"]
        ]
        self.assertEqual(section_positions, sorted(section_positions))

    def test_agent_prompt_exposes_exact_available_tool_ids_without_ground_truth(self):
        messages = build_agent_messages(self.a01)
        system, user = messages[0]["content"], messages[1]["content"]
        available = [
            prefix
            for prefix, _ in PREFIXES
            if any(
                key.startswith(prefix)
                for key in self.a01["mock_api_responses"]
            )
        ]
        heading = "## 已执行工具标识"
        self.assertEqual(user.count(heading), 1)
        available_block = user.split(heading, 1)[1].split("##", 1)[0].strip()
        self.assertEqual(json.loads(available_block), available)
        for tool_id in available:
            self.assertIn(tool_id, user)
        self.assertIn("精确字符串", system)
        self.assertNotIn("expected_tools_minimum", system + user)

    def test_agent_prompt_is_isolated_from_ground_truth_mutation(self):
        sentinel = "__GROUND_TRUTH_SENTINEL_NEVER_IN_PROMPT_7F3A9C__"
        mutated = dict(self.a01)
        mutated["ground_truth"] = dict(self.a01["ground_truth"])
        mutated["ground_truth"]["expected_tools_minimum"] = [sentinel]

        original_messages = build_agent_messages(self.a01)
        mutated_messages = build_agent_messages(mutated)

        self.assertEqual(mutated_messages, original_messages)
        self.assertNotIn(
            sentinel,
            json.dumps(mutated_messages, ensure_ascii=False),
        )

    def test_agent_prompt_omits_tool_without_matching_mock_key(self):
        case = dict(self.a01)
        case["mock_api_responses"] = {
            key: value
            for key, value in self.a01["mock_api_responses"].items()
            if not key.startswith("query_threat_intel")
        }
        user = build_agent_messages(case)[1]["content"]
        heading = "## 已执行工具标识"
        self.assertEqual(user.count(heading), 1)
        available_block = user.split(heading, 1)[1].split("##", 1)[0].strip()
        expected = [
            prefix
            for prefix, _ in PREFIXES
            if any(key.startswith(prefix) for key in case["mock_api_responses"])
        ]
        self.assertEqual(json.loads(available_block), expected)

    def test_no_related_alerts_is_explicit(self):
        self.assertIn("无关联告警", build_agent_messages(self.a01)[1]["content"])

    def test_hallucination_judge_uses_hallucination_output_shape(self):
        messages = build_judge_messages(self.a01, {"judgment": {}}, "hallucination_check")
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn(
            "{total_statements,verifiable,hallucinations,uncertain,details:[{statement,verdict,reason}]}",
            messages[0]["content"],
        )
        self.assertIn("顶层 uncertain 是整数计数", messages[0]["content"])
        self.assertIn("details 中 verdict 为 uncertain", messages[0]["content"])
        self.assertIn("JSON", messages[0]["content"])

    def test_quality_judge_uses_score_output_shape_for_one_dimension(self):
        messages = build_judge_messages(
            self.a01, {"remediation": []}, "remediation_actionability"
        )
        self.assertIn("只评估处置建议", messages[0]["content"])
        self.assertIn(
            "{score:1-5或null,reason:string,evidence_quotes:[string]}",
            messages[0]["content"],
        )
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["agent_output"], {"remediation": []})

    def test_quality_judge_is_stable_for_reordered_response_mapping(self):
        reordered = dict(self.a01)
        reordered["mock_api_responses"] = dict(
            reversed(list(self.a01["mock_api_responses"].items()))
        )

        self.assertEqual(
            build_judge_messages(self.a01, {"judgment": {}}, "severity_rationality"),
            build_judge_messages(reordered, {"judgment": {}}, "severity_rationality"),
        )

    def test_hallucination_judge_is_stable_for_reordered_response_mapping(self):
        reordered = dict(self.a01)
        reordered["mock_api_responses"] = dict(
            reversed(list(self.a01["mock_api_responses"].items()))
        )

        self.assertEqual(
            build_judge_messages(self.a01, {"judgment": {}}, "hallucination_check"),
            build_judge_messages(reordered, {"judgment": {}}, "hallucination_check"),
        )
