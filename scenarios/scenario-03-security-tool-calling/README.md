# 场景三：安全工具调用

这里放的是场景三“安全工具调用编排 Agent”的 Eval Harness 和初始 Agent 原型。
它的重点不是连接真实防火墙、扫描器或工单系统，而是先把工具选择、参数填写、多步编排、权限拒绝和错误恢复这条评测链路跑通。

## 目录说明

```text
scenario-03-security-tool-calling/
├── agent-architecture.md       # Agent 外部行为、工具循环和 transcript 契约
├── eval-design.md               # Eval 设计、用例分布和 Grader 规则
├── eval-generation-prompt.md    # 生成或扩展 Eval 数据时使用的提示词
├── Eval-data_v0/
│   └── Eval_scen_03.json        # 20 条正式场景三 Eval 数据
└── eval/
    ├── run_eval.py              # Harness 入口
    ├── agent_loop.py            # JSON 协议 Agent Loop
    ├── mock_agent.py            # 离线确定性 Agent 原型
    ├── mock_tool_server.py      # 根据 Eval JSON 返回 Mock 工具结果
    ├── tool_registry.py         # 工具注册和角色权限检查
    ├── transcript.py             # transcript 事件结构和状态映射
    ├── code_graders.py          # 7 个确定性 Grader
    ├── model_graders.py         # orchestration_quality / safety_check
    ├── prompt_builder.py         # Agent/Judge prompt
    ├── llm_client.py             # Qwen、DeepSeek、OpenAI-compatible 接入
    ├── report.py                 # JSON/CSV 报告
    ├── tests/                    # 离线单元测试
    └── results/                  # 本地运行结果，不提交 .env 或密钥
```

## 最短运行方式

```bash
cd scenarios/scenario-03-security-tool-calling/eval
python3 run_tests.py
python3 run_eval.py --mock-agent --run-dir results/mock-baseline
```



## 真实模型运行

复制 `.env.example` 为 `.env` 并填写密钥，然后可以使用 Qwen、DeepSeek 或 OpenAI-compatible 服务。模型每轮输出统一 JSON：

```json
{"type":"tool_call","tool_name":"scan_ports","params":{"target_ip":"10.0.1.5","port_range":"22,80,443"}}
```

或结束循环：

```json
{"type":"final","output":{"summary":"...","tools_called":[],"actions_taken":[]}}
```

运行示例：

```bash
python3 run_eval.py --run-dir results/qwen-baseline
python3 run_eval.py --case-id S03-013 --run-dir results/qwen-s0313
```



## 结果文件

- `eval_results.json`：完整 manifest、每条 case 的 transcript、最终输出和 Grader 明细。
- `eval_summary.csv`：便于快速查看每条 case 的通过情况。
- `tool_sequence_consistency` 会给出 `exact_match`、`precision`、`recall`、漏步骤、额外步骤和顺序错误。


