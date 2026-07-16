from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IOC(StrictModel):
    type: Literal["ip", "domain", "hash", "url"]
    value: str
    malicious: bool
    context: str


class Judgment(StrictModel):
    severity: Literal["critical", "high", "medium", "low", "false_positive"]
    attack_type: str
    confidence: float = Field(ge=0, le=1)
    summary: str
    evidence_chain: List[str]
    iocs: List[IOC]


class AgentMetadata(StrictModel):
    tools_called: List[str]


class AgentOutput(StrictModel):
    alert_id: str
    judgment: Judgment
    remediation: List[str]
    metadata: AgentMetadata


class GraderResult(StrictModel):
    passed: bool
    reason: str
    expected: Optional[object] = None
    actual: Optional[object] = None


class QualityScore(StrictModel):
    score: Optional[int] = Field(default=None, ge=1, le=5)
    reason: str
    evidence_quotes: List[str]


class HallucinationDetail(StrictModel):
    statement: str
    verdict: Literal["verifiable", "hallucination", "uncertain"]
    reason: str


class HallucinationResult(StrictModel):
    total_statements: int = Field(ge=0)
    verifiable: int = Field(ge=0)
    hallucinations: int = Field(ge=0)
    uncertain: int = Field(ge=0)
    details: List[HallucinationDetail]

    def ratio(self):
        return (
            None
            if self.total_statements == 0
            else self.hallucinations / self.total_statements
        )


class LLMCallResult(StrictModel):
    label: str
    parsed: object
    raw_text: str
    provider: str
    model: str
    response_mode: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: int
    attempts: int


class CaseResult(StrictModel):
    test_case_id: str
    scenario: str
    difficulty: str
    is_positive: bool
    expected_severity: str
    status: Literal["completed", "error"]
    agent_output: Optional[AgentOutput] = None
    code_graders: Dict[str, GraderResult] = Field(default_factory=dict)
    quality_scores: Optional[Dict[str, QualityScore]] = None
    hallucination: Optional[HallucinationResult] = None
    calls: List[LLMCallResult] = Field(default_factory=list)
    overall_pass: Union[bool, Literal["not_evaluated"]] = "not_evaluated"
    error_type: Optional[str] = None
    error_message: Optional[str] = None
