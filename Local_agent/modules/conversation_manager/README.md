# 会话管理（conversation_manager）

程序驱动的会话生命周期模块：**不是**主对话 Function Calling 工具。

设计见 [docs/main-conversation.md](../../docs/main-conversation.md) 与 [INTEGRATION.md](INTEGRATION.md)。

- **模块 ID**：`conversation_manager`
- **发送名**：`会话管理` / `cm`
- **消息类型**：`cm_snapshot` / `cm_event`

## 职责

| 做 | 不做 |
|----|------|
| 维护 Conversation State / Summary / Open Tasks | 当 FC 工具被 main 调用 |
| 规则触发 Analyzer（`conversation.analyze`） | 自己发起 planning |
| Memory Candidates → `memory.observe` | 把 memory 暴露给 main FC |

Mind Context（怎么说话）归 `emotion`；本模块回答「之前聊了什么」。

## 本地 API（local_bus）

| 方法 | 说明 |
|------|------|
| `on_turn_end(TurnEndEvent)` | main 每轮结束后由程序调用 |
| `get_snapshot(session_id)` | 规则命中、token 压力、State、Open Tasks |
| `context_for_main(session_id)` | 注入主模型的 State / Summary / Open Tasks |

## 两级触发

1. 规则过滤器（token 余量、长轮、状态过期等）
2. Analyzer LLM 更新 State / Summary / Memory Candidates / Open Tasks

Open Tasks 只保存在 snapshot 中。用户说「继续」时由 **main FC** 调 planning，本模块不发起规划。

## LLM 槽位

| slot | 用途 |
|------|------|
| `conversation.analyze` | 规则命中后更新 State / 记忆候选等 |

## UI

工作台只读展示 `cm_snapshot`；可发 `action=refresh` 请求再推一帧。
