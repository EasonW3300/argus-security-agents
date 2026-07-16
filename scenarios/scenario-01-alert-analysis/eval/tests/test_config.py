import json
import os
import math
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import PricingConfig, load_config


class ConfigTest(unittest.TestCase):
    def test_deepseek_agent_and_qwen_judge(self):
        cfg = load_config({
            "AGENT_PROVIDER": "deepseek",
            "AGENT_MODEL": "deepseek-v4-pro",
            "DEEPSEEK_API_KEY": "agent-secret",
            "JUDGE_PROVIDER": "qwen",
            "JUDGE_MODEL": "qwen-plus",
            "DASHSCOPE_API_KEY": "judge-secret",
            "JUDGE_ENABLE_THINKING": "false",
        })
        self.assertEqual(cfg.agent.base_url, "https://api.deepseek.com")
        self.assertEqual(cfg.judge.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertFalse(cfg.judge.enable_thinking)
        self.assertNotIn("agent-secret", str(cfg.public_dict()))

    def test_custom_requires_base_url_and_key(self):
        with self.assertRaisesRegex(ValueError, "CUSTOM.*base URL"):
            load_config({"AGENT_PROVIDER": "custom", "AGENT_MODEL": "local-model"})

    def test_judge_inherits_agent_when_omitted(self):
        cfg = load_config({
            "AGENT_PROVIDER": "openai",
            "AGENT_MODEL": "gpt-4o-mini",
            "OPENAI_API_KEY": "secret",
        })
        self.assertEqual(cfg.judge.provider, "openai")
        self.assertEqual(cfg.judge.model, "gpt-4o-mini")

    def test_pricing_rejects_negative_and_non_finite_values(self):
        fields = (
            "agent_input_per_1m",
            "agent_output_per_1m",
            "judge_input_per_1m",
            "judge_output_per_1m",
        )
        invalid_values = (-1, math.nan, math.inf, -math.inf)

        for field in fields:
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        PricingConfig(**{field: value})

    def test_pricing_allows_zero(self):
        pricing = PricingConfig(
            agent_input_per_1m=0,
            agent_output_per_1m=0,
            judge_input_per_1m=0,
            judge_output_per_1m=0,
        )

        self.assertEqual(pricing.agent_input_per_1m, 0)
        self.assertEqual(pricing.agent_output_per_1m, 0)
        self.assertEqual(pricing.judge_input_per_1m, 0)
        self.assertEqual(pricing.judge_output_per_1m, 0)

    def test_public_config_recursively_redacts_extra_body_secrets(self):
        api_key = "deepseek-sensitive-key"
        extra_body = {
            "trace_id": "trace-123",
            "header-" + api_key: "key-name-must-be-redacted",
            "nested": {
                "authorization": "Bearer unrelated-value",
                "note": "prefix %s suffix" % api_key,
                "items": [
                    {"access_token": "nested-token"},
                    "safe-value",
                ],
            },
            "clientSecret": {"raw": "must-not-survive"},
            "password_hint": "must-not-survive-either",
        }
        cfg = load_config(
            {
                "AGENT_PROVIDER": "deepseek",
                "AGENT_MODEL": "model",
                "DEEPSEEK_API_KEY": api_key,
                "AGENT_EXTRA_BODY_JSON": json.dumps(extra_body),
            }
        )

        public = cfg.agent.public_dict()
        rendered = json.dumps(public)

        self.assertNotIn(api_key, rendered)
        self.assertNotIn("unrelated-value", rendered)
        self.assertNotIn("nested-token", rendered)
        self.assertNotIn("must-not-survive", rendered)
        self.assertEqual(public["extra_body"]["trace_id"], "trace-123")
        self.assertIsNone(public["max_tokens"])
        self.assertEqual(
            public["extra_body"]["nested"]["items"][1], "safe-value"
        )
        self.assertIn("[REDACTED]", rendered)
