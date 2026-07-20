# 场景四：任务简报生成及推送

本场景提供一个可重复执行的安全简报生成与推送 Eval Harness。Agent 必须仅使用用例中的
`mock_source_data`，按模板生成结构化 JSON 简报，并严格遵守收件人、推送渠道与脱敏要求。

## 场景文件

- `EvalsData.json`：20 个固定评测用例及其数据源、模板、推送配置、真值和评分约束。
- `agent-architecture.md`：Agent 的输入、生成、校验与推送架构说明。
- `eval-design.md`：评测设计、覆盖范围与评分策略。
- `eval-generation-prompt.md`：生成场景评测数据时使用的提示词。
- `eval/agent_loop.py`：真实模型 Agent 的一次用例执行流程。
- `eval/mock_agent.py`：无需网络和密钥的确定性 Mock Agent；用于基线与回归测试。
- `eval/prompt_builder.py`：将单个用例组装为 Agent 的完整提示。
- `eval/code_graders.py`：数据准确性、模板、Markdown、脱敏、推送目标和输出 Schema 的确定性评分器。
- `eval/model_graders.py`：语言质量与洞见质量的模型评分器。
- `eval/llm_client.py` 与 `eval/config.py`：OpenAI 兼容模型客户端和安全的环境变量配置加载。
- `eval/schemas.py`：数据集与 Agent 输出的结构约束。
- `eval/report.py`：JSON、CSV 与断点检查点报告写入逻辑。
- `eval/tests/` 与 `eval/run_tests.py`：Harness 单元测试。
- `eval/.env.example`：可复制的配置示例；只包含占位符，绝不提交实际的 `.env` 或任何密钥。

## 离线运行（Mock Agent）

在仓库根目录执行：

```bash
cd scenarios/scenario-04-security-briefing
PYTHONPYCACHEPREFIX=/tmp/scenario4-pycache python3 -m compileall -q eval
cd eval && python3 run_tests.py
python3 run_eval.py --mock-agent --run-dir results/mock-baseline
```

输出写入 `eval/results/mock-baseline/`：`eval_results.json` 包含逐用例明细，
`eval_summary.csv` 方便快速筛选，另有运行清单与可恢复运行的 checkpoints。运行清单会在处理前写入数据集 SHA-256、mock/real 模式、Agent/Judge provider/model/response mode 和 grader mode；`--resume` 只会复用 provenance 完全相同的 completed checkpoint。

## 真实模型运行

先安装依赖并从示例创建本机配置（`.env` 仅保留在本机）：

```bash
cd scenarios/scenario-04-security-briefing/eval
python3 -m pip install -r requirements.txt
cp .env.example .env
# 在 .env 中填写所选 provider、model 与 API key；不要提交该文件。
python3 run_eval.py --run-dir results/real-model-run
```

`.env.example` 提供 Qwen、DeepSeek 和其他 OpenAI 兼容端点的配置形式。真实模型运行会调用
Agent 与模型评分器；可通过 `--case-id S04-001`、`--limit 1` 进行小范围验证，或用
`--resume` 从已有 checkpoints 继续。

## 输出审计契约

每个章节使用 `data_source_mapping` 保存“指标名 → 源字段路径”，并用同名 `data_values` 保存该路径的实际 JSON 值。每个模板 `required_data` 都必须位于对应章节映射中，正文也必须明确展示该指标和值；对象和数组不能只显示路径，必须包含每个标量叶子值。敏感叶子仅可在已启用脱敏的管理层报告中显示为 `masking_applied` 的替换值，且 record 的 `original`、`masked`、`rule` 必须与用例的敏感模式一致；安全负责人报告和脱敏关闭的报告必须保留原值。原值审计字段和 `data_values` 仅用于内部评分，管理层泄漏扫描不将它们视作可见报告内容。

## 负例与结果解读

`status=completed` 表示 Harness 已成功执行并产出可评分的结构化输出，不等同于所有评分项通过。
离线基线中的两个负例故意保留单项失败，用来验证评分器能够拦截风险：

- `S04-019` 模拟管理层简报泄露具体 IP/资产信息，因此仅 `masking_check` 应失败。
- `S04-020` 模拟将简报错误投递给全员地址，因此仅 `push_target` 应失败。

这两个用例的 `overall_pass=false` 是预期安全信号，不是执行异常；其余正例应全部通过确定性
Code Graders。
