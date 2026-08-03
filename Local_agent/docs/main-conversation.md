# 主对话与会话管理 / 心智状态

> 状态：**已接通**。main FC、`conversation.analyze`、Mind（`emotion` / `mind.analyze` / 人格 YAML）、planning 黑盒、记忆候选 `observe` 均已落地。  
> 模块：`main`、`conversation_manager`、`emotion`（Mind）。  
> 待办：扩展模块即插即用扫描、Open Tasks「继续」语义等（见文末）。

## 1. 职责切分

| 模块 | 谁调用 | 职责 |
|------|--------|------|
| **main** | 用户（经 Server Center） | 聊天 + FC；轮前拉取 CM / Mind 上下文；轮后通知 CM 与 Mind |
| **conversation_manager** | **仅程序**（`local_bus`） | 会话 State/Summary/Open Tasks；规则触发 Analyzer；记忆候选 → `memory` |
| **emotion（Mind）** | **仅程序**（`local_bus`） | 情绪连续性、work_mode、关系熟悉度；规则触发 `mind.analyze`；注入 Mind Context |
| **memory** | Manager（及独立调试） | 落库；**不对 main 的 FC 开放** |
| **security / processor** | executor / planning 内部 | **不对 main 开放** |

```
用户 ↔ main（聊天 + FC）
         │ 程序 local_bus
         ├─► conversation_manager ──► State / Summary / memory…
         └─► emotion (Mind) ──► 情绪衰减或 Analyzer ──► persona_state UI
         │
         └── 注入：Tool Policy + Mind Context + Conversation State/Summary + 最近轮

main FC → planning | executor | rag | env | crawler(扩展)…
```

**Mind Context** 回答「现在该怎么说话」；**Conversation Context** 回答「之前聊了什么」。二者分开注入。

## 2. Function Calling 工具表

| tier | 模块 | 说明 |
|------|------|------|
| core | `planning` | 多步任务：只交详细自然语言；质询/进度进 **main 时间线**；模型只见最终结构化结果 |
| core | `executor` | 单步任务；经现有安检 |
| core | `rag` | `query` / `chat`；main **不**往 RAG 入库 |
| core | `env` | `collect` / `summary` / `screenshot` / `camera`；静默 `system_status` 不进主时间线 |
| extension | `crawler` | 抓取内容 |

`emotion` / `conversation_manager` / `memory` / `security` / `processor` **不是** FC 工具。

## 3. Conversation Manager

### 3.1 程序态

- token 用量、turn 计数、距上次 State 更新轮数  
- 工具 / planning / executor 结果摘要、文件变化  
- 模块审计日志（仅 UI，不进主模型）

### 3.2 两级触发

1. 规则过滤器 → 2. Analyzer（`conversation.analyze`）更新 State / Summary / Memory Candidates / Open Tasks。

### 3.3 Open Tasks

只保存；用户说「继续」时由 **main FC** 调 planning。

## 4. Mind（emotion）

### 4.1 程序态

- 情绪 intensity 衰减；过低回落「平静」  
- 熟悉度按轮次累计  
- work_mode 可由 planning/executor 结果推断  
- 只读 CM 的 topic/project，不双写任务事实  

### 4.2 Analyzer（`mind.analyze`）

规则命中（工具完成、长轮、情感启发词、模式切换、过期）后，LLM 建议 mood/intensity/vibe/behavior_hints；强度有最大步长。  
无事件时不调 LLM，只衰减。

### 4.3 人格与开关

- YAML/JSON：`modules/emotion/personas/`，`LA_EMOTION_PERSONA`；见 `PERSONA.md`。
- **总开关**：默认关闭。关闭时主对话不注入 Mind、不跑状态更新。`LA_EMOTION_ENABLED` 或工作台开关（`data/emotion/enabled.json`）。

## 5. 主模型默认上下文

`Tool Policy（SYSTEM_PROMPT）` + `Mind Context` + `Conversation State/Summary/Open Tasks` + 最近几轮 + 当前工具结果。

## 6. UI

| 频道 | 内容 |
|------|------|
| `main` | 用户/助手文本；工具与 planning 富消息 |
| `conversation_manager` | `cm_snapshot` |
| `emotion` | `persona_state`（mood/text；不触发未读） |
| `env` | 静默采集，与主对话隔离 |

## 7. 落地进度

- [x] `main` / `conversation_manager` / planning 黑盒  
- [x] Mind 模块骨架、规则、衰减、`mind.analyze`、main 注入与轮末通知  
- [x] `persona_state` 推送  
- [x] 人格 YAML/JSON 加载器与热切换（见 PERSONA.md）  
- [ ] 扩展模块即插即用扫描完善  
- [x] 主对话富消息专用渲染（execution_log / system_status；截图/拍照沿用专用卡片）  
- [ ] Open Tasks「继续」语义增强  

详见 `modules/*/README.md` / `INTEGRATION.md`。
