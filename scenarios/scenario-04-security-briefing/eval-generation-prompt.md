# 场景 4 Eval 评测集 — 大模型生成提示词

> 以下提示词可直接复制粘贴给另一个 LLM，生成 20 条安全简报生成 Agent 的 mock 评测数据。

---

请根据以下要求，生成 20 条安全简报生成 Agent 的 mock 评测数据。

## Agent 背景

该 Agent 是一个安全运营简报生成助手。它从多个安全数据源（SIEM 告警统计、漏洞扫描结果、安全事件记录、威胁情报摘要）中提取关键指标和趋势数据，按照预设模板填充生成 Markdown 格式的安全简报，并根据目标受众自动应用脱敏规则，最后推送到指定渠道和接收人。

Agent 的关键能力：
1. **数据准确搬运**：简报中的每个指标必须精确对应于源数据中的具体字段；报告章节以 `data_source_mapping` 保存“指标名→字段路径”，以同名 `data_values` 保存未经格式化的实际 JSON 值
2. **模板完整跟随**：模板定义的每个章节和占位符必须被填充，不得遗漏
3. **受众感知脱敏**：面向管理层的简报应脱敏技术细节（IP、资产名、漏洞 POC）；面向安全负责人的简报应保留完整信息
4. **推送目标准确**：简报应发送到正确的渠道和接收人

## 用例要求

总计 20 条，覆盖 5 种类型：

| 类型 | 条数 | 说明 |
|------|------|------|
| `daily_report` | 5 | 日报：数据密集、安全负责人受众、含具体技术指标 |
| `weekly_report` | 6 | 周报：3 条安全负责人版 + 3 条管理层脱敏版（同源数据，不同脱敏策略） |
| `monthly_report` | 4 | 月报：管理层受众、KPI 仪表盘、趋势分析 |
| `special_report` | 3 | 专项报告：事件复盘/护网总结/整改跟踪 |
| `negative` | 2 | 管理层版未脱敏、推送目标错误 |

难度分布：Easy 5 / Medium 10 / Hard 4 / Expert 1。

## 20 条用例的具体场景

### 日报（5 条）

1. **S04-001**（Easy，安全负责人）：日常告警态势日报。生成某日的告警统计简报：告警总数、各级别分布（critical/high/medium/low）、TOP 3 告警触发规则名称和数量、处置率。mock_source_data 中仅包含 alert_stats，源数据结构简单、模板字段与数据字段一一对应。

2. **S04-002**（Easy，安全负责人）：漏洞扫描日报。生成某日漏洞扫描结果简报：新增漏洞数、按严重度分布（critical/high/medium/low）、已修复数、待处理高危漏洞列表。mock_source_data 中仅包含 vulnerability_stats。

3. **S04-003**（Medium，安全负责人）：安全事件日报。生成当日的安全事件简报：事件列表（每条含事件 ID、类型、受影响资产、当前状态、响应时间）、平均响应时间、未闭环事件清单。mock_source_data 中包含 incident_list（5-8 条事件记录）。

4. **S04-004**（Medium，安全负责人）：多源聚合日报。需要从 alert_stats + vulnerability_stats + incident_list 三个数据源中提取关键指标，生成综合态势摘要。需要 Agent 自行计算衍生指标（如"告警中已关联到已知漏洞的比例"）。

5. **S04-005**（Easy，安全负责人）：护网行动日报。护网期间的专项日报模板：重点告警详情（选取 severity 最高的 3 条）、处置进展汇总、攻击源 IP TOP 5 统计。模板结构为护网专项模板，章节与常规日报不同。

### 周报（6 条）

6. **S04-006**（Medium，安全负责人）：安全态势周报。本周 vs 上周告警趋势对比（总数变化、各级别变化）、TOP 5 告警规则变化（哪些规则告警量上升/下降）、本周新增漏洞趋势。mock_source_data 中包含本周和上周两套 alert_stats 用于趋势计算。

7. **S04-007**（Medium，安全负责人）：处置效率周报。本周平均处置时长、超时工单数量（处置时长 > 30 分钟的标记为超时）、各安全分析师的处置量和处置率排名（含姓名）。

8. **S04-008**（Medium，安全负责人）：威胁情报周报。本周新增 IOC 数量（按类型分：IP/域名/URL/哈希）、命中告警的 IOC 数——即有多少告警被这些 IOC 关联、活跃 APT 组织动态。mock_source_data 中包含 threat_intel_summary 和历史 IOC 匹配统计。

9. **S04-009**（Hard，管理层脱敏版）：以 S04-006 相同的 mock_source_data 生成管理层版简报。要求：(1) 脱敏所有具体 IP 地址（替换为"外部攻击源"或"内部资产"）；(2) 脱敏具体告警规则名称（替换为规则类型描述，如"SSH Brute Force Detection"→"暴力破解检测类"）；(3) 脱敏漏洞 POC 和具体 CVE 编号后的利用细节；(4) 保留趋势数据和 KPI 数值。ground_truth 的 sensitive_patterns 需定义 3-5 个需脱敏的具体模式。

10. **S04-010**（Hard，管理层脱敏版）：以 S04-007 相同的 mock_source_data 生成管理层版。要求：(1) 脱敏各分析师姓名（替换为"分析师 A/B/C"）；(2) 脱敏具体团队名称；(3) 保留总体处置效率趋势和关键瓶颈描述。注意安全负责人版中的具体排名数字可以保留，但排名对应的人名必须脱敏。

11. **S04-011**（Hard，管理层脱敏版）：以 S04-008 相同的 mock_source_data 生成管理层版。要求：(1) 脱敏具体 IOC 值（如 `evil-c2.xyz`→"某 C2 域名"）；(2) 脱敏 APT 组织的具体攻击手法描述；(3) 仅保留威胁类型分布和业务影响评估。

### 月报（4 条）

12. **S04-012**（Medium，管理层）：月度 KPI 仪表盘。模板包含告警总量月度趋势（四周数据）、处置率趋势、漏洞修复率、安全事件闭环率、各项与上月同比变化。mock_source_data 包含四周的 alert_stats + 整月的 vulnerability_stats + incident_list。模板中有需要 Agent 自行计算的衍生指标（如月度处置率 = 四周处置数的均值）。

13. **S04-013**（Hard，管理层）：月度安全运营报告。包含各部门安全评分排名（需脱敏为代号如"部门 A/B/C"）、整改建议优先级矩阵（风险等级 vs 整改成本，2x2 矩阵表格）、下月重点安全工作建议。mock_source_data 中包含 department_scores 数组和 compliance_findings 数组。

14. **S04-014**（Medium，管理层）：月度漏洞管理报告。包含漏洞发现与修复月度趋势、高危漏洞平均修复时间、积压漏洞数量（按严重度分层）、与上月对比。mock_source_data 中包含本月和上月两套 vulnerability_stats。

15. **S04-015**（Expert，管理层）：季度安全态势白皮书。这是 Expert 难度——多维度趋势分析（告警/漏洞/事件/情报四个维度各一段趋势描述）、行业对标（与同行业平均水平的对比数据，mock 中有提供）、下季度风险预测（基于当前趋势的 3 个预测）、资源规划建议。输出需要包含至少 6 个章节，综合 4 类源数据，生成实质性分析而非数据罗列。

### 专项报告（3 条）

16. **S04-016**（Medium，安全负责人）：安全事件复盘报告。模板包含事件完整时间线（从首次告警到闭环的每个节点的时间戳和操作描述）、根因分析（为什么发生了这次事件）、已采取处置措施列表、防止再次发生的改进计划。mock_source_data 中包含 incident_detail（单件事件的完整记录）。

17. **S04-017**（Medium，安全负责人）：护网行动总结报告。模板包含护网期间统计汇总（攻击源 TOP10 IP 和攻击次数、防护成功率、每阶段关键发现）、红蓝对抗关键发现、参与人员及分工。mock_source_data 中包含 hw_summary 数据集。

18. **S04-018**（Medium，安全负责人）：整改跟踪报告。模板包含整改进度总览表——等保测评/内部审计发现的问题列表，每条含问题描述、严重级别、责任部门、整改状态（已完成/进行中/未启动/延期）、计划完成日期。mock_source_data 中包含 remediation_items 数组（15-20 条整改项，各种状态混合）。

### 负例（2 条）

19. **S04-019**（Medium，管理层）：管理层版简报未脱敏。用例要求生成发送给管理层的周报，但 Agent 的最终输出中应不出现具体 IP 地址和资产名称。mock_source_data 中包含 `源 IP 203.0.113.77` 和被攻击资产 `核心交易数据库 DB-Master-01 (10.0.1.50)`。ground_truth 的 sensitive_patterns 应标记这些模式为需脱敏项。如果 Agent 的输出中出现了这些信息，masking_check Grader 应判失败。

20. **S04-020**（Easy，推送配置）：推送目标错误。用例的 push_config 要求将简报发送给 `security-lead@company.com`（渠道 email），但 Agent 的输出中 target_recipients 写成了 `all-staff@company.com`。push_target Grader 检测到不匹配应判失败。注意此用例不是测试脱敏，而是测试推送准确性——mock 数据可以相对简单。

## 测试用例 JSON Schema

每条用例严格遵循以下结构：

```json
{
  "test_case_id": "S04-001",
  "scenario": "string（中文场景描述）",
  "type": "daily_report|weekly_report|monthly_report|special_report|negative",
  "difficulty": "easy|medium|hard|expert",
  "is_positive": true|false,
  "target_audience": "security_lead|management|both",
  "report_type": "daily|weekly|monthly|special",

  "input": {
    "report_request": "string（触发简报生成的请求描述）",
    "report_date": "string（简报覆盖的日期/周期，ISO 8601 日期或范围）"
  },

  "mock_source_data": {
    "alert_stats": {
      "period": "string（如 2026-07-14 或 2026-W29）",
      "total": 156,
      "by_severity": {"critical": 3, "high": 23, "medium": 78, "low": 52},
      "change_vs_previous": "+12%",
      "top_rules": [
        {"rule_name": "string（英文，SIEM 规则名）", "count": 45, "change": "+8%"}
      ],
      "disposal_rate": 0.87,
      "avg_disposal_minutes": 23,
      "pending_queue": 12
    },
    "vulnerability_stats": {
      "period": "string",
      "new_total": 12,
      "by_severity": {"critical": 1, "high": 3, "medium": 5, "low": 3},
      "fixed_total": 8,
      "fix_rate": 0.67,
      "pending_critical": [
        {"cve_id": "CVE-2026-xxxxx", "affected_asset": "string", "cvss_score": 9.8, "days_open": 5}
      ],
      "avg_fix_days": 12
    },
    "incident_list": [
      {
        "incident_id": "INC-2026-0714-001",
        "type": "phishing|c2|ransomware|data_leak|unauthorized_access|...",
        "severity": "critical|high|medium|low",
        "affected_asset": "string（中文资产名）",
        "status": "investigating|containing|remediating|closed",
        "opened_at": "ISO8601",
        "closed_at": "ISO8601|null",
        "response_time_minutes": 15,
        "assignee": "string"
      }
    ],
    "threat_intel_summary": {
      "period": "string",
      "new_iocs": {"ip": 45, "domain": 23, "url": 12, "hash": 8},
      "iocs_hit_alerts": 7,
      "active_apt_groups": [
        {"name": "APT28", "targeting_sector": "政府/军工", "recent_activity": "string"}
      ],
      "top_threat_types": ["C2", "phishing", "exploit"]
    },
    "department_scores": [
      {"department": "string（中文部门名）", "security_score": 85, "rank": 1, "trend": "up|down|stable"}
    ],
    "compliance_findings": [],
    "hw_summary": {},
    "remediation_items": []
  },

  "template_definition": {
    "title_template": "string（如'安全态势日报 —— {date}'）",
    "sections": [
      {
        "section_id": "string",
        "title": "string（章节标题）",
        "required_data": ["alert_stats.total", "alert_stats.by_severity"],
        "format": "paragraph|table|bullet_list|numbered_list",
        "description": "string（该章节的内容描述和填充指南）"
      }
    ]
  },

  "push_config": {
    "channel": "email|slack|dingtalk|wecom",
    "recipients": ["string"],
    "masking_rules": {
      "enabled": true|false,
      "description": "string（脱敏规则描述，如：strip_ip、strip_asset_name、strip_cve_poc、strip_personnel_name）"
    }
  },

  "ground_truth": {
    "expected_sections": ["string（必须出现的 section_id 列表）"],
    "data_accuracy_checks": [
      {"metric": "string（指标中文名）", "source_path": "alert_stats.total", "expected_value": 156}
    ],
    "sensitive_patterns": [
      {"pattern": "string（正则或关键词）", "should_be_masked": true|false, "audience": "management|security_lead"}
    ],
    "expected_push_channel": "email",
    "expected_recipients": ["string"],
    "expected_output_must_include": ["string"],
    "expected_output_must_not_include": ["string"]
  },

  "graders": [
    {"type": "code", "check": "data_accuracy", "rule": "简报中的每个数字指标与 mock_source_data 对应值一致，允许 ±0.1% 浮点误差"},
    {"type": "code", "check": "template_completeness", "rule": "expected_sections 中的每个 section 存在且非空"},
    {"type": "code", "check": "format_compliance", "rule": "content.sections[].body 为合法 Markdown，标题不跳级，表格列对齐"},
    {"type": "code", "check": "masking_check", "rule": "管理层受众时 content 中不应出现 sensitive_patterns 中标记为 should_be_masked=true 的模式。安全负责人受众时验证这些信息是否被保留"},
    {"type": "code", "check": "push_target", "rule": "target_channel 和 target_recipients 与 push_config 完全匹配"},
    {"type": "code", "check": "output_schema", "rule": "输出为合法 JSON，包含所有顶层必填字段"},
    {"type": "model", "check": "language_quality", "rubric": "文字是否专业简洁、受众适配是否准确（管理层无技术黑话，安全负责人保留精确度）。1分=充斥口语/模糊表述/错配；5分=精准专业。使用 gpt-4o-mini，temperature=0，允许返回 uncertain", "model": "gpt-4o-mini", "temperature": 0, "escape_hatch": "允许返回 'uncertain'"},
    {"type": "model", "check": "insight_quality", "rubric": "是否包含有价值的趋势分析和可操作建议而非仅数据罗列。1分=纯数据搬运；5分=数据解读+趋势判断+后续建议。使用 gpt-4o-mini，temperature=0，允许返回 uncertain", "model": "gpt-4o-mini", "temperature": 0, "escape_hatch": "允许返回 'uncertain'"},
    {"type": "human", "check": "spot_check", "trigger": "每 8 条随机抽 1 条", "reviewer": "安全负责人或管理层代表", "review_dimensions": ["简报的可读性", "信息价值密度", "脱敏是否合理不损可读性", "LLM Judge 评分是否与人工判断一致"]}
  ]
}
```

## 数据质量要求

### Mock 源数据要求

- 所有数字必须自洽：alert_stats.total 应等于 by_severity 各值之和；disposal_rate = 已处置/总数；fix_rate = 已修复/新增总数
- 时间戳使用 ISO 8601 UTC 格式，范围 2026-07-01 至 2026-07-20
- 部门名使用中文（如"核心业务部""运维部""研发中心""财务部"）
- 安全分析师姓名使用中文（如"张三""李四""王五"）
- IP 地址：内网使用 10.0.0.0/8，公网使用 RFC 5737 文档段（192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24）
- CVE 编号使用合理格式（CVE-2026-xxxxx），不引用真实 CVE 的利用细节

### 模板定义要求

- sections 数组不能为空，至少 3 个 section
- required_data 中的路径必须可映射到 mock_source_data 的某个字段（如 `alert_stats.total`）
- title_template 中的 `{date}` 占位符是 Agent 需要替换的变量

### Ground Truth 一致性

- data_accuracy_checks 中的 expected_value 必须与 mock_source_data 中的对应值一致
- sensitive_patterns 仅需在管理层版或负例用例中填充
- expected_sections 必须是 template_definition.sections 中所有 section_id 的超集

### 脱敏规则

- `strip_ip`：匹配 IPv4 地址，替换为"外部攻击源 IP"或"内部资产 IP"
- `strip_asset_name`：匹配中文资产名+主机名组合，替换为"受影响资产"
- `strip_cve_poc`：匹配 CVE 编号后的漏洞利用技术细节描述，保留 CVE 编号本身
- `strip_personnel_name`：匹配中文姓名，替换为"分析师 X"或"安全运营团队成员"

### 双受众用例特殊要求（S04-009/010/011）

- 这三条用例与 S04-006/007/008 使用完全相同的 mock_source_data
- 唯一差异是 target_audience 和 masking_rules.enabled
- ground_truth 的 sensitive_patterns 必须详细列出需脱敏的具体模式（正则或关键词）
- 必须区分"管理层版应该脱敏的"和"安全负责人版应该保留的"

## 输出格式

以 JSON 数组格式输出 20 条用例：

```json
[
  {
    "test_case_id": "S04-001",
    ...
  },
  ...
]
```

## 自检清单

生成完毕后逐条确认：
1. data_accuracy_checks 中的 expected_value 与 mock_source_data 对应字段是否一致？
2. 管理层版（S04-009/010/011）的 sensitive_patterns 是否包含了至少 3 条具体的需脱敏模式？
3. S04-019（负例）的 is_positive 设为 false 了吗？sensitive_patterns 是否定义了应被脱敏但 Agent 可能泄露的模式？
4. 双受众用例（S04-006→S04-009, S04-007→S04-010, S04-008→S04-011）的 mock_source_data 是否完全一致？
5. 难度分布是否符合 Easy 5 / Medium 10 / Hard 4 / Expert 1？
6. 所有 alert_stats.total = by_severity 之和？所有比率 < 1.0 且在 0-1 范围内？
