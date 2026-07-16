# 网安运营 Agent Eval 与架构设计

## 仓库定位

本仓库用于沉淀四个网安运营场景的 Eval 测试集、Eval Harness、基线实验结果和 Agent 初始架构设计，帮助前场人员按照统一契约实现真实 Agent，并使用同一批测试持续回归。

当前只完成场景一：安全告警分析与处置建议。

职责边界如下：

- 本仓库负责 Eval 数据、评分体系、可运行的评测原型和 Agent 外部架构契约；
- 前场人员负责真实 Agent 的内部流程、工具编排、生产连接器和业务集成；
- 当前 Python Harness 使用 mock 工具返回验证研判和评分链路，不等同于生产 Agent。

## 仓库目录

```text
.
├── README.md
├── scenarios/
│   ├── scenario-01-alert-analysis/
│   │   ├── README.md
│   │   ├── docs/
│   │   │   ├── agent-architecture.md
│   │   │   ├── eval-data-label-guide.md
│   │   │   └── experiment-results.md
│   │   └── eval/
│   │       ├── Eval-data_0.json
│   │       ├── Eval-data_v1.json
│   │       ├── calibrate_eval_data.py
│   │       ├── run_eval.py
│   │       ├── config.py
│   │       ├── schemas.py
│   │       ├── prompt_builder.py
│   │       ├── llm_client.py
│   │       ├── code_graders.py
│   │       ├── model_graders.py
│   │       ├── report.py
│   │       ├── requirements.txt
│   │       ├── .env.example
│   │       ├── tests/
│   │       └── results/qwen3.5-flash-baseline/
│   ├── scenario-02-document-rag/README.md
│   ├── scenario-03-security-tool-calling/README.md
│   └── scenario-04-security-briefing/README.md
└── .gitignore
```

# 场景一：安全告警分析与处置建议

场景一接收 SOC/SIEM 告警，结合告警详情、资产上下文、威胁情报和关联告警，输出严重度、攻击类型、置信度、证据链、IOC 和处置建议。

## 建议阅读顺序

1. [场景一 README](scenarios/scenario-01-alert-analysis/README.md)：了解目录、运行方法和前场接入方式；
2. [Agent 初始架构设计](scenarios/scenario-01-alert-analysis/docs/agent-architecture.md)：了解输入输出、六步流程和四个工具；
3. [Eval 数据核心标签说明](scenarios/scenario-01-alert-analysis/docs/eval-data-label-guide.md)：了解 JSON 数据和评分标签；
4. [基线实验结果](scenarios/scenario-01-alert-analysis/docs/experiment-results.md)：了解 30 条 Qwen 测试结论和限制。

## 场景一文件说明

### 入口和设计文档

| 文件 | 作用 |
|---|---|
| `scenarios/scenario-01-alert-analysis/README.md` | 场景一接手指南、运行命令和复现路径 |
| `docs/agent-architecture.md` | 真实 Agent 必须遵守的输入、工具、输出和 Eval 对接契约 |
| `docs/eval-data-label-guide.md` | Eval JSON 顶层标签、mock 返回、Ground Truth 和 Grader 说明 |
| `docs/experiment-results.md` | Qwen `qwen3.5-flash` 的 30 条正式基线和已知问题 |

### Eval 数据和校准

| 文件 | 作用 |
|---|---|
| `eval/Eval-data_0.json` | 30 条原始生成基线，只用于追溯和重新校准 |
| `eval/Eval-data_v1.json` | 30 条校准后的正式评测集，运行时默认读取 |
| `eval/calibrate_eval_data.py` | 从 v0 确定性生成 v1 的校准脚本 |

### Eval Harness

| 文件 | 作用 |
|---|---|
| `eval/run_eval.py` | 评测入口，负责用例选择、执行、checkpoint、resume 和报告生成 |
| `eval/config.py` | Qwen、DeepSeek、OpenAI 和 custom Provider 的环境配置 |
| `eval/schemas.py` | Agent、Judge、调用记录和用例结果的严格数据模型 |
| `eval/prompt_builder.py` | 路线 A Prompt 组装和标准 Tool ID 契约 |
| `eval/llm_client.py` | Chat Completions 兼容调用、重试、JSON 解析和 Schema 校验 |
| `eval/code_graders.py` | 6 个确定性评分器，包括 Ground Truth 严重度匹配 |
| `eval/model_graders.py` | 质量评分和幻觉检查 Judge |
| `eval/report.py` | 汇总指标并生成 CSV、JSON 报告 |
| `eval/requirements.txt` | Python 依赖 |
| `eval/.env.example` | 不含密钥的本地配置模板 |

### 测试和正式结果

| 路径 | 作用 |
|---|---|
| `eval/tests/test_config.py` | Provider、Judge 继承、价格参数和敏感配置脱敏测试 |
| `eval/tests/test_schemas.py` | Agent/Judge 输出 Schema、枚举和范围测试 |
| `eval/tests/test_eval_data_v1.py` | 30 条 Eval 数据身份、标签、分布和 Grader 契约测试 |
| `eval/tests/test_prompt_builder.py` | Prompt 稳定性、Tool ID 和 Ground Truth 隔离测试 |
| `eval/tests/test_llm_client.py` | 模型请求参数、JSON 解析、重试和错误分类测试 |
| `eval/tests/test_code_graders.py` | 6 个确定性 Grader 测试 |
| `eval/tests/test_model_graders.py` | 质量与幻觉 Judge 调用契约测试 |
| `eval/tests/test_report.py` | 汇总指标、成本和 CSV/JSON 报告测试 |
| `eval/tests/test_run_eval.py` | Runner、错误隔离、Manifest、checkpoint 和 resume 测试 |
| `eval/results/qwen3.5-flash-baseline/run_manifest.json` | 正式实验的数据、Prompt、模型和运行参数指纹 |
| `eval/results/qwen3.5-flash-baseline/eval_summary.csv` | 30 条逐条汇总，适合筛选错例 |
| `eval/results/qwen3.5-flash-baseline/eval_results.json` | 完整输出、评分、Judge 理由和汇总指标 |
| `eval/results/qwen3.5-flash-baseline/checkpoints/A01.json`–`A30.json` | 与用例 ID 一一对应的独立执行结果，用于逐条排查和恢复验证 |

## 最短复现路径

```bash
cd scenarios/scenario-01-alert-analysis/eval
python3 -m pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
cp .env.example .env
python3 run_eval.py --run-id local-a01 --case-id A01 --skip-model-graders
```

`.env` 只保留在本机，不得提交到 GitLab。真实模型的 Eval 会把用例中的告警上下文和 mock 工具返回发送给所配置的第三方 Provider，运行前应确认数据发送范围和模型调用成本。

## 当前基线

- 30/30 条完成；
- 标准 Tool ID 最低集合通过率 100%；
- 严重度准确率 80%；
- 误报召回率 100%；
- 75 个离线测试通过；
- Agent 与 Judge 均使用 Qwen `qwen3.5-flash`。

基线证明 Eval 链路已经跑通，不代表真实 Agent 已经实现，也不代表质量目标已经全部达成。

# 场景二：安全文档 RAG

# 场景三：安全工具调用

# 场景四：任务简报生成及推送
>>>>>>> 1aa99a8 (feat:场景一：对于态感等平台等告警分析处置建议Agent的Evals基线以及Agent架构设计)
