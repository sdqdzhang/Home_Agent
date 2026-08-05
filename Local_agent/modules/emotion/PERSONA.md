# 人格配置文件规范（已接入）

> 状态：**已实现加载器**。通过 `LA_EMOTION_PERSONA` 选择人格；支持 YAML/JSON；文件变更会自动热重载。

## 目标

把自称、身份、价值观、行为原则、交流风格、禁止项等**稳定人格信息**集中到一个文件。  
运行时 Mind 模块读取该文件，生成 Mind Context 的「人格基础」段落；**不**把工具调用策略写进人格文件（留在 `main` Tool Policy）。

## 路径

```
Local_agent/modules/emotion/personas/
  default.yaml      # 默认
  casual.yaml       # 示例：更随意
```

| 环境变量 | 说明 |
|----------|------|
| `LA_EMOTION_PERSONA` | 人格 id（如 `default` / `casual`）、文件名，或绝对/相对路径 |
| `LA_EMOTION_PERSONAS_DIR` | 可选自定义人格目录；空则用模块内 `personas/` |

## 字段（YAML）

```yaml
id: default
display_name: 可靠助手
version: 1

# 可直接注入模型；若省略，将由 identity/values/… 自动拼装
summary: |
  你是 HomeAgent 的长期本地助手：…

identity:
  name: HomeAgent
  role: 本地长期协作助手
  self_reference: 我

values:
  - 诚实
principles:
  - 不确定时明确说明不确定
style:
  tone: 清晰直接
  language: 中文
  humor: low
  formality: medium
  emoji: false
prohibitions:
  - 不使用表情符号或 emoji
ui:
  personality: 可靠谨慎
  traits:
    - 耐心

# 可选：人格专属启发词，与程序通用词表合并（猫系例子见 cat2.yaml）
# event_hints:
#   playful: []
#   appreciation: []
#   task_success: []
#   negative: []
#   generic_positive: []
```

也支持同结构的 `.json`。

## 制作与切换

1. 复制 `personas/default.yaml` → `mentor.yaml`，改字段，`summary` 建议 ≤ 400 字。
2. `.env` 设 `LA_EMOTION_PERSONA=mentor`，或 UI / `set_persona` 切换（会写入 `data/emotion/active_persona.json`，重启仍保持）。
3. 改文件保存后，下次读 persona 时会按 mtime 自动重载。

## 不要放进人格文件

- 工具路由细则（Tool Policy）
- 当前情绪 / work_mode / 熟悉度（动态 Mind State）
- 会话摘要与 Open Tasks（Conversation Manager）
- **通用**情感启发词（放 `events.py`）；人格只放专属词（`event_hints`）

## 与动态状态

| 层 | 来源 | 变化频率 |
|----|------|----------|
| Persona 文件 | 人编辑 / `set_persona` | 很少 |
| Emotion / Relationship / work_mode / interaction_mode | 程序 + `mind.analyze` | 每轮可能 |
| Mind Context | 模板拼装 | 每轮 |

Personality「缓慢演变」仍不开放；长期偏好走 CM / memory。
