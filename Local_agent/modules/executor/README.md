# 执行模块

HomeAgent **行动层**：将明确动作或代码生成规格落地处理，不负责规划、决策或判断任务是否完成。

## 定位

| 负责 | 不负责 |
|------|--------|
| 按 `mode` 路由到子能力并返回事实 | 理解模糊需求、规划、推断下一步 |
| 命令执行：解析 → 安检 → shell/文件 IO | 补全参数、修改目标、自动重试 |
| 代码生成：详细规格 → 完整代码 | 执行或写入生成的代码 |

动作无法唯一执行 → 返回 `not_executable`。

## 子能力（`mode`）

| mode | 说明 | 安检 | LLM 槽位 |
|------|------|------|----------|
| `command`（默认） | shell.run / file.read / file.write | 是 | `executor.command.parse` |
| `codegen` | 详细规格 → 纯代码输出（stdout） | 否 | `executor.codegen` |

后续可继续添加子能力，统一走 `ExecuteRequest` / `ExecuteResult`。

### command — 命令执行

与第一版相同：自然语言明确动作 → JSON Action → 校验 → 安检 → 执行。

**带正文的 `file.write`**：正文优先从 `file_content`（附件）→ Markdown 代码块 → LLM `content`。

### codegen — 代码生成

- 输入：`action_text` 为完整、详细的规格说明（含语言、接口、输入输出、边界条件等）
- 输出：`ok=true`，`action_type=code.generate`，`stdout` 为纯代码
- 不经 SecurityService，不执行、不写盘

## 核心流程

```
ExecuteRequest(action_text, mode)
  → 路由到 capabilities/{mode}
  → command: LLM 解析 → 安检 → subprocess / 文件 IO
  → codegen: LLM 生成代码 → stdout
  → ExecuteResult + execution_log + jobs.db
```

## 模块间调用

```python
from shared.local_bus import call
from modules.executor.schemas import ExecuteRequest

# 命令执行（默认）
result = await call(
    "executor",
    "execute",
    ExecuteRequest(
        action_text="在 Local_agent 目录列出所有 .py 文件",
        caller_module="planning",
    ),
)

# 代码生成
result = await call(
    "executor",
    "execute",
    ExecuteRequest(
        mode="codegen",
        action_text="用 Python 写一个函数 parse_csv(path: str) -> list[dict]...",
        caller_module="planning",
    ),
)
code = result.stdout
```

## 本地 API（调试）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/executor/execute` | 提交任务（`mode` 可选） |
| POST | `/executor/chat` | 对话式（`mode` 可选） |
| GET | `/executor/jobs` | 任务列表 |
| GET | `/executor/jobs/{id}` | 任务详情 |

Web UI payload 可传 `mode: "codegen"` 切换子能力。

## LLM 槽位

| slot | 用途 |
|------|------|
| `executor.parse` | 命令执行 + 全部文件操作子能力的 JSON 解析（**共用**） |
| `executor.codegen` | 详细规格 → 完整代码 |

旧槽位（`executor.chat`、`executor.command.parse`、`executor.*.parse` 等）启动时自动合并为 `executor.parse`。

## 配置（`LA_EXECUTOR_`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `LA_EXECUTOR_DEFAULT_CWD` | `Local_agent/` 根 | 默认工作目录 |
| `LA_EXECUTOR_TIMEOUT_SECONDS` | `300` | shell.run 超时 |
| `LA_EXECUTOR_SHELL` | `powershell` | 终端 |

## 数据

- `data/executor/jobs.db` — 任务记录（含 `mode`）
- `data/executor/logs/{job_id}.log` — 执行日志

## 目录结构

```
modules/executor/
  capabilities/
    command/    # 命令执行子能力
    codegen/    # 代码生成子能力
  service.py    # 路由与 Web UI
  schemas.py    # 统一入参/出参
  runner.py     # shell / 文件 IO
```
