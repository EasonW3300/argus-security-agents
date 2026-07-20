# 场景四 Agent 原型架构设计

## 1. 目标与范围

场景四是“任务简报生成及推送”Agent，负责根据报告请求、Mock 安全数据、简报模板和推送配置，生成一份结构化安全简报。

本阶段只验证 Agent 总体架构是否能够跑通 Eval，不实现真实的 SIEM、漏洞平台、工单系统、消息平台或定时任务。真实业务系统由后续前场实现替换。

原型必须覆盖：

- 从 Mock 源数据中提取并复述指标；
- 按模板生成完整章节；
- 输出合法 JSON，正文使用 Markdown；
- 根据受众执行或不执行敏感信息脱敏；
- 输出正确的推送渠道和接收人；
- 通过代码 Grader 和模型 Grader 进行自动评测；
- 支持 Qwen、DeepSeek 等 OpenAI-compatible 模型；
- 支持请求超时、逐条 checkpoint 和断点续跑。

不在本原型范围内：

- 真实数据源连接；
- 真实报告发送；
- 真实定时调度；
- 复杂多轮规划；
- 业务系统权限和审计平台集成。

## 2. 总体架构

采用路线 A：单轮结构化报告生成。

```text
用户报告请求
    │
    ▼
Eval Case Loader
    │  report_request / report_date
    ▼
Prompt Builder
    │  mock_source_data + template_definition + push_config
    │  audience / masking constraints / JSON contract
    ▼
Agent LLM Client
    │  Qwen / DeepSeek / OpenAI-compatible endpoint
    ▼
Structured Report Parser
    │
    ├── Code Graders
    │     ├── data_accuracy
    │     ├── template_completeness
    │     ├── format_compliance
    │     ├── masking_check
    │     ├── push_target
    │     └── output_schema
    │
    └── Model Graders
          ├── language_quality
          └── insight_quality
    ▼
Eval Report + Checkpoint
```

原型的 Agent 只有一个稳定接口：

```python
generate_report(case: dict) -> dict
```

真实前场 Agent 后续只需要替换该接口背后的实现，不需要改变 Eval 数据格式、Grader 或报告汇总逻辑。

## 3. 输入契约

每条 Eval 用例包含以下输入：

| 输入 | 作用 |
|---|---|
| `input.report_request` | 用户希望生成的报告任务 |
| `input.report_date` | 报告日期或统计周期 |
| `mock_source_data` | 模拟 SIEM、漏洞、事件、威胁情报等源数据 |
| `template_definition` | 标题模板、章节、字段和格式要求 |
| `push_config` | 渠道、接收人和脱敏规则 |
| `ground_truth` | 代码 Grader 使用的期望值、章节和敏感模式 |

Prompt 必须明确告诉模型：

1. 只能使用给定的 `mock_source_data`，不能编造指标；
2. 必须填充 `template_definition.sections` 中的每个章节；
3. 必须按 `push_config` 输出渠道和接收人；
4. 管理层视图必须执行脱敏，安全负责人视图按要求保留技术细节；
5. 只能返回约定的 JSON，不要返回 Markdown 代码围栏或额外解释。

## 4. 输出契约

Agent 必须返回：

```json
{
  "report_title": "string",
  "report_type": "daily|weekly|monthly|special",
  "target_audience": "security_lead|management|both",
  "target_channel": "email|slack|dingtalk|wecom",
  "target_recipients": ["string"],
  "content": {
    "sections": [
      {
        "section_id": "string",
        "title": "string",
        "body": "string，Markdown",
        "data_source_mapping": {
          "指标名": "源数据字段路径"
        },
        "data_values": {
          "指标名": "该路径的原始 JSON 值（内部评分审计用）"
        }
      }
    ]
  },
  "masking_applied": [
    {
      "original": "string",
      "masked": "string",
      "rule": "string"
    }
  ],
  "metadata": {
    "generated_at": "ISO8601",
    "data_sources_used": ["string"],
    "push_status": "sent|queued|draft"
  }
}
```

`section_id` 是评测稳定匹配章节的主键。`title` 用于展示，`body` 用于 Markdown 合规和数据准确性检查。`data_source_mapping` 固定为“指标名 → 源字段路径”，`data_values` 必须使用相同指标名保存该路径的未格式化实际 JSON 值；每个模板 `required_data` 都必须在对应章节中出现。对象和数组必须在正文中逐一展示所有标量叶子值，或展示 `masking_applied` 中记录的敏感叶子脱敏值；仅出现来源路径不构成内容完整性。脱敏替换仅适用于 `management` 受众且用例已启用脱敏，且 record 的 `original` 必须匹配 `ground_truth.sensitive_patterns` 中 `should_be_masked=true` 的模式、`rule` 必须等于该模式；安全负责人和未启用脱敏的用例始终要求原值。评分器会将正文中同名指标、映射路径和审计值逐一绑定，不能用其他路径的碰巧数值替代。

## 5. 脱敏语义

脱敏由 `push_config.masking_rules` 和受众共同决定：

- `security_lead`：默认保留 IP、资产名、CVE、IOC 和技术规则名，除非用例明确要求脱敏；
- `management`：必须执行用例定义的脱敏规则，不能在正文、表格、列表、映射或元数据中泄漏敏感值；
- `both`：生成的内容必须满足管理层可见部分的脱敏要求，同时保留安全负责人所需的完整信息时，应由后续系统拆分视图；原型中按 Eval 用例的明确要求执行；
- `masking_applied` 必须记录原值、掩码值和规则。没有发生脱敏时返回空数组。`data_values` 与 `masking_applied.original` 是受控内部审计字段，不属于管理层可见简报；管理层泄漏扫描只检查可见内容、来源路径映射和元数据，避免把合规审计记录误判为泄漏。

负例 S04-019 应在管理层报告泄漏公网 IP 或资产名时被 `masking_check` 判定失败，而不是被当作 Harness 运行错误。

## 6. 组件职责与文件映射

| 文件 | 职责 |
|---|---|
| `eval/config.py` | 读取 Agent/Judge provider、模型、超时和响应模式 |
| `eval/llm_client.py` | Qwen、DeepSeek 等 OpenAI-compatible 调用、重试和硬超时 |
| `eval/prompt_builder.py` | 构造报告生成 Prompt 和 Judge Prompt |
| `eval/agent_loop.py` | 统一执行 Agent 调用并记录调用信息 |
| `eval/mock_agent.py` | 离线确定性报告生成器，只用于 Harness 验证 |
| `eval/schemas.py` | 报告输出、章节和评测结果的数据结构 |
| `eval/code_graders.py` | 六个代码评分器及 Ground Truth 一致性检查 |
| `eval/model_graders.py` | 语言质量和洞察质量模型评分 |
| `eval/report.py` | 写入 JSON、CSV 和运行 manifest |
| `eval/run_eval.py` | CLI、逐条运行、checkpoint 和 `--resume` |
| `eval/tests/` | Agent、Mock、Grader、数据集和恢复机制测试 |

## 7. 评测与通过判定

代码 Grader 必须直接检查实际输出，不仅检查字段是否合法：

- `data_accuracy`：每个模板 `required_data` 与 Ground Truth 指标都必须绑定到同章节的来源路径、实际审计值和正文声明；数字、百分比、计数、字符串、索引路径和 `.length` 均与源数据精确一致，衍生指标按用例计算；
- `template_completeness`：期望章节全部存在，正文非空，模板占位符不残留，且每个 `required_data` 都有对应映射和值；
- `format_compliance`：正文是合法 Markdown，标题层级不跳级，表格列数一致，代码围栏成对；
- `masking_check`：管理层不得出现敏感模式，安全负责人不得错误删除必须保留的信息；
- `push_target`：渠道和接收人必须与 `push_config` 完全一致；
- `output_schema`：完整 JSON Schema 和枚举值校验。

每条用例应保存：原始 case、最终 JSON、解析错误、六个代码分数、两个模型分数、总分、调用耗时和 checkpoint 状态。

负例的正确行为是：Agent 可以正常生成输出，但相关 Grader 失败；只有模型调用、JSON 解析或 Harness 异常才记录为 `error`。

## 8. 运行方式

离线验证：

```bash
cd scenarios/scenario-04-security-briefing/eval
python3 run_tests.py
python3 run_eval.py --mock-agent --run-dir results/mock-baseline
```

真实模型验证：

```bash
cp .env.example .env
python3 run_eval.py --limit 3 --run-dir results/qwen3.5-flash-smoke
python3 run_eval.py --run-dir results/qwen3.5-flash-baseline --resume
```

请求超时可以覆盖：

```bash
python3 run_eval.py \
  --run-dir results/qwen3.5-flash-baseline \
  --request-timeout-seconds 90 \
  --resume
```

## 9. 原型验收标准

- 20 条 Eval 可被加载并逐条执行；
- Mock Agent 能稳定生成完整输出并验证 Harness；
- S04-019 的脱敏泄漏被识别为评分失败；
- S04-020 的错误推送目标被识别为评分失败；
- Qwen、DeepSeek 等模型只需通过 `.env` 配置即可接入；
- 任意单条请求失败不会丢失已完成结果；
- `--resume` 仅在数据集 SHA-256、mock/real 模式、Agent/Judge provider、model、response mode 和 grader mode 都与运行清单、checkpoint 一致时跳过已完成条目；不一致时会重算，error 条目始终重试；
- 能输出 `eval_results.json`、`eval_summary.csv` 和逐条 checkpoint。
