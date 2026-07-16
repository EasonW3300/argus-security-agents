# 场景一 Eval 基线实验结果

## 1. 实验目的

本次实验用于验证路线 A Eval Harness 是否能够完整执行 30 条场景一用例，并检验 Prompt v2 的标准 Tool ID 契约、Ground Truth 严重度一致性评分、错误隔离和断点续跑能力。

本实验验证的是 Eval 数据和评测架构，不是对生产 Agent 实现的验收。

## 2. 实验配置

| 配置项 | 值 |
|---|---|
| 数据集 | `Eval-data_v1.json`，30 条 |
| 数据集 SHA-256 | `c4002a393508107e198264130598dadbf994dd384e85b0bb4bde5f77156050d2` |
| Prompt 版本 | `route-a-v2-tool-ids` |
| Agent Provider / 模型 | Qwen / `qwen3.5-flash` |
| Judge Provider / 模型 | Qwen / `qwen3.5-flash` |
| response mode | `json_object` |
| temperature | `0` |
| Model Grader | 开启，每条 4 次 Judge 调用 |

每条用例正常情况下产生 1 次 Agent 调用和 4 次 Judge 调用。最终 checkpoint 保存 30 × 5 = 150 个成功调用记录。

## 3. 最终结果

| 指标 | 结果 |
|---|---:|
| 完成率 | 100%（30/30） |
| Tool ID 最低集合通过率 | 100% |
| 输出 Schema 通过率 | 100% |
| 严重度枚举合法率 | 100% |
| 严重度准确率 | 80%（24/30） |
| 置信度范围通过率 | 100% |
| 处置建议非空通过率 | 100% |
| Code Grader 综合通过率 | 80% |
| 误报召回率 | 100% |
| Judge uncertain 数量 | 0 |
| 幻觉率 | 0% |
| 平均延迟 | 51,376.7 ms/条 |
| P95 延迟 | 64,544 ms |
| 输入 Token | 236,159 |
| 输出 Token | 140,545 |
| 估算成本 | 未配置单价，结果为 `null` |

三个 Judge 质量维度的平均分均为 5：

- 严重度合理性：5；
- 处置可执行性：5；
- 证据完整性：5。

这些分数由与 Agent 相同的 `qwen3.5-flash` 评出，只能作为当前链路的辅助信号，不能代替独立模型或安全专家复核。

## 4. Tool ID 修复效果

Prompt v1 没有向模型明确暴露标准工具 ID，模型容易在 `metadata.tools_called` 中输出产品名或自然语言数据源，导致 `tools_called_minimum` 为 0%。

Prompt v2 从当前用例的 `mock_api_responses` key 推导可用标准工具 ID，并要求模型精确输出。修复后的正式结果为 30/30 通过。

该修复没有读取或注入 `ground_truth.expected_tools_minimum`，因此没有把评分答案泄露给 Agent。

## 5. 严重度错例

6 条用例的输出严重度高于 Ground Truth：

| 用例 | Ground Truth | Agent 输出 |
|---|---|---|
| A03 | `high` | `critical` |
| A04 | `medium` | `high` |
| A11 | `high` | `critical` |
| A12 | `high` | `critical` |
| A14 | `high` | `critical` |
| A18 | `high` | `critical` |

这说明当前模型倾向于把“高风险迹象”直接升级为 `critical`。前场实现时应重点区分：

- 是否已有成功入侵或实际影响证据；
- 是否为核心资产；
- 攻击是否已被阻断；
- 关联告警是否构成完整攻击链；
- 单一恶意 IOC 是否足以证明资产已经失陷。

不建议为了提高分数修改 Ground Truth，应优先调整严重度规则、证据门槛或研判流程。

## 6. A13 异常与恢复验证

全量首轮执行时，A13 的 hallucination Judge 把合法枚举 `verifiable` 拼写成 `veriable`。客户端完成 3 次 Schema 重试后将 A13 记录为结构化错误，Runner 没有中止整批，继续完成 A14-A30。

使用相同配置执行 `--resume` 后：

- 已完成的 29 条没有重新调用模型；
- 只重跑 A13；
- A13 最终完成；
- 最终报告为 30/30 completed。

这验证了单条错误隔离、checkpoint 和 resume 的原型设计。

当前实现会在重跑成功后覆盖原 error checkpoint，因此首轮失败请求的 token、成本和完整重试历史不会保留在最终报告中。生产化时建议增加 append-only 的 attempt ledger。

## 7. 可以得出的结论

- 30 条校准数据可以被 Harness 顺序加载和评测；
- Agent/Judge 的 OpenAI-compatible 调用链路可运行；
- Prompt、Schema、Code Grader、Model Grader、报告和 checkpoint 已形成闭环；
- 标准 Tool ID 契约已经通过真实 Qwen 运行验证；
- `severity_match` 可以直接计算 Ground Truth 严重度准确率；
- 单条模型异常不会破坏整批运行；
- 前场可以在保持数据和输出契约的前提下，替换生成阶段来评测真实 Agent。

## 8. 不能得出的结论

- 不能证明真实工具调用编排已经实现；
- 不能证明 Qwen Judge 的 5 分等同于安全专家结论；
- 不能证明模型在多次重复运行下保持同样结果；
- 不能证明 DeepSeek 已经完成真实全量验证；当前仅有兼容代码和离线测试；
- 不能把 80% 严重度准确率视为已达到方案中 ≥90% 的目标。

## 9. 正式产物

- `eval_results.json`：汇总指标、30 条完整输出和评分明细；
- `eval_summary.csv`：便于筛选和分析的逐条摘要；
- `run_manifest.json`：数据集指纹、Prompt 版本、非敏感模型配置和运行参数；
- `checkpoints/`：30 条用例的独立执行结果。

