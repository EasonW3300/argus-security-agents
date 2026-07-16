from __future__ import annotations

from typing import Dict

from schemas import GraderResult


SEVERITIES = {"critical", "high", "medium", "low", "false_positive"}


def _result(
    passed: bool,
    reason: str,
    expected: object = None,
    actual: object = None,
) -> GraderResult:
    return GraderResult(
        passed=passed,
        reason=reason,
        expected=expected,
        actual=actual,
    )


def run_code_graders(
    agent_output: dict,
    test_case: dict,
) -> Dict[str, GraderResult]:
    output = agent_output if isinstance(agent_output, dict) else {}
    case = test_case if isinstance(test_case, dict) else {}

    raw_judgment = output.get("judgment")
    judgment = raw_judgment if isinstance(raw_judgment, dict) else {}
    raw_metadata = output.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    raw_ground_truth = case.get("ground_truth")
    ground_truth = (
        raw_ground_truth if isinstance(raw_ground_truth, dict) else {}
    )

    required = ground_truth.get("expected_tools_minimum")
    actual_tools = metadata.get("tools_called")
    tools_ok = (
        isinstance(required, list)
        and isinstance(actual_tools, list)
        and all(tool in actual_tools for tool in required)
    )

    required_fields = {"alert_id", "judgment", "remediation", "metadata"}
    judgment_fields = {
        "severity",
        "attack_type",
        "confidence",
        "summary",
        "evidence_chain",
        "iocs",
    }
    schema_ok = required_fields.issubset(output) and judgment_fields.issubset(
        judgment
    )

    actual_severity = judgment.get("severity")
    expected_severity = case.get("expected_severity")
    severity_valid = (
        isinstance(actual_severity, str) and actual_severity in SEVERITIES
    )
    severity_matches = (
        "severity" in judgment
        and "expected_severity" in case
        and actual_severity == expected_severity
    )

    confidence = judgment.get("confidence")
    confidence_ok = (
        not isinstance(confidence, bool)
        and isinstance(confidence, (int, float))
        and 0 <= confidence <= 1
    )

    remediation = output.get("remediation")
    remediation_ok = (
        isinstance(remediation, list)
        and len(remediation) >= 1
        and all(
            isinstance(item, str) and len(item) >= 10
            for item in remediation
        )
    )

    return {
        "tools_called_minimum": _result(
            tools_ok,
            "required tools present" if tools_ok else "required tools missing",
            required,
            actual_tools,
        ),
        "output_schema": _result(
            schema_ok,
            "required fields present" if schema_ok else "required fields missing",
        ),
        "severity_enum": _result(
            severity_valid,
            "severity is valid" if severity_valid else "severity is invalid",
            sorted(SEVERITIES),
            actual_severity,
        ),
        "severity_match": _result(
            severity_matches,
            "severity matches" if severity_matches else "severity mismatch",
            expected_severity,
            actual_severity,
        ),
        "confidence_range": _result(
            confidence_ok,
            "confidence in range" if confidence_ok else "confidence out of range",
            "0..1",
            confidence,
        ),
        "remediation_not_empty": _result(
            remediation_ok,
            (
                "remediation actionable"
                if remediation_ok
                else "remediation missing or invalid"
            ),
            "at least one item >=10 chars",
            remediation,
        ),
    }
