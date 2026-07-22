# 四场景 agent-compose 接入指南

这个目录把四个已有场景接入了 `agent-compose`，但不替换各场景已有的 Eval Harness。

`agent-compose` 在这里负责：创建隔离工作区快照、启动带 Python 依赖的 guest、记录运行日志和提供调度入口。`run_scenario.py` 负责将统一命令转发给各场景原有的 `run_eval.py` 或测试入口。数据集、Prompt、Grader、checkpoint 和报告仍由原 Harness 管理。

## 目录与边界

```text
argus-security-agents/
├── agent-compose.yml                 # 四个 Agent 的编排声明
├── agent-compose.ui.yml              # Web UI 专用的 GitHub Workspace 编排声明
├── integration/
│   ├── Dockerfile                     # 包含四套 Harness Python 依赖的 guest 镜像
│   ├── .env.example                   # 本地模型配置模板
│   ├── run_scenario.py                # 统一命令型适配器
│   └── README.md                      # 本文档
├── scenarios/                         # 原始四场景代码、Eval 和架构设计快照
├── agent-compose-results/             # 运行时生成，已忽略
└── tests/test_run_scenario.py         # 适配器单元测试
```

这不是把 Qwen 或 DeepSeek 注册为 agent-compose 的原生 Provider。官方原生 Provider 是 `codex`、`claude`、`gemini`、`opencode`；本项目选择 `opencode` 作为沙箱 Agent 的编排入口。实际的 Qwen、DeepSeek 或其他 OpenAI-compatible 调用仍由各场景现有 Python 客户端处理，因此模型和 Key 的配置方式与此前 Eval 一致。

## 首次准备

在这个隔离工程根目录执行：

```bash
cp integration/.env.example integration/.env
```

编辑 `integration/.env`。Qwen 示例只需要保留：

```dotenv
AGENT_PROVIDER=qwen
AGENT_MODEL=qwen3.5-flash
DASHSCOPE_API_KEY=你的DashScope密钥
```

`.env` 已被 Git 忽略，不能提交。只有你运行 `--mode model` 时，Harness 才会把对应 Eval 用例、Mock 工具/检索数据和 Prompt 发送给所配置的模型服务。`tests` 与 `mock` 均不访问外部模型。

## 在 Web UI 中测试四个场景

`agent-compose.yml` 使用本地文件工作区，适合此前的 CLI 验证；Web UI 使用
`agent-compose.ui.yml`，从 GitHub 拉取 `feature/scenario-o2-eval` 分支。

仓库地址和 `feature/scenario-o2-eval` 分支已固定在 `agent-compose.ui.yml`。
当前 GitHub 仓库为公开仓库，因此 Web UI 无需 GitHub Token；不要将任何 Token
写进 `.env.example`、YAML、README 或提交记录。

在运行 Web UI 的 `agent-compose` 工程目录中注册项目：

```bash
docker compose exec -T agent-compose agent-compose \
  -f /data/work/agent-compose.ui.yml up
```

刷新 `http://localhost` 后会出现 `argus-security-agents-ui` 项目和四个场景
Agent。进入一个 Agent 后选择 **Run Command**，粘贴下列命令。先使用离线/Mock
模式；它们不会调用 Qwen、DeepSeek 或任何第三方模型服务。

```bash
# 场景一：离线测试
python3 integration/run_scenario.py --scenario scenario-01 --mode tests

# 场景二：单条 Mock 冒烟
python3 integration/run_scenario.py --scenario scenario-02 --mode mock --limit 1 --run-id ui-s02-mock

# 场景三：单条 Mock 冒烟
python3 integration/run_scenario.py --scenario scenario-03 --mode mock --limit 1 --run-id ui-s03-mock

# 场景四：单条 Mock 冒烟
python3 integration/run_scenario.py --scenario scenario-04 --mode mock --limit 1 --run-id ui-s04-mock
```

在 UI 的 Run 日志中确认场景一测试完成，场景二至四出现 `overall_pass=true`。
只有你明确需要真实模型回归时，才将 `--mode mock` 改为 `--mode model` 并配置
相应模型 Key。

## 启动 agent-compose

官方代码位于与本工程并列的 `../agent-compose/`。先按官方 README 安装或构建 CLI，并启动本地 daemon。之后在本工程根目录运行：

```bash
agent-compose config --quiet
agent-compose build
agent-compose up
agent-compose ps --all
```

`build` 会基于 `ghcr.io/chaitin/agent-compose-guest:latest` 安装全部 Python 依赖；首次构建需要 Docker 和网络。`up` 只把项目定义应用到 daemon，尚未调用任何模型。

## 四个 Agent 的运行命令

所有命令都通过 `agent-compose run <agent> --command` 运行。`--command` 的 stdout/stderr 会被 agent-compose 记录；查看时使用 `agent-compose logs --agent <agent>`。

### 场景一：安全告警分析

场景一只有离线测试和真实模型模式，原因是其原型没有确定性 Mock Agent。

```bash
# 75 个离线单元测试，不调用模型
agent-compose run alert-analysis-agent --command \
  'python3 integration/run_scenario.py --scenario scenario-01 --mode tests'

# 真实模型单条验证；会调用 integration/.env 中的模型服务
agent-compose run alert-analysis-agent --command \
  'python3 integration/run_scenario.py --scenario scenario-01 --mode model --case-id A01 --run-id s01-smoke'
```

### 场景二：安全文档 RAG

```bash
# 3 条确定性 Mock 冒烟
agent-compose run document-rag-agent --command \
  'python3 integration/run_scenario.py --scenario scenario-02 --mode mock --limit 3 --run-id s02-mock-smoke'

# 真实模型全量 Eval
agent-compose run document-rag-agent --command \
  'python3 integration/run_scenario.py --scenario scenario-02 --mode model --run-id s02-model-full'
```

### 场景三：安全工具调用

```bash
# Mock Agent 会使用既有 Mock Tool Server 和权限逻辑
agent-compose run security-tool-agent --command \
  'python3 integration/run_scenario.py --scenario scenario-03 --mode mock --limit 3 --run-id s03-mock-smoke'

# 真实模型单条工具调用回归
agent-compose run security-tool-agent --command \
  'python3 integration/run_scenario.py --scenario scenario-03 --mode model --case-id S03-001 --run-id s03-model-smoke'
```

### 场景四：安全简报生成与推送

```bash
# 3 条确定性 Mock 冒烟
agent-compose run security-briefing-agent --command \
  'python3 integration/run_scenario.py --scenario scenario-04 --mode mock --limit 3 --run-id s04-mock-smoke'

# 真实模型单条验证
agent-compose run security-briefing-agent --command \
  'python3 integration/run_scenario.py --scenario scenario-04 --mode model --case-id S04-001 --run-id s04-model-smoke'
```

## 结果、恢复与关闭

- 四个场景的最终报告都保留在 `agent-compose-results/<scenario>/<run-id>/`，与正式基线隔离。场景一、二先按其原 Harness 的固定目录生成，再由适配器导出到该持久目录；场景三、四直接写入该目录。
- 对支持恢复的场景，在同样的配置和 `--run-id` 下追加 `--resume`：

```bash
agent-compose run security-briefing-agent --command \
  'python3 integration/run_scenario.py --scenario scenario-04 --mode model --run-id s04-model-smoke --resume'
```

查看运行日志：

```bash
agent-compose logs --agent security-briefing-agent
```

结束本项目的运行资源：

```bash
agent-compose down
```

## 后续生产化替换点

- 场景一：将一次性 Mock 上下文注入替换为真实告警、资产、威胁情报和关联告警工具。
- 场景二：将 Mock chunks 替换为真实检索、Rerank 和文档权限过滤服务。
- 场景三：将 Mock Tool Server 替换为受权限控制的 MCP 或生产工具 API。
- 场景四：将 Mock 数据源与推送记录替换为真实数据源、审批和邮件/IM 推送连接器。

替换内部实现时，保持现有输入、输出 Schema 和 Eval Ground Truth 契约不变；这样可继续使用当前评测集回归。
