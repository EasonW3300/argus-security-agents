from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Dict, List, Optional


EXPECTED_IDS = tuple(f"S04-{index:03d}" for index in range(1, 21))
REQUIRED_CASE_FIELDS = (
    "scenario",
    "type",
    "difficulty",
    "is_positive",
    "input",
    "mock_source_data",
    "template_definition",
    "push_config",
    "ground_truth",
    "graders",
)
REPORT_TYPES = {"daily", "weekly", "monthly", "special"}
TARGET_AUDIENCES = {"security_lead", "management", "both"}
TARGET_CHANNELS = {"email", "slack", "dingtalk", "wecom"}
PUSH_STATUSES = {"sent", "queued", "draft"}


@dataclass
class GraderResult:
    """A serializable outcome for a deterministic evaluation check."""

    passed: bool
    reason: str
    expected: object = None
    actual: object = None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "expected": self.expected,
            "actual": self.actual,
        }


def _dataset_error(message: str) -> ValueError:
    return ValueError("dataset validation failed: " + message)


def _require(value: object, name: str, expected_type: type) -> None:
    if not isinstance(value, expected_type):
        raise ValueError("%s must be %s" % (name, expected_type.__name__))


def _validate_case(case: object, index: int) -> None:
    if not isinstance(case, dict):
        raise _dataset_error("case %d must be an object" % (index + 1))
    case_id = case.get("test_case_id", "case %d" % (index + 1))
    for name in REQUIRED_CASE_FIELDS:
        if name not in case:
            raise _dataset_error("%s missing %s" % (case_id, name))
    _require(case["scenario"], "%s.scenario" % case_id, str)
    _require(case["type"], "%s.type" % case_id, str)
    _require(case["difficulty"], "%s.difficulty" % case_id, str)
    _require(case["is_positive"], "%s.is_positive" % case_id, bool)
    _require(case["input"], "%s.input" % case_id, dict)
    _require(case["mock_source_data"], "%s.mock_source_data" % case_id, dict)
    _require(case["template_definition"], "%s.template_definition" % case_id, dict)
    _require(case["push_config"], "%s.push_config" % case_id, dict)
    _require(case["ground_truth"], "%s.ground_truth" % case_id, dict)
    _require(case["graders"], "%s.graders" % case_id, list)

    sections = case["template_definition"].get("sections")
    expected_sections = case["ground_truth"].get("expected_sections")
    if not isinstance(sections, list) or not sections:
        raise _dataset_error("%s.template_definition.sections must be a non-empty list" % case_id)
    if (
        not isinstance(expected_sections, list)
        or not expected_sections
        or not all(isinstance(item, str) and item for item in expected_sections)
    ):
        raise _dataset_error("%s.ground_truth.expected_sections must be a non-empty string list" % case_id)
    template_ids = []
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise _dataset_error("%s.template_definition.sections[%d] must be an object" % (case_id, section_index))
        section_id = section.get("section_id")
        if not isinstance(section_id, str) or not section_id:
            raise _dataset_error(
                "%s.template_definition.sections[%d].section_id must be a non-empty string"
                % (case_id, section_index)
            )
        template_ids.append(section_id)
    if template_ids != expected_sections:
        raise _dataset_error("%s template section ids must match expected_sections" % case_id)
    if not all(isinstance(grader, dict) and grader.get("check") for grader in case["graders"]):
        raise _dataset_error("%s.graders must contain grader checks" % case_id)


def load_cases(path: Path) -> List[dict]:
    """Load Scenario 4 cases and enforce the immutable dataset contract."""
    try:
        cases = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _dataset_error(str(exc)) from exc
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_IDS):
        raise _dataset_error("dataset must contain exactly 20 cases")
    for index, case in enumerate(cases):
        _validate_case(case, index)
    if tuple(case.get("test_case_id") for case in cases) != EXPECTED_IDS:
        raise _dataset_error("case ids must be ordered S04-001 through S04-020")
    return cases


class ReportOutput:
    """Validator for the structured report contract emitted by the report agent."""

    REQUIRED_FIELDS = (
        "report_title",
        "report_type",
        "target_audience",
        "target_channel",
        "target_recipients",
        "content",
        "masking_applied",
        "metadata",
    )

    @classmethod
    def validate(cls, output: object, expected_section_ids: Optional[List[str]] = None) -> dict:
        if not isinstance(output, dict):
            raise ValueError("report output must be an object")
        missing = [name for name in cls.REQUIRED_FIELDS if name not in output]
        if missing:
            raise ValueError("report output missing required fields: " + ", ".join(missing))
        _require(output["report_title"], "report_title", str)
        _require(output["target_recipients"], "target_recipients", list)
        _require(output["content"], "content", dict)
        _require(output["masking_applied"], "masking_applied", list)
        _require(output["metadata"], "metadata", dict)
        if output["report_type"] not in REPORT_TYPES:
            raise ValueError("report_type must be one of " + ", ".join(sorted(REPORT_TYPES)))
        if output["target_audience"] not in TARGET_AUDIENCES:
            raise ValueError("target_audience must be one of " + ", ".join(sorted(TARGET_AUDIENCES)))
        if output["target_channel"] not in TARGET_CHANNELS:
            raise ValueError("target_channel must be one of " + ", ".join(sorted(TARGET_CHANNELS)))
        if not output["target_recipients"] or not all(
            isinstance(item, str) and item for item in output["target_recipients"]
        ):
            raise ValueError("target_recipients must be a non-empty string list")

        sections = output["content"].get("sections")
        if not isinstance(sections, list):
            raise ValueError("content.sections must be a list")
        section_ids = []
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                raise ValueError("content.sections[%d] must be an object" % index)
            for name in ("section_id", "title", "body", "data_source_mapping"):
                if name not in section:
                    raise ValueError("content.sections[%d] missing %s" % (index, name))
            _require(section["section_id"], "content.sections[%d].section_id" % index, str)
            _require(section["title"], "content.sections[%d].title" % index, str)
            _require(section["body"], "content.sections[%d].body" % index, str)
            _require(section["data_source_mapping"], "content.sections[%d].data_source_mapping" % index, dict)
            section_ids.append(section["section_id"])
        if expected_section_ids is not None and section_ids != expected_section_ids:
            raise ValueError("content section ids must exactly match expected_section_ids")

        metadata = output["metadata"]
        for name in ("generated_at", "data_sources_used", "push_status"):
            if name not in metadata:
                raise ValueError("metadata missing " + name)
        _require(metadata["generated_at"], "metadata.generated_at", str)
        _require(metadata["data_sources_used"], "metadata.data_sources_used", list)
        if metadata["push_status"] not in PUSH_STATUSES:
            raise ValueError("metadata.push_status must be one of " + ", ".join(sorted(PUSH_STATUSES)))
        return output


@dataclass
class CaseResult:
    test_case_id: str
    scenario: str
    type: str
    difficulty: str
    is_positive: bool
    status: str
    final_output: Optional[dict] = None
    code_graders: Dict[str, object] = field(default_factory=dict)
    model_scores: Optional[dict] = None
    calls: List[object] = field(default_factory=list)
    overall_pass: bool | str = "not_evaluated"
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        def convert(value: object) -> object:
            if is_dataclass(value):
                return {item.name: convert(getattr(value, item.name)) for item in fields(value)}
            if hasattr(value, "__dict__"):
                return {key: convert(item) for key, item in value.__dict__.items()}
            if isinstance(value, list):
                return [convert(item) for item in value]
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            return value

        return convert(self)
