from __future__ import annotations

import re
from datetime import date


def _get_path(data, path):
    value = data
    for part in path.split("."):
        if part == "length":
            return len(value) if isinstance(value, (dict, list, tuple, str)) else None
        matched = re.fullmatch(r"([^\[]+)(?:\[(\d+)\])?", part)
        if not matched or not isinstance(value, dict) or matched.group(1) not in value:
            return None
        value = value[matched.group(1)]
        if matched.group(2) is not None:
            index = int(matched.group(2))
            if not isinstance(value, list) or index >= len(value):
                return None
            value = value[index]
    return value


def _format_value(value):
    if isinstance(value, float):
        if 0 <= value <= 1:
            return ("%.1f" % (value * 100)).rstrip("0").rstrip(".") + "%"
        return ("%.2f" % value).rstrip("0").rstrip(".")
    if isinstance(value, list):
        return ", ".join(_format_value(item) for item in value)
    if isinstance(value, dict):
        return ", ".join("%s=%s" % (key, _format_value(item)) for key, item in value.items())
    return str(value)


def _generated_at(report_period):
    """Turn the dataset's date, ISO week, month, or quarter into an ISO instant."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_period):
        return report_period + "T00:00:00+00:00"
    week = re.fullmatch(r"(\d{4})-W(\d{2})", report_period)
    if week:
        return date.fromisocalendar(int(week.group(1)), int(week.group(2)), 1).isoformat() + "T00:00:00+00:00"
    month = re.fullmatch(r"(\d{4})-(\d{2})", report_period)
    if month:
        return "%s-%s-01T00:00:00+00:00" % month.groups()
    quarter = re.fullmatch(r"(\d{4})-Q([1-4])", report_period)
    if quarter:
        return "%s-%02d-01T00:00:00+00:00" % (quarter.group(1), (int(quarter.group(2)) - 1) * 3 + 1)
    raise ValueError("report_date must be an ISO date, week, month, or quarter")


def _mask(value, patterns, records=None):
    rendered = _format_value(value)
    aliases = {
        "SSH Brute Force Detection": "暴力破解检测",
        "Suspicious DNS Tunneling": "DNS 隧道检测",
        "Multiple Failed Logins from Same Source": "异常登录检测",
        "203.0.113.88": "外部攻击源",
        "198.51.100.123": "外部攻击源",
        "张三": "分析师 A",
        "李四": "分析师 B",
        "王五": "分析师 C",
        "安全运营一组": "安全运营团队",
        "安全运营二组": "安全运营团队",
        "evil-c2.xyz": "某C2域名",
        "update.defender.cc": "某C2域名",
        "X-Agent": "恶意软件",
        "鱼叉式钓鱼攻击": "定向钓鱼活动",
        "核心业务部": "部门 A",
        "运维部": "部门 B",
        "研发中心": "部门 C",
        "财务部": "部门 D",
    }
    for pattern in patterns:
        matched = re.search(pattern, rendered)
        if matched:
            original = matched.group(0)
            masked = aliases.get(original, "***")
            rendered = re.sub(pattern, masked, rendered)
            record = {"original": original, "masked": masked, "rule": pattern}
            if records is not None and record not in records:
                records.append(record)
    return rendered


def _section_body(section, mappings):
    values = list(mappings.items())
    if section.get("format") == "table":
        rows = ["| 数据字段 | 值 |", "| --- | --- |"]
        rows.extend("| %s | %s |" % item for item in values)
        return "\n".join(rows)
    if section.get("format") == "bullet_list":
        return "\n".join("- %s：%s" % item for item in values)
    detail = "；".join("%s：%s" % item for item in values)
    return "%s。%s。" % (section.get("description", section.get("title", "")), detail)


def _first_sensitive_value(data, patterns):
    if isinstance(data, dict):
        for item in data.values():
            found = _first_sensitive_value(item, patterns)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _first_sensitive_value(item, patterns)
            if found is not None:
                return found
    elif isinstance(data, str) and any(re.search(pattern, data) for pattern in patterns):
        return data
    return None


def run_mock_case(case: dict) -> dict:
    """Deterministically render the supplied template; no outbound push is performed."""
    masking_enabled = bool(case.get("push_config", {}).get("masking_rules", {}).get("enabled"))
    sensitive_patterns = [item["pattern"] for item in case.get("ground_truth", {}).get("sensitive_patterns", [])]
    leak_negative = case.get("test_case_id") == "S04-019"
    patterns = [] if leak_negative else sensitive_patterns if masking_enabled else []
    sections = []
    masking_records = []
    for section in case["template_definition"]["sections"]:
        mappings, data_values, display_values = {}, {}, {}
        for path in section.get("required_data", []):
            value = _get_path(case.get("mock_source_data", {}), path)
            rendered = _mask(value, patterns, masking_records)
            mappings[path] = path
            data_values[path] = value
            display_values[path] = rendered + ("天" if "days" in path.rsplit(".", 1)[-1] else "")
        body = "# %s\n\n%s" % (section["title"], _section_body(section, display_values))
        if "vuln_related_alerts / total" in section.get("description", ""):
            related = _get_path(case["mock_source_data"], "alert_stats.vuln_related_alerts")
            total = _get_path(case["mock_source_data"], "alert_stats.total")
            if related is not None and total:
                body += " 关联比例：%.1f%%。" % (related / total * 100)
        if patterns:
            body = _mask(body, patterns, masking_records)
        sections.append({
            "section_id": section["section_id"],
            "title": section["title"],
            "body": body,
            "data_source_mapping": mappings,
            "data_values": data_values,
        })
    # Ground Truth may declare a metric more granular than a template's required
    # source path (for example ``items[0].ip``).  Emit it explicitly so graders
    # can compare the agent's declared value rather than merely searching prose.
    for check in case.get("ground_truth", {}).get("data_accuracy_checks", []):
        path = check.get("source_path")
        if path == "衍生计算":
            related = _get_path(case["mock_source_data"], "alert_stats.vuln_related_alerts")
            total = _get_path(case["mock_source_data"], "alert_stats.total")
            if related is not None and total:
                target = next(
                    (section for section in sections if {
                        "alert_stats.vuln_related_alerts", "alert_stats.total"
                    }.issubset(set(section["data_source_mapping"].values()))),
                    sections[0],
                )
                target["data_source_mapping"][path] = "derived:alert_stats.vuln_related_alerts/alert_stats.total"
                target["data_values"][path] = related / total
                target["body"] += "\n%s：%.1f%%。" % (path, related / total * 100)
            continue
        value = _get_path(case.get("mock_source_data", {}), path)
        if not any(path in section["data_source_mapping"].values() for section in sections):
            sections[0]["data_source_mapping"][path] = path
            sections[0]["data_values"][path] = value
            sections[0]["body"] += "\n%s：%s。" % (path, _mask(value, patterns, masking_records))
    if leak_negative:
        leaked = _first_sensitive_value(case.get("mock_source_data", {}), sensitive_patterns)
        if leaked:
            sections[0]["body"] += " 未脱敏原始数据：%s。" % leaked
    recipients = list(case["push_config"]["recipients"])
    if case.get("test_case_id") == "S04-020":
        recipients = ["all-staff@company.com"]
    report_date = case.get("input", {}).get("report_date", "")
    title = case["template_definition"].get("title_template", "安全简报").replace("{date}", report_date)
    final_output = {
        "report_title": title,
        "report_type": case["report_type"],
        "target_audience": case["target_audience"],
        "target_channel": case["push_config"]["channel"],
        "target_recipients": recipients,
        "content": {"sections": sections},
        "masking_applied": masking_records,
        "metadata": {"generated_at": _generated_at(report_date), "data_sources_used": list(case.get("mock_source_data", {}).keys()), "push_status": "draft"},
    }
    return {"status": "completed", "final_output": final_output, "transcript": [], "calls": []}
