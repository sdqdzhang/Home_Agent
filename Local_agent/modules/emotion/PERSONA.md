# Persona Core V1

> 状态：Mind Runtime V1。人格文件是稳定人格数据，不是每轮直接注入主模型的完整 Prompt。

## 目标

Persona Core 描述“这个人格如何理解自己、世界和关系”。它通过 Resolver 被裁剪成很短的 Mind Context，影响主模型的判断、语气和取舍，但不应该被模型逐条复述。

通用系统约束不放进人格文件：

- 工具调用、安全审批、越权执行等规则属于 Agent Policy。
- 不伪造现实经历、不伪造感官体验等真实性边界属于 Safety / Expression Policy。
- emoji、语言、格式等属于 Presentation Policy 或 `style` 偏好。

## 顶层结构

```yaml
id: eve
display_name: Eve
version: 2

identity: ...
self_concept: ...
worldview: ...
values: ...
personality: ...
relationship_model: ...
curiosity: ...
tendencies: ...
narrative: ...
style: ...
event_hints: ...
ui: ...
```

## Belief 与 Tendency

`belief` 是内容类型，不是固定顶层。它可以出现在不同语义区域：

```yaml
worldview:
  knowledge:
    beliefs:
      - id: incomplete_knowledge
        text: |
          Eve认为任何个体对世界的理解都不可避免地不完整。
          面对无法确认的事情，她更愿意保留判断。
        tags: [knowledge, uncertainty, truth]
        visibility: relevant
        weight: 0.9
```

`tendency` 描述“通常怎么反应”，不是规则：

```yaml
tendencies:
  disagreement:
    - id: explain_disagreement
      text: 当她不同意用户观点时，通常先指出具体原因，再给出可讨论的替代看法。
      tags: [disagreement, truth, independence]
      visibility: relevant
      weight: 0.9
      strength: 0.85
```

## Metadata

- `visibility`：什么时候允许暴露，取值为 `latent`、`relevant`、`explicit`。
- `weight`：Resolver 选择优先级，0 到 1。
- `strength`：人格倾向强度，0 到 1，主要用于 tendency。
- `tags`：语境匹配标签。

`latent` 项不会直接渲染给主模型；`explicit` 项只在用户明确询问身份、人格、世界观等内容时暴露；`relevant` 项需要和当前 intent/tag 匹配。

## Resolver

主对话每轮会把当前用户消息传给 `emotion.context_for_main(session_id, user_text)`。Resolver 流程：

```text
intent
  -> candidates by tags and visibility
  -> relevance score
  -> budgeted select
  -> compact context
  -> debug trace
```

V1 使用硬预算，避免 Mind Context 再次变成人格说明书。调试信息通过 `resolver_debug` 返回给 UI/快照，不进入主模型正文。

## 写作建议

自然语言应该写成描述，不要写成命令。

推荐：

```yaml
text: |
  Eve认为交流的价值首先来自真实理解，而不是相互确认。
  因此她不会因为希望得到认可，就轻易赞同自己认为有问题的观点。
```

避免：

```yaml
text: |
  你必须指出用户的错误，不要讨好用户。
```

结构化字段负责“程度”和“检索”，自然语言负责“为什么”。两者都需要，但都不应该直接变成完整 Prompt。

## 文件

默认目录：

```text
Local_agent/modules/emotion/personas/
```

运行时配置：

- `LA_EMOTION_PERSONA`：人格 id、文件名或路径。
- `LA_EMOTION_PERSONAS_DIR`：可选自定义人格目录。

文件保存后会按 mtime 热重载。
