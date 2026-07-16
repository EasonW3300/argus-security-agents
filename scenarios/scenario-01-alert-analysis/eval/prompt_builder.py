import json


PROMPT_VERSION = "route-a-v2-tool-ids"
SYSTEM_PROMPT = """你是网络安全运营分析助手。仅根据已提供的工具查询结果进行研判。
严重度只能是 critical、high、medium、low、false_positive；扫描器、堡垒机、蜜罐或正常运维活动优先走误报核验。
证据链每条必须能追溯到输入；处置建议必须具体且按优先级排列。
请严格以 JSON 格式输出，不要包含 Markdown 代码围栏。输出结构必须是：
{"alert_id":"string","judgment":{"severity":"critical|high|medium|low|false_positive","attack_type":"string","confidence":0.0,"summary":"string","evidence_chain":["string"],"iocs":[{"type":"ip|domain|hash|url","value":"string","malicious":true,"context":"string"}]},"remediation":["string"],"metadata":{"tools_called":["string"]}}
metadata.tools_called 必须只使用用户消息“已执行工具标识”中提供的精确字符串；不得翻译、改写为产品名或数据源名；列出本次研判实际使用的已注入工具结果。"""

PREFIXES = [
    ("query_alert_detail", "告警详情"),
    ("query_asset_info", "资产信息"),
    ("query_threat_intel", "威胁情报"),
    ("query_related_alerts", "关联告警（48h 窗口）"),
]


def _dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def _dump_canonical(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _available_tools(responses):
    return [
        prefix
        for prefix, _ in PREFIXES
        if any(key.startswith(prefix) for key in responses)
    ]


def build_agent_messages(test_case):
    sections = []
    responses = test_case["mock_api_responses"]
    for prefix, title in PREFIXES:
        values = [
            value
            for key, value in sorted(responses.items())
            if key.startswith(prefix)
        ]
        if prefix == "query_related_alerts" and (
            not values or all(value.get("total_related") == 0 for value in values)
        ):
            body = "无关联告警"
        else:
            body = "\n\n".join(_dump(value) for value in values) if values else "无数据"
        sections.append("### %s（%s）\n%s" % (title, prefix, body))
    user = (
        "## 告警输入\n%s\n\n"
        "## 已执行工具标识\n%s\n\n"
        "## 工具查询结果\n\n%s\n\n"
        "## 任务\n请输出结构化 JSON 研判结论。"
        % (
            test_case["input"]["trigger_context"],
            json.dumps(_available_tools(responses), ensure_ascii=False),
            "\n\n".join(sections),
        )
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_judge_messages(test_case, agent_output, dimension):
    payload = {
        "mock_api_responses": test_case["mock_api_responses"],
        "agent_output": agent_output,
    }
    if dimension == "hallucination_check":
        instruction = (
            "逐条核对 evidence_chain。输出 "
            "{total_statements,verifiable,hallucinations,uncertain,"
            "details:[{statement,verdict,reason}]}，verdict 只能是 "
            "verifiable、hallucination、uncertain。顶层 uncertain 是整数计数；"
            "details 中 verdict 为 uncertain 表示该条陈述无法确定。"
        )
        uncertainty_instruction = ""
    else:
        rubrics = {
            "severity_rationality": "只评估严重度与输入证据是否一致",
            "remediation_actionability": "只评估处置建议是否具体、可执行并按优先级排列",
            "evidence_completeness": "只评估证据链是否覆盖关键 IOC 与行为特征",
        }
        instruction = (
            rubrics[dimension]
            + "。输出 {score:1-5或null,reason:string,evidence_quotes:[string]}。"
        )
        uncertainty_instruction = "无法确定 score 时使用 null；"
    system = (
        "你是安全评测 Judge。%s 必须引用输入证据；%s严格以 JSON 输出。"
        % (instruction, uncertainty_instruction)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _dump_canonical(payload)},
    ]
