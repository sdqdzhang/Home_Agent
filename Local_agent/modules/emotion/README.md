# 情感与状态 / Mind（emotion）

程序驱动的 Mind Runtime：维护短期情绪连续性，读取稳定 Persona Core，并通过 Resolver + Advisor 向主对话注入紧凑 **Mind Context**。

- **模块 ID**：`emotion`
- **发送名**：`情感与性格状态模块`
- **消息类型**：`persona_state` / `mind_snapshot`
- **不是** main 的 Function Calling 工具

## 总开关

| 状态 | 行为 |
|------|------|
| **关闭**（默认） | 主对话不注入 Mind Context，不跑情绪更新；与接入前一致 |
| **开启** | 注入 Resolver 裁剪后的 Mind Context，轮末事件检测 / Analyzer / 状态更新生效 |

- 环境变量：`LA_EMOTION_ENABLED=false|true`（初始默认）
- 运行时：工作台开关或 `set_enabled`；写入 `data/emotion/enabled.json`，优先于环境变量
- 当前人格：工作台切换写入 `data/emotion/active_persona.json`，优先于 `LA_EMOTION_PERSONA`

| 做 | 不做 |
|----|------|
| Persona Core 即插即用（YAML/JSON） | 会话摘要、Open Tasks（归 CM） |
| mood + intensity + persistence；**有效事件优先于衰减** | User Model / Experience 库（归 memory） |
| `cognitive_load` / `focus`（程序粗估，可被 Analyzer 覆盖） | 双写项目/任务事实 |
| work_mode + interaction_mode、familiarity + current_warmth | Live2D / TTS / 四维关系 |
| Resolver → Compact Mind Context（含 Policy 边界） | 每轮改人格核心 / 把完整 YAML 当 Prompt |

## 状态字段

- **Emotion**：`mood`（7 标签）、`intensity`、`cognitive_load`、`focus`、`persistence`、`unresolved_affect`
- **Relationship**：`familiarity`（长期，事件累计）、`current_warmth`（短期亲近感，可快升快降）、`turn_count`、`meaningful_turns`、`vibe`
- **Work mode**：任务阶段（`idle|chat|deep_tech|clarifying|executing|wrapping_up`）
- **Interaction mode**：说话姿态（`chat|playful|task|supportive|exploratory`），与 work_mode 正交

## 轮前：Resolver + Advisor

主对话每轮开始调用 `context_for_main(session_id, user_text)`：

```
user_text
  → detect_intent（self_intro / persona_question / disagreement / task / chat）
  → Resolver：按 visibility + tags 打分，硬预算选出少量人格片段
  → Advisor：在 self_intro / persona_question / disagreement / chat（及 supportive/exploratory）时调用 mind.advisor
  → 任务意图走程序默认策略（人格降权，不强制调 LLM）
  → Compact Mind Context（含 Policy 边界）注入主模型
```

Resolver 规则（`resolver.py`）：

- `latent` 永不直接渲染
- `explicit` 仅在 `self_intro` / `persona_question` 暴露（自我介绍、人格/价值观提问）
- `relevant` 按 intent tags 与 weight / strength 打分，最多约 5 条 / 700 字

调试字段 `resolver_debug` / `advisor_debug` 进 UI 快照，不进主模型正文。人格文件写法见 [PERSONA.md](./PERSONA.md)。

## 轮末流水线

```
turn_end
  → detect_program_events（工具成败 / 夸奖 / 玩闹 / 任务成功…）
  → 规则门控 → 可选 mind.analyze（解释事件意义）
  → 程序 apply：
      · 有效情绪事件 → 更新/维持 intensity（不走自然衰减）
      · 无有效事件 → 按 persistence 衰减 intensity，并回落 warmth
      · 更新 familiarity / current_warmth / interaction_mode
  → 推送 persona_state / mind_snapshot
```

触发规则：`tool_completed` / `long_turn` / `stale_mind` / `affective_hint` / `mode_shift`。

细分正向事件：`user_appreciation` / `playful_interaction` / `task_success`（以及工具类）；泛化兜底仍可用 `affective_positive`。

## 本地 API（local_bus）

| 方法 | 说明 |
|------|------|
| `context_for_main(session_id, user_text="")` | 开启时返回 Mind Context、`resolver_debug`、`advisor_debug`；关闭时 `mind_context=""` |
| `on_turn_end(MindTurnEndEvent)` | 仅开启时更新状态 |
| `is_enabled()` / `set_enabled(bool)` | 总开关 |
| `get_snapshot` / `get_persona` / `list_personas` | 调试与列举 |
| `set_persona(spec)` / `reload_persona(spec?)` | 切换 / 重载人格 |

## 人格

- 目录：`personas/*.yaml`（内置如 `default` / `casual` / `cute` 等；见 [PERSONA.md](./PERSONA.md)）
- 环境变量：`LA_EMOTION_PERSONA`（默认 `default`）、可选 `LA_EMOTION_PERSONAS_DIR`
- Persona Core 不直接作为 Prompt 注入；`resolver.py` 按当前用户消息选择少量相关人格片段。
- `advisor.py` 调用 `mind.advisor` 槽位，把相关人格片段与 Mind State 转成结构化回应策略（mode / stance / tone / verbosity 等）。
- 安全、真实性、工具越权等通用约束属于 `policy.py`，不属于人格核心。
- 文件保存后按 mtime 热重载。

## LLM 槽位

| slot | 用途 |
|------|------|
| `mind.analyze` | 规则命中后解释事件意义 |
| `mind.advisor` | 轮前生成结构化回应策略 |

## 文件

```
emotion/
  service.py
  events.py / continuity.py / rules.py / analyzer.py / context.py
  persona_loader.py / persona_schema.py / resolver.py / advisor.py / policy.py / config.py
  personas/*.yaml
  PERSONA.md / INTEGRATION.md
```
