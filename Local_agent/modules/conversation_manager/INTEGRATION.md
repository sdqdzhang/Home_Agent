# Conversation Manager 对接说明

## 谁可以调用

| 调用方 | 方式 | 允许 |
|--------|------|------|
| `main`（程序） | `local_bus.call("conversation_manager", "on_turn_end", …)` | ✅ |
| 其它模块（程序） | 上报文件变化等事件（后续扩展） | ✅ |
| 主对话 LLM tool | — | ❌ |
| 本模块 → `planning` | — | ❌ |

记忆写入由本模块在 Analyzer 产出 Memory Candidates 后调用 `memory`（待实现）；**不**把 memory 暴露给 main FC。

## 进程内

```python
from shared.local_bus import call
from modules.conversation_manager.schemas import TurnEndEvent

snap = await call(
    "conversation_manager",
    "on_turn_end",
    TurnEndEvent(
        session_id="…",
        turn_index=3,
        user_text="…",
        assistant_text="…",
        context_used_tokens=1200,
        context_limit_tokens=8000,
        planning_completed=False,
        executor_completed=True,
    ),
)
```

注入主对话上下文：

```python
ctx = await call("conversation_manager", "context_for_main", "session_id")
# 或 get_snapshot
```

## UI

- 频道：`conversation_manager` / 发送名 `会话管理`
- `msg_type=cm_snapshot`：全量 `ManagerSnapshot`
- 前端工作台只读展示；可发 `action=refresh` 请求再推一帧

## Open Tasks

只保存在 snapshot / State 中。用户表达继续后，由 **main** 的 FC 调 `planning`；Manager 不发起规划。
