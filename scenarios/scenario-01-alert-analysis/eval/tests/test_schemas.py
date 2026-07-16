import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import AgentOutput, HallucinationResult, QualityScore


VALID = {
    "alert_id": "A01",
    "judgment": {
        "severity": "critical",
        "attack_type": "brute_force",
        "confidence": 0.9,
        "summary": "已成功登录核心资产",
        "evidence_chain": ["root 登录成功"],
        "iocs": [],
    },
    "remediation": ["立即隔离目标主机并重置 root 密码"],
    "metadata": {"tools_called": ["query_alert_detail", "query_threat_intel"]},
}


class SchemaTest(unittest.TestCase):
    def test_agent_output_accepts_valid_payload(self):
        self.assertEqual(
            AgentOutput.model_validate(VALID).judgment.severity,
            "critical",
        )

    def test_agent_output_rejects_unknown_severity(self):
        broken = dict(VALID)
        broken["judgment"] = dict(VALID["judgment"], severity="urgent")
        with self.assertRaises(ValidationError):
            AgentOutput.model_validate(broken)

    def test_quality_score_allows_uncertain(self):
        score = QualityScore(score=None, reason="证据不足", evidence_quotes=[])
        self.assertIsNone(score.score)

    def test_zero_statement_hallucination_ratio_is_none(self):
        result = HallucinationResult(
            total_statements=0,
            verifiable=0,
            hallucinations=0,
            uncertain=0,
            details=[],
        )
        self.assertIsNone(result.ratio())


if __name__ == "__main__":
    unittest.main()
