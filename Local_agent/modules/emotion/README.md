# 情感与状态 / Mind（emotion）

程序驱动的心智与状态模块：维护短期情绪连续性，并向主对话注入 **Mind Context**。

- **模块 ID**：`emotion`
- **发送名**：`情感与性格状态模块`
- **消息类型**：`persona_state`
- **不是** main 的 Function Calling 工具

## 总开关

| 状态 | 行为 |
|------|------|
| **关闭**（默认） | 主对话不注入 Mind Context，不跑情绪更新；与接入前一致 |
| **开启** | 注入人格/状态，轮末 Analyzer / 衰减生效 |

- 环境变量：`LA_EMOTION_ENABLED=false|true`（初始默认）
- 运行时：工作台开关或 `set_enabled`；写入 `data/emotion/enabled.json`，优先于环境变量
- `local_bus.call("emotion", "is_enabled")` / `set_enabled(True|False)`

| 做 | 不做 |
|----|------|
| 人格文件即插即用（YAML/JSON） | 会话摘要、Open Tasks（归 CM） |
| 情绪 / 精力 / 专注 + 衰减与事件跃迁 | 双写项目/任务事实 |
| work_mode、关系熟悉度 | Live2D / TTS |
| Mind Context → main | 每轮改人格核心 |

## 关键 API（local_bus）

| 方法 | 说明 |
|------|------|
| `context_for_main(session_id)` | 开启时返回 Mind Context；关闭时 `mind_context=""` |
| `on_turn_end(MindTurnEndEvent)` | 仅开启时更新状态 |
| `is_enabled()` / `set_enabled(bool)` | 总开关 |
| `get_snapshot` / `get_persona` / `list_personas` | 调试与列举 |
| `set_persona(spec)` / `reload_persona(spec?)` | 切换 / 重载人格 |

## 人格

- 目录：`personas/*.yaml`（见 [PERSONA.md](./PERSONA.md)）
- 环境变量：`LA_EMOTION_PERSONA`（默认 `default`）、可选 `LA_EMOTION_PERSONAS_DIR`
- 文件 mtime 变化自动热重载
- UI：`mind_snapshot` 推送**整理后**人格视图（非 YAML 原文）+ 人格下拉切换

## 情绪模型

- **程序**：衰减 intensity；熟悉度累计；work_mode 可由工具结果推断。
- **LLM（`mind.analyze`）**：规则命中时建议 mood/intensity/vibe/behavior_hints。

触发：`tool_completed` / `long_turn` / `stale_mind` / `affective_hint` / `mode_shift`。  
`persona_state` **仅在实质状态变化时推送**（UI `refresh` 仍可主动拉）。

## 文件

```
emotion/
  service.py
  persona_loader.py / persona_schema.py / config.py
  personas/default.yaml / casual.yaml
  context.py / continuity.py / rules.py / analyzer.py
  PERSONA.md / INTEGRATION.md
```
