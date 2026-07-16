# 场景一 Eval 数据核心标签说明

## 1. 这份文档解决什么问题

`Eval-data_v1.json` 是场景一当前正式使用的 30 条评测用例。每条用例同时包含告警输入、预置的工具返回、评分用 Ground Truth 和 Grader 配置。

前场实现 Agent 时，模型只能看到告警输入和允许提供的工具结果；`ground_truth` 和评分规则属于答案侧数据，不得放进 Agent Prompt。本说明用于帮助开发人员读懂字段、生成兼容输出，并在需要时安全扩充用例。

## 2. 文件关系

| 文件 | 定位 | 是否直接运行 |
|---|---|---:|
| `Eval-data_0.json` | 原始生成基线，用于保留数据来源 | 否 |
| `calibrate_eval_data.py` | 从 v0 确定性生成 v1 的校准脚本 | 是 |
| `Eval-data_v1.json` | 校准后的正式评测集 | 是 |
| `tests/test_eval_data_v1.py` | 数据契约和分布回归测试 | 是 |

日常评测读取 v1。需要修改数据时，应修改明确的数据来源或校准规则，再重新生成并测试 v1，不建议只手工改最终文件而不留下可复现路径。

## 3. 单条用例总览

```json
{
  "test_case_id": "A01",
  "scenario": "SSH 暴力破解并成功登录核心资产",
  "difficulty": "easy",
  "is_positive": true,
  "expected_severity": "critical",
  "expected_attack_type": "brute_force",
  "input": {},
  "mock_api_responses": {},
  "ground_truth": {},
  "graders": []
}
```

这五部分的职责是：

1. 顶层字段定义用例身份和主要分类标签；
2. `input` 模拟告警触发；
3. `mock_api_responses` 模拟安全平台返回；
4. `ground_truth` 保存专家期望；
5. `graders` 声明如何评分。

## 4. 顶层身份与分类标签

| 字段 | 类型/允许值 | 说明 |
|---|---|---|
| `test_case_id` | `A01`–`A30` | 用例唯一 ID。checkpoint、CSV 和 JSON 报告都依赖该字段 |
| `scenario` | string | 面向人的场景摘要，不作为唯一评分依据 |
| `difficulty` | `easy|medium|hard|expert` | 用例推理难度，用于分层统计，不等同于严重级别 |
| `is_positive` | boolean | `true` 表示真实威胁或应处置事件；`false` 表示误报/正常活动类负例 |
| `expected_severity` | `critical|high|medium|low|false_positive` | 专家标注的最终严重级别，用于 `severity_match` 和准确率 |
| `expected_attack_type` | string | 专家标注的攻击类型；负例统一为 `none` |

### 4.1 `difficulty` 不代表风险

`expert` 表示研判需要更多上下文或更复杂的证据组合，不代表结果一定是 `critical`。同样，`easy` 用例也可能是严重威胁。

### 4.2 `is_positive` 不代表“是否产生过告警”

30 条数据都是由告警触发的。`is_positive=false` 表示经过上下文核验后应判断为误报或正常活动，而不是没有告警。

### 4.3 `expected_severity` 与嵌套严重度

顶层 `expected_severity` 是汇总和 Code Grader 使用的标准字段。`ground_truth.expected_judgment.severity` 应与它保持一致，数据契约测试会检查二者同步。

## 5. `input`：Agent 可见的触发输入

```json
{
  "alert_id": "ALT-20260710-0001",
  "trigger_context": "SOC 推送：检测到 SSH 异常登录"
}
```

| 字段 | 说明 |
|---|---|
| `alert_id` | 传给告警详情工具的业务标识，Agent 输出应原样返回 |
| `trigger_context` | 启动分析时的简短告警描述，不包含完整研判答案 |

路线 A 会把 `trigger_context` 放入 Agent Prompt。真实 Agent 应把它当作触发上下文，而不是唯一证据来源。

## 6. `mock_api_responses`：预置工具返回

该对象的 key 采用“标准工具 ID + 参数标识”的形式，value 是对应工具返回。一个工具可以有多条响应，例如多个 IP 或 IOC。

| key 前缀 | 标准 Tool ID | 数据含义 |
|---|---|---|
| `query_alert_detail_` | `query_alert_detail` | 告警规则、原始日志、网络信息和初始 IOC |
| `query_asset_info_` | `query_asset_info` | 资产归属、重要性、网络区域和特殊角色 |
| `query_threat_intel_` | `query_threat_intel` | IOC 恶意性、信誉、标签、组织和情报置信度 |
| `query_related_alerts_` | `query_related_alerts` | 指定窗口内同资产或 IOC 的关联告警 |

例如：

```json
{
  "query_asset_info_10.0.1.20": {
    "ip": "10.0.1.20",
    "asset_level": "critical",
    "is_scanner": false,
    "is_bastion": false,
    "is_honeypot": false
  }
}
```

key 后缀用于区分多次预置查询，不是新的工具名。写入 `metadata.tools_called` 时只能写前缀对应的标准 Tool ID。

### 6.1 四类响应中的核心字段

- 告警详情：`severity_original` 只是来源平台初始级别，不能直接当最终答案；`raw_log`、`payload_highlights` 和 `related_iocs` 是主要证据。
- 资产信息：`asset_level` 影响业务冲击；`is_scanner`、`is_bastion`、`is_honeypot` 是误报研判的重要上下文，但仍需结合行为核验。
- 威胁情报：`is_malicious`、`reputation_score`、`threat_tags`、`associated_apt` 和 `confidence` 需要联合解释，不能只看一个字段。
- 关联告警：`total_related=0` 表示本次预置查询无结果，不代表工具调用失败。

## 7. `ground_truth`：只供评分使用的专家答案

> 重要：本对象及其任何派生提示都不得提供给被测 Agent。

| 字段 | 说明 |
|---|---|
| `expected_tools_called` | 数据设计时预期可使用的完整工具集合，用于分析覆盖情况 |
| `expected_tools_minimum` | 本条用例最低必须使用的工具集合，由 `tools_called_minimum` Grader 检查 |
| `expected_judgment` | 专家期望的严重度、攻击类型、最低置信度和证据要求 |
| `expected_remediation_must_include` | 处置建议应覆盖的关键动作或对象 |

### 7.1 `expected_tools_called` 与 `expected_tools_minimum`

前者描述完整设计路径，后者是最低验收条件。不同用例的最低工具集合不同：有些更依赖资产身份，有些更依赖 IOC 情报，有些必须检查关联告警。因此不应把某一个固定工具组合硬编码为所有用例的唯一流程。

### 7.2 `expected_judgment`

```json
{
  "severity": "high",
  "attack_type": "credential_dump",
  "min_confidence": 0.8,
  "key_evidence_must_include": ["应覆盖的证据"],
  "key_evidence_must_not_include": ["不应出现的错误结论"]
}
```

- `severity`、`attack_type` 应与顶层标签一致；
- `min_confidence` 是专家期望下限，不等于要求模型固定输出该值；
- `key_evidence_must_include` 帮助检查证据完整性；
- `key_evidence_must_not_include` 用于防止关键误判或无依据结论。

## 8. `graders`：评分配置

每条正式用例包含 6 个 Code Grader、2 个 Model Grader 和 1 个人工抽检配置。

### 8.1 六个 Code Grader

| Grader | 检查内容 |
|---|---|
| `tools_called_minimum` | `metadata.tools_called` 是否包含本条 Ground Truth 要求的最低工具集合 |
| `output_schema` | 顶层和 `judgment` 必填字段是否存在 |
| `severity_enum` | 实际严重度是否属于合法枚举 |
| `severity_match` | 实际严重度是否等于顶层 `expected_severity` |
| `confidence_range` | 置信度是否为 0 到 1 的数值，布尔值不算数字 |
| `remediation_not_empty` | 是否至少有一条长度达到基本要求的处置建议 |

最容易混淆的是：

```text
severity_enum  = actual_severity 是否属于合法枚举
severity_match = actual_severity 是否等于 expected_severity
```

例如 Agent 输出 `critical`、Ground Truth 是 `high`：`severity_enum` 通过，但 `severity_match` 失败。场景一的 `severity_accuracy` 由 `severity_match` 计算，不能用枚举合法率替代研判准确率。

### 8.2 两个 Model Grader

- `judgment_quality`：实际分三次独立 Judge 调用，分别检查严重度合理性、处置可执行性和证据完整性；
- `hallucination_check`：逐条判断证据链陈述能否在 mock 数据中找到支撑。

Judge 可以返回不确定结果，避免在证据不足时被迫评分。Judge 评分是辅助诊断，正式校准仍应结合安全专家抽检。

### 8.3 人工抽检

`spot_check` 是人工复核触发配置。当前 Python Harness 不自动执行人工评分，它用于提醒正式评测过程按约定抽样。

## 9. Agent 必须返回的标签

```json
{
  "alert_id": "string",
  "judgment": {
    "severity": "critical|high|medium|low|false_positive",
    "attack_type": "string",
    "confidence": 0.0,
    "summary": "string",
    "evidence_chain": ["string"],
    "iocs": [
      {
        "type": "ip|domain|hash|url",
        "value": "string",
        "malicious": true,
        "context": "string"
      }
    ]
  },
  "remediation": ["string"],
  "metadata": {
    "tools_called": ["query_alert_detail"]
  }
}
```

| 字段 | 输出要求 |
|---|---|
| `alert_id` | 与输入一致 |
| `judgment.severity` | 使用五级枚举，并根据成功影响和资产上下文研判 |
| `judgment.attack_type` | 使用测试集约定类型；误报为 `none` |
| `judgment.confidence` | 0 到 1 的数值，体现证据强度与冲突 |
| `judgment.summary` | 一句话说明发生了什么、是否成功以及影响对象 |
| `judgment.evidence_chain` | 每条都应能追溯到工具返回，不写模型常识推断成的事实 |
| `judgment.iocs` | 只列本次告警涉及且有上下文的 IOC |
| `remediation` | 按优先级给出明确对象和动作，至少一条 |
| `metadata.tools_called` | 只列实际使用过的标准 Tool ID，不写产品名或中文名称 |

## 10. 精简示例

以下示例只展示字段关系，不是正式数据中的完整用例：

```json
{
  "test_case_id": "EXAMPLE-01",
  "scenario": "内部扫描器触发端口扫描告警",
  "difficulty": "easy",
  "is_positive": false,
  "expected_severity": "false_positive",
  "expected_attack_type": "none",
  "input": {
    "alert_id": "ALT-EXAMPLE-01",
    "trigger_context": "检测到内网主机端口扫描"
  },
  "mock_api_responses": {
    "query_alert_detail_ALT-EXAMPLE-01": {
      "alert_id": "ALT-EXAMPLE-01",
      "source_ip": "10.0.0.10",
      "destination_ip": "10.0.0.20"
    },
    "query_asset_info_10.0.0.10": {
      "ip": "10.0.0.10",
      "is_scanner": true,
      "is_bastion": false,
      "is_honeypot": false
    }
  },
  "ground_truth": {
    "expected_tools_called": ["query_alert_detail", "query_asset_info"],
    "expected_tools_minimum": ["query_alert_detail", "query_asset_info"],
    "expected_judgment": {
      "severity": "false_positive",
      "attack_type": "none",
      "min_confidence": 0.9,
      "key_evidence_must_include": ["源资产是授权扫描器"],
      "key_evidence_must_not_include": ["已确认横向移动"]
    },
    "expected_remediation_must_include": ["核对扫描任务并优化告警白名单"]
  },
  "graders": []
}
```

Agent 可以看到 `input`，并通过路线 A 获得 `mock_api_responses`；它不能看到示例中的 `ground_truth`。

## 11. 新增或修改用例的流程

1. 明确用例要测的单一核心能力，并判断属于正例还是负例；
2. 在原始数据或校准规则中维护变更，保留 v0 到 v1 的确定性生成路径；
3. 确保顶层标签与 `ground_truth.expected_judgment` 一致；
4. 使用 RFC 5737 文档 IP 和 RFC 1918 私网地址，避免放入真实业务数据；
5. 为实际存在的工具返回使用正确 key 前缀；
6. 配置 6 个 Code Grader、2 个 Model Grader 和人工抽检项；
7. 运行校准脚本和数据契约测试；
8. 先跑单条与 3 条冒烟，确认后再跑全量；
9. 新版本数据集应使用明确版本名和新的运行目录，不覆盖历史基线。

运行数据回归：

```bash
python3 calibrate_eval_data.py
python3 -m unittest tests/test_eval_data_v1.py -v
```

运行全部离线测试：

```bash
python3 -m unittest discover -s tests -v
```
