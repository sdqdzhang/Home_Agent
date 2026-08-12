# Mind / emotion 对接说明

## 谁可以调用

| 调用方 | 方式 | 允许 |
|--------|------|------|
| `main`（程序） | `context_for_main` / `on_turn_end` | ✅ |
| 其它模块 / 调试 | `get_snapshot` / `get_persona` / `set_persona` | ✅ |
| 主对话 LLM tool | — | ❌ |

## 人格切换

```python
from shared.local_bus import call

await call("emotion", "list_personas")
await call("emotion", "set_persona", "casual")
await call("emotion", "reload_persona")  # 重载当前
ctx = await call("emotion", "context_for_main", "default", "介绍一下自己吧")
```

环境变量：`LA_EMOTION_PERSONA=default`（见 `.env.example`）。规范：[PERSONA.md](./PERSONA.md)。

## 轮次挂钩（main）

```
轮前: emotion.context_for_main(session_id, user_text) + cm.context_for_main
轮后: cm.on_turn_end → emotion.on_turn_end
         → detect_program_events →（规则命中则）mind.analyze → 程序 apply
```

Mind Context 使用文案化标签（熟悉度/认知负荷/专注），不直接注入裸 float。
Persona Core 由 Resolver 按当前用户消息裁剪；Mind Advisor 再将相关人格片段与 Mind State 转成结构化回应策略。
`resolver_debug` / `advisor_debug` 记录调试信息，但不作为用户可见回答内容。

测试期主对话会追加 JSONL 调试日志：

```text
data/debug/mind_advisor_turns.jsonl
```

每行包含 user/assistant 文本、可用模块与工具、tool_trace、Mind Context、resolver_debug、advisor_debug，便于排查人格指导是否影响工具调用。

## UI → emotion

| action | 说明 |
|--------|------|
| `refresh` / `get_snapshot` / `get_persona` / `list_personas` | 推送 `mind_snapshot`（含 `enabled`） |
| `set_enabled` + `enabled` | 开关；持久化到 `data/emotion/enabled.json` |
| `set_persona` + `persona` | 切换人格并推送 |
| `reload_persona` | 重载文件 |

前端工作台：`EmotionWorkspace.vue`；请求封装：`utils/emotion.js`。

## LLM

- `mind.analyze`：轮后规则命中后的轻量状态分析
- `mind.advisor`：轮前人格回应指导，只输出结构化策略，不回答用户、不调用工具
