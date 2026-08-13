# 规划模块（planning）

接收用户目标 → 多轮**信息收集**（可选）→ **一次性**生成静态任务图（Task Graph）→ 可选拓扑执行。

Web UI：Server Center「规划」频道工作台（质询 / 环境探测 / 画布 / 执行）。  
其它模块：`local_bus.call("planning", …)`。详见 [INTEGRATION.md](INTEGRATION.md)。

## 状态

| 项 | 现状 |
|----|------|
| 出图 `plan` | ✅ |
| 质询 `clarify` / 环境探测 `run_env_query` | ✅ |
| 拓扑执行 `run_graph` | ✅ |
| `app/main` + Server Center / WS | ✅ |
| Web UI 工作台 | ✅（Server Center frontend） |
| 主对话黑盒 `run_task` | ✅（质询进 main 时间线） |
| HTTP router | ❌（走消息通道 + local_bus） |

## 原则

图中流动的只有 **DataBlock**。每个节点消费若干块、产出恰好一块；输入必须带 **role**。

| role | 用于 | 含义 |
|------|------|------|
| `body` | Action | 写文件附件正文（至多 1 个） |
| `context` | Action / Process | 仅依赖，不进附件 |
| `requirement` | Process | 真正规格（至少 1 个） |
| `material` | Process | 参考材料 |

起点系统块：`id=goal`。环境探测成功块：`env1`、`env2`…。

## 节点

| kind | 运行时 |
|------|--------|
| `action` | `executor.execute`；仅 `role=body` 进 `file_content` |
| `process` | `processor.process`；块带 `metadata.input_role` |

## LLM 槽位

| slot_key | 用途 |
|----------|------|
| `planning.clarify` | 信息是否足够；输出 questions / env_queries |
| `planning.plan` | 一次性生成 TaskGraph JSON |

## 模块元数据

| 项 | 值 |
|----|-----|
| 模块 ID | `planning` |
| 发送名 | `规划模块` / `planning` / `planner` |
| 常用 `msg_type` | `plan_result`、`clarify_result`、`env_probe_result`、`plan_progress`、`graph_run_result` |
| `target` | `user_ui` |

## 快速调用

```python
from shared.local_bus import call
from modules.planning.schemas import PlanRequest, ClarifyRequest

clarify = await call("planning", "clarify", ClarifyRequest(goal="…"))
outcome = await call("planning", "plan", PlanRequest(goal="…"))
```

原子方法：`clarify` / `run_env_query` / `plan` / `run_graph`。主对话走 `run_task`（黑盒）。
