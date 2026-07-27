# 主对话（main）

聊天 + Function Calling 编排。设计见 [docs/main-conversation.md](../../docs/main-conversation.md)。

## 已接通

- FC 循环（`main.chat` slot）+ 工具表：`planning_run` / `executor_run` / `rag_*` / `env_*` / `crawler_fetch`
- 规划黑盒桥接：质询进主对话时间线，模型只收最终结构化结果；等待用户回答时阻塞 FC
- 每轮结束后程序调用 `conversation_manager.on_turn_end`
- Manager 上下文（State / Summary / Open Tasks）注入系统提示

## 不对主对话开放

`security`、`processor`、`memory`（记忆由 Conversation Manager 写入）。
