# 场景四 Harness Task 2 报告

## 交付内容

- 新增 `prompt_builder.py`：将请求、源数据、模板、推送/脱敏约束及严格 JSON 输出契约注入模型消息。
- 新增 `llm_client.py`：适配 Qwen、DeepSeek 等 OpenAI-compatible Chat Completions 接口，支持 JSON 输出模式、SDK 超时、主线程硬墙钟超时及最多三次重试。
- 新增 `agent_loop.py`：执行单轮报告生成，验证报告结构，并保留消息转录和可序列化调用记录。
- 新增 `mock_agent.py`：递归读取模板所需数据并生成 Markdown 内容和来源映射；正例遵从脱敏与推送契约，S04-019 故意泄露一项敏感值，S04-020 故意将收件人设为 `all-staff@company.com`。
- 新增 `tests/test_agent_and_mock_agent.py`：覆盖提示词、Mock 正例/两个负例、Agent loop 审计记录和客户端 JSON 重试。

## 验证

在 `scenarios/scenario-04-security-briefing/eval` 运行：

```text
python3 -m unittest discover -s tests -v
Ran 14 tests ... OK

PYTHONPYCACHEPREFIX=/private/tmp/s04-pycache python3 -m py_compile prompt_builder.py llm_client.py agent_loop.py mock_agent.py

所有 20 个 Mock 输出均通过 ReportOutput.validate。
```
