# 执行模块

HomeAgent **行动层**：将明确动作准确执行，不负责规划、决策或判断任务是否完成。

## 定位

| 负责 | 不负责 |
|------|--------|
| 解析明确动作 → 执行 → 如实返回事实 | 理解用户需求、规划、推断下一步 |
| PowerShell / 路径 / 编码等执行策略 | 补全参数、修改目标、自动重试 |

动作无法唯一执行 → 返回 `not_executable`，**不执行、不写 jobs.db**。

## 动作类型（第一版）

| type | 说明 |
|------|------|
| `shell.run` | PowerShell 命令 |
| `file.read` | 直接读文件（不经 shell） |
| `file.write` | 直接写文件（不经 shell） |

自然语言动作由 `executor.chat` LLM 转为上述 JSON；代码校验后执行。

**带正文的 `file.write`**：正文优先从用户消息中的 ` ``` ` 代码块或 `payload.file_content`（附件）原样提取，不由模型抄写全文。

### file.write 正文来源（优先级）

1. `file_content`（Web UI 附件 / API）
2. 消息内 Markdown ` ``` ` 代码块（多块时取最大）
3. LLM JSON 的 `content`（仅适合短文本、无代码块时）

## 核心流程

```
ExecuteRequest(action_text)
  → LLM 解析 JSON Action
  → SecurityService.check()（file 映射为 executor:file.read/write 伪命令）
  → subprocess / 文件 IO
  → ExecuteResult + execution_log + jobs.db
```

## 模块间调用

```python
from shared.local_bus import call
from modules.executor.schemas import ExecuteRequest

result = await call(
    "executor",
    "execute",
    ExecuteRequest(
        action_text="在 Local_agent 目录列出所有 .py 文件",
        caller_module="planning",
        caller_request_id="plan_001",
    ),
)
```

详见 [docs/module-communication.md](../../docs/module-communication.md)。

## 本地 API（调试）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/executor/execute` | 提交明确动作 |
| POST | `/executor/chat` | 对话式执行（同 Web UI） |
| GET | `/executor/jobs` | 任务列表 |
| GET | `/executor/jobs/{id}` | 任务详情 |
| GET | `/executor/jobs/{id}/log` | 日志 tail |

## Server Center

| 项 | 值 |
|----|-----|
| 模块名 | `执行模块` / `executor` |
| `msg_type` | `execution_log` |
| Web UI | 执行频道发自然语言，经 LLM 解析后执行 |

## 配置（`LA_EXECUTOR_`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `LA_EXECUTOR_DEFAULT_CWD` | `Local_agent/` 根 | 默认工作目录；启动时若不在白目录则自动追加 |
| `LA_EXECUTOR_TIMEOUT_SECONDS` | `300` | shell.run 超时 |
| `LA_EXECUTOR_SHELL` | `powershell` | 终端 |

## LLM 槽位

| slot | 用途 |
|------|------|
| `executor.chat` | 自然语言动作 → JSON Action |

## 数据

- `data/executor/jobs.db` — 任务记录
- `data/executor/logs/{job_id}.log` — 执行日志
