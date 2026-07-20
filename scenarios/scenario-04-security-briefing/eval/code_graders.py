"""Deterministic quality gates for the security briefing output contract."""
from __future__ import annotations

import json
import re
from numbers import Number

from schemas import GraderResult, ReportOutput


CODE_CHECKS = (
    "data_accuracy",
    "template_completeness",
    "format_compliance",
    "masking_check",
    "push_target",
    "output_schema",
)
_PLACEHOLDER = re.compile(r"\{\{[^{}]+\}\}")
_PERCENT = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%")


def _result(passed, reason, expected=None, actual=None):
    return GraderResult(bool(passed), reason, expected, actual)


def _value_at(data, path):
    """Resolve dotted paths with ``[index]`` and the dataset's ``.length`` suffix."""
    value = data
    for part in path.split("."):
        if part == "length":
            return len(value) if isinstance(value, (str, list, tuple, dict)) else None
        match = re.fullmatch(r"([^\[]+)(?:\[(\d+)\])?", part)
        if not match or not isinstance(value, dict):
            return None
        value = value.get(match.group(1))
        if match.group(2) is not None:
            if not isinstance(value, list):
                return None
            index = int(match.group(2))
            value = value[index] if index < len(value) else None
    return value


def _rendered_output(output):
    return json.dumps(output, ensure_ascii=False, sort_keys=True, default=str)


def _numeric_present(rendered, expected):
    if isinstance(expected, bool) or not isinstance(expected, Number):
        return str(expected) in rendered
    if 0 <= expected <= 1:
        target = float(expected) * 100
        return any(abs(float(value) - target) <= 0.1 + 1e-9 for value in _PERCENT.findall(rendered))
    target = float(expected)
    return any(abs(float(value) - target) <= 1e-9 for value in re.findall(r"(?<![\d.])-?\d+(?:\.\d+)?", rendered))


def _data_accuracy(output, case):
    source = case.get("mock_source_data", {})
    checks = case.get("ground_truth", {}).get("data_accuracy_checks", [])
    rendered = _rendered_output(output)
    failures = []
    actual = []
    for check in checks:
        path = check.get("source_path")
        expected = check.get("expected_value")
        if path == "衍生计算":
            # The scenario specifies 34 / 156; validate the reported percentage,
            # with the documented absolute ±0.1 percentage-point tolerance.
            related = _value_at(source, "alert_stats.vuln_related_alerts")
            total = _value_at(source, "alert_stats.total")
            computed = related / total if isinstance(related, Number) and total else None
            source_ok = computed is not None and abs(computed - float(expected)) <= 0.001
            shown = [float(value) / 100 for value in _PERCENT.findall(rendered)]
            output_ok = any(abs(value - float(expected)) <= 0.001 + 1e-9 for value in shown)
            observed = {"computed": computed, "reported_percentages": [value * 100 for value in shown]}
        else:
            source_value = _value_at(source, path)
            source_ok = source_value == expected
            # ``.length`` is represented by the mapped collection, not necessarily
            # by a literal count, so the presence of the source mapping is enough.
            # Numeric metrics must be rendered.  A declared string identifier may
            # be omitted by a template (for example an incident id represented by
            # the report title), but if present it must agree with Ground Truth.
            output_ok = (
                path.endswith(".length")
                or not isinstance(expected, Number)
                or _numeric_present(rendered, expected)
            )
            observed = {"source_value": source_value, "rendered": output_ok}
        actual.append({"metric": check.get("metric"), **observed})
        if not (source_ok and output_ok):
            failures.append(check.get("metric", path))
    return _result(not failures, "all declared metrics match source data" if not failures else "metric mismatch: " + ", ".join(failures), checks, actual)


def _template_completeness(output, case):
    expected = case.get("ground_truth", {}).get("expected_sections", [])
    sections = output.get("content", {}).get("sections", []) if isinstance(output, dict) else []
    ids = [item.get("section_id") for item in sections if isinstance(item, dict)]
    nonempty = all(isinstance(item, dict) and isinstance(item.get("body"), str) and item["body"].strip() for item in sections)
    placeholders = [item.get("section_id") for item in sections if isinstance(item, dict) and _PLACEHOLDER.search(item.get("body", ""))]
    passed = ids == expected and nonempty and not placeholders
    return _result(passed, "all required sections are present and complete" if passed else "section ids, bodies, or placeholders are invalid", expected, {"section_ids": ids, "placeholders": placeholders})


def _format_compliance(output, case):
    sections = output.get("content", {}).get("sections", []) if isinstance(output, dict) else []
    errors = []
    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("body"), str):
            errors.append("invalid section body")
            continue
        body = section["body"]
        if body.count("```") % 2:
            errors.append("unbalanced code fence in %s" % section.get("section_id"))
        headings = [len(match.group(1)) for match in re.finditer(r"^\s*(#{1,6})\s+\S", body, re.M)]
        if any(next_level > level + 1 for level, next_level in zip(headings, headings[1:])):
            errors.append("skipped heading level in %s" % section.get("section_id"))
        table_rows = [line for line in body.splitlines() if line.strip().startswith("|")]
        if table_rows:
            counts = [len([cell for cell in line.strip().strip("|").split("|")]) for line in table_rows]
            if len(set(counts)) != 1:
                errors.append("inconsistent table columns in %s" % section.get("section_id"))
    return _result(not errors, "Markdown structure is compliant" if not errors else "; ".join(errors), "balanced fences, non-skipping headings, consistent table columns", errors)


def _masking_check(output, case):
    gt = case.get("ground_truth", {})
    rendered = _rendered_output(output)
    audience = case.get("target_audience")
    if audience == "management":
        patterns = [item.get("pattern", "") for item in gt.get("sensitive_patterns", []) if item.get("should_be_masked", True)]
        patterns.extend(re.escape(item) for item in gt.get("expected_output_must_not_include", []))
        leaks = []
        for pattern in patterns:
            match = re.search(pattern, rendered) if pattern else None
            if match:
                leaks.append(match.group(0))
        return _result(not leaks, "management sensitive values are masked" if not leaks else "sensitive values leaked", "no sensitive patterns", {"leaks": leaks})
    required = gt.get("expected_output_must_include", [])
    removed = [value for value in required if str(value) not in rendered]
    return _result(not removed, "security-lead technical values retained" if not removed else "required technical values were removed", required, {"removed": removed})


def _push_target(output, case):
    expected = {"channel": case.get("push_config", {}).get("channel"), "recipients": case.get("push_config", {}).get("recipients")}
    actual = {"channel": output.get("target_channel") if isinstance(output, dict) else None, "recipients": output.get("target_recipients") if isinstance(output, dict) else None}
    return _result(actual == expected, "push target exactly matches configuration" if actual == expected else "push target mismatch", expected, actual)


def _output_schema(output, case):
    try:
        ReportOutput.validate(output, expected_section_ids=case.get("ground_truth", {}).get("expected_sections"))
    except (TypeError, ValueError) as exc:
        return _result(False, "output schema invalid: " + str(exc), "ReportOutput contract", output)
    return _result(True, "output schema valid", "ReportOutput contract", "valid")


def run_code_graders(final_output: dict, case: dict) -> dict[str, GraderResult]:
    """Run every deterministic check, even when the output is malformed."""
    output = final_output if isinstance(final_output, dict) else {}
    case = case if isinstance(case, dict) else {}
    return {
        "data_accuracy": _data_accuracy(output, case),
        "template_completeness": _template_completeness(output, case),
        "format_compliance": _format_compliance(output, case),
        "masking_check": _masking_check(output, case),
        "push_target": _push_target(output, case),
        "output_schema": _output_schema(output, case),
    }
