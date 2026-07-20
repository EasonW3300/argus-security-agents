from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Dict, List, Optional


@dataclass
class LLMCallResult:
    label: str
    parsed: dict
    raw_text: str
    provider: str
    model: str
    response_mode: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: int = 0
    attempts: int = 1


@dataclass
class GraderResult:
    passed: bool
    reason: str
    expected: object = None
    actual: object = None

    def to_dict(self):
        return {"passed": self.passed, "reason": self.reason, "expected": self.expected, "actual": self.actual}


@dataclass
class CaseResult:
    test_case_id: str
    scenario: str
    type: str
    difficulty: str
    is_positive: bool
    status: str
    final_output: Optional[dict] = None
    transcript: List[dict] = field(default_factory=list)
    code_graders: Dict[str, GraderResult] = field(default_factory=dict)
    model_scores: Optional[dict] = None
    calls: list = field(default_factory=list)
    overall_pass: bool | str = "not_evaluated"
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self):
        def convert(value):
            if is_dataclass(value):
                return {item.name: convert(getattr(value, item.name)) for item in fields(value)}
            if hasattr(value, "__dict__"):
                return {k: convert(v) for k, v in value.__dict__.items()}
            if isinstance(value, list):
                return [convert(v) for v in value]
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            return value
        return convert(self)
