# 场景二：安全文档 RAG

这个目录是场景二的 Agent 原型和 Eval 评测集。当前目标不是实现真实 RAG，而是先把“mock 检索结果注入 prompt → Agent 生成结构化回答 → Grader 评分 → 输出报告”这条链路跑通。

## 文件说明

- `agent-architecture.md`：场景二 Agent 架构设计文档，说明路线 A、输出格式、grader 设计和模型接入方式。
- `eval/Eval_data_1.json`：25 条 Eval 测试用例，每条包含用户问题、mock retrieved chunks、ground truth 和 grader 配置。
- `eval/run_eval.py`：Eval 主入口，负责加载数据、调用 mock agent 或真实 LLM、执行 grader、生成报告。
- `eval/mock_agent.py`：离线原型 Agent，不做真实推理，只根据 ground truth 生成可落地的结构化输出，用来验证 Harness 和报告链路。
- `eval/prompt_builder.py`：把 mock chunks 格式化进 prompt，也提供 Judge prompt。
- `eval/code_graders.py`：6 个代码型 Grader，包括引用格式、输出 Schema、拒绝行为、检索相关性、引用落地、置信度阈值。
- `eval/model_graders.py`：3 个模型型 Grader，包括 faithfulness、coverage、compliance_accuracy。
- `eval/results/`：Eval 运行结果目录，每次运行会生成 `run_manifest.json`、`eval_results.json`、`eval_summary.csv` 和 checkpoints。

## 快速运行

离线验证 Harness：

```bash
cd scenarios/scenario-02-document-rag/eval
GENERATOR_PROVIDER=mock GENERATOR_MODEL=mock-scenario-02-agent GENERATOR_API_KEY=dummy \
JUDGE_PROVIDER=mock JUDGE_MODEL=mock-scenario-02-judge JUDGE_API_KEY=dummy \
python3 run_eval.py --run-id mock-baseline --mock-agent --skip-model-graders
```

接入 Qwen / DeepSeek 等模型时，参考 `eval/.env.example` 填写 `.env`，然后运行：

```bash
cd scenarios/scenario-02-document-rag/eval
python3 run_eval.py --run-id qwen3.5-flash-baseline
```

如果只想先跑 3 条冒烟：

```bash
python3 run_eval.py --run-id smoke --limit 3
```
