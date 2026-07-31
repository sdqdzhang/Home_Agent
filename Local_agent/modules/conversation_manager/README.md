# 会话管理（conversation_manager）

程序驱动的会话生命周期模块：**不是**主对话 Function Calling 工具。

设计见 [docs/main-conversation.md](../../docs/main-conversation.md) 与 [INTEGRATION.md](INTEGRATION.md)。

## 能力

| API | 说明 |
|-----|------|
| `on_turn_end` | main 每轮结束后由程序 `local_bus.call` |
| `get_snapshot` / `context_for_main` | 指标与注入主模型的 State/Summary |
| UI `cm_snapshot` | 工作台展示规则命中、token 压力、State、Open Tasks 等 |

规则命中后走 Analyzer LLM（`conversation.analyze`）；产出的 Memory Candidates 经本模块调用 `memory.observe` 落库（不对 main FC 开放）。
