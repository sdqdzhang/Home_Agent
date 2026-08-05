# 情感与状态 / Mind（emotion）

程序驱动的心智与状态模块：维护短期情绪连续性，并向主对话注入 **Mind Context**。

- **模块 ID**：`emotion`
- **发送名**：`情感与性格状态模块`
- **消息类型**：`persona_state` / `mind_snapshot`
- **不是** main 的 Function Calling 工具

## 总开关

| 状态 | 行为 |
|------|------|
| **关闭**（默认） | 主对话不注入 Mind Context，不跑情绪更新；与接入前一致 |
| **开启** | 注入人格/状态，轮末事件检测 / Analyzer / 状态更新生效 |

- 环境变量：`LA_EMOTION_ENABLED=false|true`（初始默认）
- 运行时：工作台开关或 `set_enabled`；写入 `data/emotion/enabled.json`，优先于环境变量

| 做 | 不做 |
|----|------|
| 人格文件即插即用（YAML/JSON） | 会话摘要、Open Tasks（归 CM） |
| mood + intensity + persistence；**有效事件优先于衰减** | User Model / Experience 库（归 memory） |
| `cognitive_load` / `focus`（程序粗估，可被 Analyzer 覆盖） | 双写项目/任务事实 |
| work_mode + interaction_mode、familiarity + current_warmth | Live2D / TTS / 四维关系 |
| Mind Context → main（含表达边界） | 每轮改人格核心 |

## 状态字段

- **Emotion**：`mood`（7 标签）、`intensity`、`cognitive_load`、`focus`、`persistence`、`unresolved_affect`
- **Relationship**：`familiarity`（长期，事件累计）、`current_warmth`（短期亲近感，可快升快降）、`turn_count`、`meaningful_turns`、`vibe`
- **Work mode**：任务阶段（`idle|chat|deep_tech|clarifying|executing|wrapping_up`）
- **Interaction mode**：说话姿态（`chat|playful|task|supportive|exploratory`），与 work_mode 正交

## 轮末流水线

```
turn_end
  → detect_program_events（工具成败 / 夸奖 / 玩闹 / 任务成功…）
  → 规则门控 → 可选 mind.analyze（解释事件意义）
  → 程序 apply：
      · 有效情绪事件 → 更新/维持 intensity（不走自然衰减）
      · 无有效事件 → 按 persistence 衰减 intensity，并回落 warmth
      · 更新 familiarity / current_warmth / interaction_mode
  → 注入 Mind Context（含表达边界）/ 推送 UI
```

触发规则仍为：`tool_completed` / `long_turn` / `stale_mind` / `affective_hint` / `mode_shift`。

细分正向事件：`user_appreciation` / `playful_interaction` / `task_success`（以及工具类）；泛化兜底仍可用 `affective_positive`。

## 本地 API（local_bus）

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

## 文件

```
emotion/
  service.py
  events.py / continuity.py / rules.py / analyzer.py / context.py
  persona_loader.py / persona_schema.py / config.py
  personas/default.yaml / casual.yaml
  PERSONA.md / INTEGRATION.md
```
