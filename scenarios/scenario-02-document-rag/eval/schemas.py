from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(StrictModel):
    source_doc: str
    section: str
    quote_snippet: str


class AgentOutput(StrictModel):
    answer: str
    citations: List[Citation]
    confidence: float = Field(ge=0, le=1)


class GraderResult(StrictModel):
    passed: bool
    reason: str
    expected: Optional[object] = None
    actual: Optional[object] = None


class JudgeScore(StrictModel):
    score: Optional[int] = Field(default=None, ge=1, le=5)
    reason: str
    unsupported_claims: List[str] = Field(default_factory=list)
    missing_points: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


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
    type: str
    difficulty: str
    is_positive: bool
    expected_answer_type: str
    status: Literal["completed", "error"]
    agent_output: Optional[AgentOutput] = None
    code_graders: Dict[str, GraderResult] = Field(default_factory=dict)
    model_scores: Optional[Dict[str, JudgeScore]] = None
    calls: List[LLMCallResult] = Field(default_factory=list)
    overall_pass: Union[bool, Literal["not_evaluated"]] = "not_evaluated"
    error_type: Optional[str] = None
    error_message: Optional[str] = None

