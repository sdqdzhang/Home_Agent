# 规划模块（占位）

> **状态：未开发。** 本目录仅预留模块 ID、名称与消息类型约定，便于后续实现；尚未接入 `app/main.py`，无 HTTP 路由与业务逻辑。

## 定位（草案）

在 HomeAgent 中负责 **复杂目标 → 可执行子任务** 的分解与编排，例如：

- 接收用户或主对话的高层目标
- 拆分为可交给 crawler / rag / executor 等模块的步骤
- 向 Server Center 推送 `plan_result`，供 Web UI「规划」频道展示

与 **执行模块**（真正跑命令）、**自省模块**（事后反思）形成「规划 → 执行 → 反思」链路；具体算法与调度策略待设计。

## Server Center 集成（已预留）

| 项 | 值 |
|----|-----|
| 模块 ID | `planning` |
| 发送名 | `规划模块` / `planning` / `planner` |
| 常用 `msg_type` | `plan_result`、`text` |
| `target` | `user_ui` |

### `plan_result` 消息格式（占位）

```json
{
  "goal": "整理项目文档并写入 RAG",
  "summary": "分三步：爬取、清洗、入库",
  "status": "draft",
  "steps": [
    { "title": "爬取 README 所在站点", "target_module": "crawler" },
    { "title": "切块入库", "target_module": "rag" }
  ]
}
```

`status` 建议取值：`draft` | `active` | `completed`（实现时可调整）。

## 后续开发 checklist

1. 在 `app/main.py` 注册 `PlanningService` 与 WebSocket 频道
2. 实现 `service.py` / `router.py` / `schemas.py`（可参考 `modules/crawler` 结构）
3. 如需 LLM，在 `shared/llm/slots.py` 增加 `planning.*` 槽位
4. 与主对话、执行模块的调用关系在实现阶段再定
