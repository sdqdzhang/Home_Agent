# 主对话（main）

聊天 + Function Calling 编排。设计见 [docs/main-conversation.md](../../docs/main-conversation.md)。

## 已接通

- FC 循环（`main.chat` slot）
- **Core 工具**：`planning_run` / `executor_run` / `rag_query` / `rag_chat` / `env_collect` / `env_summary` / `env_screenshot` / `env_camera`
- **扩展工具**：由已加载扩展的 `capability.TOOLS` 合并进同一张表（例如 crawler 的 `crawler_fetch` / `crawler_fetch_batch`，paper 的 `paper_search_papers` 等）
- 规划黑盒桥接：质询进主对话时间线，模型只收最终结构化结果；等待用户回答时阻塞 FC
- 每轮开始拉取 `conversation_manager.context_for_main` 与 `emotion.context_for_main(session_id, user_text)`
- 每轮结束后依次：`conversation_manager.on_turn_end` → `emotion.on_turn_end`
- 注入：Tool Policy + Mind Context + Conversation State/Summary/Open Tasks

扩展未安装或未启用时，对应工具不会出现在 FC 表里。工具结果卡片由扩展包内 `invoke_tool` / `main_tools.py` 负责美化，不写死在 `main/runtime.py`。

## 不对主对话开放

`security`、`processor`、`memory`、`emotion`、`conversation_manager`（后两者由程序挂钩，非 FC）。
