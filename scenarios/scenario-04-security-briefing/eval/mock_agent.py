from __future__ import annotations

import re


def _get_path(data, path):
    value = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
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


def _mask(value, patterns):
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
        rendered = re.sub(pattern, aliases.get(matched.group(0), "***") if matched else "***", rendered)
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
    for section in case["template_definition"]["sections"]:
        mappings = {}
        for path in section.get("required_data", []):
            value = _get_path(case.get("mock_source_data", {}), path)
            rendered = _mask(value, patterns)
            mappings[path] = rendered + ("天" if "days" in path.rsplit(".", 1)[-1] else "")
        body = _section_body(section, mappings)
        if "vuln_related_alerts / total" in section.get("description", ""):
            related = _get_path(case["mock_source_data"], "alert_stats.vuln_related_alerts")
            total = _get_path(case["mock_source_data"], "alert_stats.total")
            if related is not None and total:
                body += " 关联比例：%.1f%%。" % (related / total * 100)
        if patterns:
            body = _mask(body, patterns)
        sections.append({
            "section_id": section["section_id"],
            "title": section["title"],
            "body": body,
            "data_source_mapping": mappings,
        })
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
        "masking_applied": ["management masking rules applied"] if masking_enabled and not leak_negative else [],
        "metadata": {"generated_at": "%sT00:00:00+00:00" % report_date, "data_sources_used": list(case.get("mock_source_data", {}).keys()), "push_status": "draft"},
    }
    return {"status": "completed", "final_output": final_output, "transcript": [], "calls": []}
