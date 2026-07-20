from __future__ import annotations

import json


PROMPT_VERSION = "scenario-04-security-briefing-v1"

SYSTEM_PROMPT = """你是安全简报生成 Agent。只能依据用户消息提供的 mock_source_data 生成报告，不能编造数据。
严格输出单个 JSON 对象，不要 Markdown 代码围栏。输出必须满足用户消息中的 report_output_contract；
target_channel 和 target_recipients 必须与 push_config 完全一致，并按 masking_rules 对敏感信息脱敏。
每个模板章节的 required_data 都必须在该章节 data_source_mapping 中出现：键为稳定指标名、值为对应源字段路径；
data_values 必须使用同一指标名保存未格式化的实际源值，正文必须以该指标名明确展示对应值或其记录的脱敏值。"""


def build_agent_messages(case: dict) -> list[dict]:
    """Build the complete, self-contained request sent to an LLM provider."""
    payload = {
        "request": case.get("input", {}),
        "report_type": case.get("report_type"),
        "target_audience": case.get("target_audience"),
        "mock_source_data": case.get("mock_source_data", {}),
        "template_definition": case.get("template_definition", {}),
        "push_config": case.get("push_config", {}),
        "masking_constraints": {
            "rules": case.get("push_config", {}).get("masking_rules", {}),
            "sensitive_patterns": case.get("ground_truth", {}).get("sensitive_patterns", []),
        },
        "report_output_contract": {
            "report_title": "string",
            "report_type": "daily|weekly|monthly|special",
            "target_audience": "security_lead|management|both",
            "target_channel": "email|slack|dingtalk|wecom",
            "target_recipients": ["string"],
            "content": {"sections": [{
                "section_id": "string",
                "title": "string",
                "body": "Markdown",
                "data_source_mapping": {"metric_name": "source.field.path"},
                "data_values": {"metric_name": "actual JSON value from source.field.path"},
            }]},
            "masking_applied": [{"original": "string", "masked": "string", "rule": "string"}],
            "metadata": {"generated_at": "ISO-8601 string", "data_sources_used": ["string"], "push_status": "draft"},
        },
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
