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


def _mapping_matches(value, expected):
    """Check a single rendered metric declaration against its actual source value."""
    rendered = str(value)
    if isinstance(expected, bool):
        return rendered == str(expected)
    if isinstance(expected, Number):
        percentages = [float(token) for token in _PERCENT.findall(rendered)]
        plain_tokens = [
            float(token)
            for token in re.findall(r"(?<![\d.])-?\d+(?:\.\d+)?", _PERCENT.sub("", rendered))
        ]
        # A mapping is a declaration, not prose: it must contain exactly one
        # numeric value.  This rejects values such as ``156 999`` even though
        # they contain a correct token.
        if len(percentages) + len(plain_tokens) != 1:
            return False
        if percentages:
            target = float(expected) * 100 if 0 <= expected <= 1 else float(expected)
            return abs(percentages[0] - target) <= 0.1 + 1e-9
        return abs(plain_tokens[0] - float(expected)) <= 1e-9
    return rendered == str(expected)


def _sections(output):
    content = output.get("content", {}) if isinstance(output, dict) else {}
    return content.get("sections", []) if isinstance(content, dict) else []


def _entries(section):
    mapping = section.get("data_source_mapping") if isinstance(section, dict) else None
    values = section.get("data_values") if isinstance(section, dict) else None
    if not isinstance(mapping, dict) or not isinstance(values, dict):
        return []
    return [(metric, path, values.get(metric)) for metric, path in mapping.items() if metric in values]


def _body_has_metric_value(section, metric, expected, output):
    body = section.get("body", "") if isinstance(section, dict) else ""
    if not isinstance(body, str) or metric not in body:
        return False
    # Container values are bound by their exact JSON audit value; requiring the
    # marker in prose avoids pretending an unordered container has one display.
    if isinstance(expected, (dict, list)):
        return True
    lines = [
        re.split(r"[；;。]", line.split(metric, 1)[1], maxsplit=1)[0]
        for line in body.splitlines() if metric in line
    ]
    if isinstance(expected, str):
        return any(expected in line for line in lines)
    if any(_mapping_matches(line, expected) for line in lines):
        return True
    rendered = str(expected)
    for record in output.get("masking_applied", []) if isinstance(output, dict) else []:
        if isinstance(record, dict) and record.get("original") == rendered:
            return any(record.get("masked") in line for line in lines)
    return False


def _required_data_failures(output, case):
    section_by_id = {
        section.get("section_id"): section for section in _sections(output) if isinstance(section, dict)
    }
    failures = []
    for template in case.get("template_definition", {}).get("sections", []):
        section_id = template.get("section_id") if isinstance(template, dict) else None
        section = section_by_id.get(section_id)
        for path in template.get("required_data", []) if isinstance(template, dict) else []:
            source_value = _value_at(case.get("mock_source_data", {}), path)
            matching = [entry for entry in _entries(section) if entry[1] == path]
            if not matching or not all(entry[2] == source_value for entry in matching):
                failures.append("%s:%s" % (section_id, path))
                continue
            if not any(_body_has_metric_value(section, metric, source_value, output) for metric, _, _ in matching):
                failures.append("%s:%s body" % (section_id, path))
    return failures


def _data_accuracy(output, case):
    source = case.get("mock_source_data", {})
    checks = case.get("ground_truth", {}).get("data_accuracy_checks", [])
    failures = _required_data_failures(output, case)
    actual = []
    for check in checks:
        path, expected = check.get("source_path"), check.get("expected_value")
        if path == "衍生计算":
            related = _value_at(source, "alert_stats.vuln_related_alerts")
            total = _value_at(source, "alert_stats.total")
            source_value = related / total if isinstance(related, Number) and total else None
            matching = [
                (section, metric, value)
                for section in _sections(output) if isinstance(section, dict)
                for metric, source_path, value in _entries(section)
                if metric == path and source_path.startswith("derived:")
            ]
            value_ok = source_value is not None and abs(source_value - float(expected)) <= 0.001
            output_ok = bool(matching) and all(
                isinstance(value, Number) and abs(value - source_value) <= 0.001
                and _body_has_metric_value(section, metric, value, output)
                for section, metric, value in matching
            )
            observed = {"computed": source_value, "data_values": [value for _, _, value in matching]}
        else:
            source_value = _value_at(source, path)
            matching = [
                (section, metric, value)
                for section in _sections(output) if isinstance(section, dict)
                for metric, source_path, value in _entries(section)
                if source_path == path
            ]
            value_ok = source_value == expected
            output_ok = bool(matching) and all(
                value == source_value and _body_has_metric_value(section, metric, source_value, output)
                for section, metric, value in matching
            )
            observed = {"source_value": source_value, "data_values": [value for _, _, value in matching]}
        actual.append({"metric": check.get("metric"), **observed})
        if not (value_ok and output_ok):
            failures.append(check.get("metric", path))
    for section in _sections(output):
        if not isinstance(section, dict) or not isinstance(section.get("body"), str):
            continue
        metric_names = [metric for metric, _, _ in _entries(section)]
        for line in section["body"].splitlines():
            if line.lstrip().startswith("#") or not re.search(r"\d", line):
                continue
            if "：" in line or ":" in line:
                if not any(metric in line for metric in metric_names):
                    failures.append("unbound body declaration " + line.strip())
    return _result(not failures, "all declared metrics match source data" if not failures else "metric mismatch: " + ", ".join(failures), checks, actual)


def _template_completeness(output, case):
    expected = case.get("ground_truth", {}).get("expected_sections", [])
    sections = output.get("content", {}).get("sections", []) if isinstance(output, dict) else []
    ids = [item.get("section_id") for item in sections if isinstance(item, dict)]
    nonempty = all(isinstance(item, dict) and isinstance(item.get("body"), str) and item["body"].strip() for item in sections)
    placeholders = [item.get("section_id") for item in sections if isinstance(item, dict) and _PLACEHOLDER.search(item.get("body", ""))]
    missing_data = _required_data_failures(output, case)
    passed = ids == expected and nonempty and not placeholders and not missing_data
    return _result(passed, "all required sections are present and complete" if passed else "section ids, bodies, placeholders, or required data are invalid", expected, {"section_ids": ids, "placeholders": placeholders, "missing_required_data": missing_data})


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
        if not headings:
            errors.append("missing Markdown heading in %s" % section.get("section_id"))
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
    sections = _sections(output)
    # ``data_values`` and ``masking_applied.original`` are internal audit
    # records.  They are deliberately not part of the management-visible report
    # scan; otherwise a compliant masking audit would be falsely flagged.
    management_view = {
        "report_title": output.get("report_title") if isinstance(output, dict) else None,
        "target_recipients": output.get("target_recipients") if isinstance(output, dict) else None,
        "content": [
            {
                "title": section.get("title"),
                "body": section.get("body"),
                "data_source_mapping": section.get("data_source_mapping"),
            }
            for section in sections if isinstance(section, dict)
        ],
        "metadata": output.get("metadata") if isinstance(output, dict) else None,
    }
    rendered = json.dumps(management_view, ensure_ascii=False, sort_keys=True, default=str)
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
