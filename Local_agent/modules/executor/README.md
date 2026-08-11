# 执行模块

HomeAgent **行动层**：将明确动作落地处理，不负责规划、决策或判断任务是否完成。

## 定位

| 负责 | 不负责 |
|------|--------|
| 自然语言自动路由到子能力并返回事实 | 理解模糊需求、规划、推断下一步 |
| 命令执行：解析 → 安检 → shell/文件 IO | 补全参数、修改目标、自动重试 |

动作无法唯一确定 → 返回 `not_executable`。

## 入口

`ExecuteRequest`：

- **只需** `action_text`（自然语言）；`mode` **可选**
- `mode` 缺省：LLM 先路由到子能力，再走该子能力原有解析/执行链（两阶段）
- `mode` 显式传入：跳过路由，强制该子能力（调试用）
- `file_content`：附件正文，**不送入**路由 LLM / 解析 LLM；有附件时必须路由到 `write_file`，否则 `not_executable`

## 子能力（`mode`）

| mode | 说明 | 安检 | LLM 槽位 |
|------|------|------|----------|
| `command` | shell.run | 是 | `executor.parse` |
| `read_file` / `write_file` / `delete_file` | 文件读写删（读写均可选 `start_line`/`end_line` 行范围） | 是 | `executor.parse` |
| `browse_dir` / `search_file` / `search_content` | 目录浏览 / 搜文件 / 搜内容 | 是 | `executor.parse` |

路由本身使用槽位 `executor.route`：专用文件能力仅在意图明确时选用，**其余一律兜底到 `command`（Shell）**。

### write_file — 附件

- 正文来源优先级：`file_content`（附件）→ Markdown 代码块 → LLM `content`
- 附件正文不进 LLM；有附件时模型只解析目标路径（及可选行范围）
- 有附件却未判定为 `write_file`（含用 shell 写文件）→ 错误
- 可选 `start_line`/`end_line`（1-based 闭区间）：只替换该区间与文件行数的交集；起始行超过文件末尾则在末尾追加；未指定则整文件覆盖
## 核心流程

```
ExecuteRequest(action_text[, mode][, file_content])
  → mode 缺省: executor.route → 确定 mode
  → 有附件且 mode ≠ write_file → not_executable
  → capabilities/{mode}: LLM 解析 → 安检 → 执行
  → ExecuteResult + execution_log + jobs.db
```

## 模块间调用

```python
from shared.local_bus import call
from modules.executor.schemas import ExecuteRequest

# 自动路由（推荐）
result = await call(
    "executor",
    "execute",
    ExecuteRequest(
        action_text="在 Local_agent 目录列出所有 .py 文件",
        caller_module="planning",
    ),
)

# 强制子能力（可选）
result = await call(
    "executor",
    "execute",
    ExecuteRequest(
        mode="command",
        action_text="Get-ChildItem -Recurse -Filter *.py",
        caller_module="planning",
    ),
)
```

## 本地 API（调试）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/executor/execute` | 提交任务（`mode` 可选） |
| POST | `/executor/chat` | 对话式（`mode` 可选） |
| GET | `/executor/jobs` | 任务列表 |
| GET | `/executor/jobs/{id}` | 任务详情 |

## LLM 槽位

| slot | 用途 |
|------|------|
| `executor.route` | 自然语言 → 子能力 `mode` |
| `executor.parse` | 命令 / 文件类 JSON 解析（共用） |

旧槽位（`executor.chat`、`executor.command.parse`、`executor.*.parse` 等）启动时自动合并为 `executor.parse`；缺省时补齐 `executor.route`。已移除的槽位（如 `executor.codegen`）启动时删除 binding。

## 配置（`LA_EXECUTOR_`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `LA_EXECUTOR_DEFAULT_CWD` | `Local_agent/` 根 | 默认工作目录 |
| `LA_EXECUTOR_TIMEOUT_SECONDS` | `300` | shell.run 超时 |
| `LA_EXECUTOR_SHELL` | `powershell` | 终端 |

## 数据

- `data/executor/jobs.db` — 任务记录（含解析后的 `mode`）
- `data/executor/logs/{job_id}.log` — 执行日志

## 目录结构

```
modules/executor/
  mode_router.py   # 子能力自动路由
  capabilities/
    command/       # 命令执行
    files/         # 文件类子能力
  service.py       # 路由与 Web UI
  schemas.py       # 统一入参/出参
  runner.py        # shell / 文件 IO
```
