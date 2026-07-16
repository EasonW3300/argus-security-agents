# 场景一：安全告警分析与处置建议

建议按下面这个顺序看：

1. 先看 [Agent 初始架构设计](docs/agent-architecture.md)，确认真实 Agent 要接什么输入、调哪些工具、返回什么结构；
2. 再看 [Eval 数据核心标签说明](docs/eval-data-label-guide.md)，弄清 30 条 JSON 里的输入、mock 数据和 Ground Truth 分别是什么，以此快速了解Eval包含的具体内容，以及是如何构建的；
3. 最后看 [基线实验结果](docs/experiment-results.md)，了解当前LLM基线通过了什么、还差在哪里。

这里交付的是一套可以直接运行的 Eval 测试集和 Agent 初始架构，并没有具体实现真实告警分析 Agent。可参考架构设计结合实际情况完成Agent的具体实现，再用这里的 30 条用例持续回归（由于目前对于真实环境的数据并没有完全掌握，Eval的设计是mock的，架构的设计也是基于mock的Eval评测集，）。

## 当前目录里有什么

```text
scenario-01-alert-analysis/
├── README.md
├── docs/
│   ├── agent-architecture.md
│   ├── eval-data-label-guide.md
│   └── experiment-results.md
└── eval/
    ├── Eval-data_0.json
    ├── Eval-data_v1.json
    ├── calibrate_eval_data.py
    ├── run_eval.py
    ├── config.py
    ├── schemas.py
    ├── prompt_builder.py
    ├── llm_client.py
    ├── code_graders.py
    ├── model_graders.py
    ├── report.py
    ├── requirements.txt
    ├── .env.example
    ├── tests/
    └── results/qwen3.5-flash-baseline/
```

### 三份文档

- `docs/agent-architecture.md`：实现边界。里面有六步研判流程、四个标准工具、输入输出 Schema、异常处理和 Eval 对接方式。
- `docs/eval-data-label-guide.md`：逐项解释 Eval JSON。尤其要看 Ground Truth 隔离、Tool ID、`severity_enum` 和 `severity_match` 的区别。
- `docs/experiment-results.md`：记录本轮 30 条 由qwen3.5-flash跑的实验、六条严重度错例和 A13 断点恢复情况。

### 两份数据

- `eval/Eval-data_0.json`：原始生成基线，主要用来追溯数据来源，平时不要直接拿它跑正式评测。
- `eval/Eval-data_v1.json`：校准后的正式测试集，共 30 条 A01-A30，正常运行默认读取它。

### Eval Harness 代码

- `eval/run_eval.py`：运行入口，负责选用例、调用 Agent/Judge、写 checkpoint、resume 和生成报告。
- `eval/config.py`：读取环境变量，支持 Qwen、DeepSeek、OpenAI 和自定义 Chat Completions 兼容服务。
- `eval/schemas.py`：定义 Agent 输出、Judge 输出、调用记录和单条结果的严格 Schema。
- `eval/prompt_builder.py`：路线 A 的 Prompt Builder。它把 mock 工具结果作为“已查询信息”交给模型，并明确标准 Tool ID。
- `eval/llm_client.py`：统一模型调用、JSON 解析、Schema 校验和有限重试。
- `eval/code_graders.py`：6 个确定性 Grader，包括 Ground Truth 严重度一致性检查。
- `eval/model_graders.py`：质量和幻觉 Judge。每条用例实际分 4 次 Judge 调用。
- `eval/report.py`：汇总完成率、准确率、延迟、token 等指标，输出 CSV 和 JSON。
- `eval/calibrate_eval_data.py`：从 v0 确定性生成 v1，保证校准过程可重复。（这个是不用管，用来优化Eval的脚本而已，已经优化过了）

### 测试和结果

- `eval/tests/test_config.py`：检查 Provider 配置、Judge 继承、价格参数和敏感配置脱敏。
- `eval/tests/test_schemas.py`：检查 Agent/Judge 输出 Schema、枚举和数值范围。
- `eval/tests/test_eval_data_v1.py`：检查 30 条 ID、标签一致性、难度分布和 Grader 数量。
- `eval/tests/test_prompt_builder.py`：检查 Prompt 内容稳定性、Tool ID 契约和 Ground Truth 隔离。
- `eval/tests/test_llm_client.py`：使用 Fake Client 检查请求参数、解析、重试和错误分类。
- `eval/tests/test_code_graders.py`：检查 6 个 Code Grader 的独立判定逻辑。
- `eval/tests/test_model_graders.py`：检查三个质量维度和幻觉 Judge 的调用契约。
- `eval/tests/test_report.py`：检查准确率、延迟、token、成本和 CSV/JSON 报告。
- `eval/tests/test_run_eval.py`：检查 Runner、错误隔离、Manifest、checkpoint 和 resume。
- `eval/results/qwen3.5-flash-baseline/`：本次正式 30 条基线，包括 Manifest、CSV、JSON 和逐条 checkpoint。
- `eval/results/qwen3.5-flash-baseline/checkpoints/A01.json` 至 `A30.json`：文件名对应测试用例 ID，每个文件保存该条最终状态、Agent 输出、评分和成功调用记录。

## 当前路线 A 到底做了什么

路线 A 不运行真实工具循环。它从每条 Eval 用例中读取：

- `input.trigger_context`；
- `mock_api_responses` 中已经准备好的工具返回。

然后把这些信息一次性放进 Prompt，让模型输出结构化研判结果，再交给 Grader 评分。

这样做的目的，是先确认 Eval 数据、输出契约和评分体系能跑通。后续前场实现真实 Agent 时，可以把这段“一次性生成”替换成真实工具调用流程，但尽量不要改变 Eval 数据和最终输出结构。

## 先跑离线测试

进入 Eval 目录：

```bash
cd scenarios/scenario-01-alert-analysis/eval
```

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

运行离线测试：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

预期结果是 `Ran 75 tests` 和 `OK`。这一步不会调用外部模型。

## 配置模型

复制环境变量模板：

```bash
cp .env.example .env
```

在本机 `.env` 中填写 Provider、模型和密钥。不要把 `.env` 提交到 GitLab，也不要把密钥直接写进命令、README、日志或结果文件。

Agent 和 Judge 可以使用不同 Provider。当前兼容：

- `qwen`；
- `deepseek`；
- `openai`；
- `custom`，用于其他 OpenAI Chat Completions 兼容服务。

## 建议的运行顺序

先跑单条，并暂时跳过 Model Grader：

```bash
python3 run_eval.py --run-id local-a01 --case-id A01 --skip-model-graders
```

再跑 3 条完整冒烟：

```bash
python3 run_eval.py --run-id local-smoke3 --limit 3
```

确认配置和输出没问题后，再跑 30 条：

```bash
python3 run_eval.py --run-id local-full30
```

如果中间有个别用例失败，可以在相同配置和相同参数下续跑：

```bash
python3 run_eval.py --run-id local-full30 --resume
```

不要用新 Prompt 或新模型强行复用旧 checkpoint。Harness 会用数据集、Prompt、模型非敏感配置和运行参数计算指纹，不一致时会拒绝 resume。

## 怎么看运行结果

每次运行会生成：

```text
output/<run_id>/
├── run_manifest.json
├── checkpoints/
├── eval_summary.csv
└── eval_results.json
```

- 想快速筛错例，先打开 `eval_summary.csv`；
- 想看完整 Agent 输出、Judge 理由和调用信息，看 `eval_results.json`；
- 想排查单条失败，看 `checkpoints/<case_id>.json`；
- 想确认这次到底用了哪份数据、哪个 Prompt 和哪个模型，看 `run_manifest.json`。

最关键的业务指标是 `severity_accuracy`，它来自 `severity_match`，表示 Agent 输出的严重度是否真的等于 Ground Truth。`severity_enum=100%` 只代表模型输出了合法枚举，不代表研判正确。

## 前场伙伴如何接入真实 Agent

可以保留数据加载、Grader、报告和 checkpoint，把 `prompt_builder.py + 单次模型调用` 替换成你们自己的 Agent 执行器。

接入时至少保持：

- 输入仍能接收 `alert_id` 和 `trigger_context`；
- 工具使用四个标准 ID；
- 最终输出符合 `schemas.AgentOutput`；
- Ground Truth 不进入 Agent 上下文；
- 每条用例失败不会中止整批；
- 修改后先通过 75 个离线测试，再跑真实模型冒烟。

具体是用状态机、Agent loop、工作流框架，还是规则和模型混合，由前场根据生产环境决定。这套仓库只负责给出可验证的外部契约。

## 当前还没有做什么

- 没有连接真实 SOC/SIEM、CMDB 或威胁情报平台；
- 没有实现真实 Tool Calling loop；