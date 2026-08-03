# 主对话（main）

聊天 + Function Calling 编排。设计见 [docs/main-conversation.md](../../docs/main-conversation.md)。

## 已接通

- FC 循环（`main.chat` slot）+ 工具表：`planning_run` / `executor_run` / `rag_*` / `env_*` / `crawler_fetch`
- 规划黑盒桥接：质询进主对话时间线，模型只收最终结构化结果；等待用户回答时阻塞 FC
- 每轮开始拉取 `conversation_manager.context_for_main` 与 `emotion.context_for_main`
- 每轮结束后依次：`conversation_manager.on_turn_end` → `emotion.on_turn_end`
- 注入：Tool Policy + Mind Context + Conversation State/Summary/Open Tasks

## 不对主对话开放

`security`、`processor`、`memory`、`emotion`、`conversation_manager`（后两者由程序挂钩，非 FC）。
