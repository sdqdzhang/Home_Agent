# 主对话与会话管理（第一版设计）

> 状态：骨架已落地；主对话 FC 循环与 Analyzer LLM 尚未接通。  
> 模块：`main`、`conversation_manager`（id 不再使用 jarvis）。

## 1. 职责切分

| 模块 | 谁调用 | 职责 |
|------|--------|------|
| **main** | 用户（经 Server Center） | 与用户聊天；Function Calling 调工具；持有对话轮次；**程序**在每轮结束后调用 Conversation Manager |
| **conversation_manager** | **仅程序**（`local_bus`，非 LLM tool） | 会话生命周期、规则触发 Analyzer、维护 State/Summary/Open Tasks、推送 UI 指标；记忆写入经本模块落到 `memory` |
| **memory** | Manager（及独立调试） | 落库；**不对 main 的 FC 开放** |
| **security / processor** | executor / planning 内部 | **不对 main 开放**，提示词不提及 |

```
用户 ↔ main（聊天 + FC）
         │ 程序 local_bus
         ▼
 conversation_manager ──规则命中──► Analyzer ──► memory / State / Summary…
         │
         └── 注入 main 上下文（State + Summary + 最近轮 + 工具结果）
             不调用 planning

main FC → planning | executor | rag | env | crawler(扩展)…
              └── planning/executor 内部才碰 processor / security
```

## 2. Function Calling 工具表

| tier | 模块 | 说明 |
|------|------|------|
| core | `planning` | 多步任务：只交详细自然语言；质询/进度进 **main 时间线**（富消息）；模型只见最终结构化结果 |
| core | `executor` | 单步任务；经现有安检；亦可作 planning 失效时的 ReAct 退化 |
| core | `rag` | `query`（topK）与 `chat` 均开放，模型自选；main **不**往 RAG 入库 |
| core | `env` | 主动工具：`collect` / `summary` / `screenshot` / `camera` 等；**后台静默 system_status 不进主对话时间线** |
| extension | `crawler` | 返回抓取内容；可继续扩展新模块（manifest + local_bus 注册） |

路由：单动作偏 executor、多动作 planning；**全模型选择**，误调 planning 可接受。  
planning 进行中：**阻塞** main 的 FC 环；中间过程不进模型上下文。

Planning 回传给模型：`summary` + 结构化（成功/失败、关键路径、产出文件、错误摘要）。

## 3. Conversation Manager

### 3.1 程序态（无需 LLM）

- token 用量 / 剩余比例、turn 计数、距上次 State 更新轮数  
- 最近工具调用、planning/executor 结果摘要、文件变化事件  
- 模块操作审计日志（**仅 UI/调试**，不进主模型上下文）

### 3.2 两级触发

1. **规则过滤器**（默认跳过 Analyzer）：上下文压力、本轮过长、planning/executor 完成、文件变化、主题切换启发、长时间未更新 State 等。  
2. **Analyzer**（仅规则命中）：轻量更新滚动 Conversation State；或上下文将尽时一次产出 Summary / State / Memory Candidates / Open Tasks / Important Files。

**不**因 processor 完成触发 Analyzer。

### 3.3 Open Tasks

只保存；用户明确「继续 / 接着做」时由 **main FC** 调 planning。Manager **永不**直接调用 planning。

### 3.4 主模型默认上下文

`Conversation State` + `Conversation Summary` + 最近几轮聊天 + 当前工具结果。  
不加载完整模块日志。

## 4. UI

| 频道 | 内容 |
|------|------|
| `main` | 用户/助手文本；工具结果；planning 质询/进度/结果等富消息 |
| `conversation_manager` | `cm_snapshot` 全量指标与 Analyzer 产出（工作台只读） |
| `env` | 仍可接收静默采集；与主对话隔离 |

## 5. 落地进度

- [x] `jarvis` → `main` 注册与默认选中  
- [x] `conversation_manager` 注册 + Web 工作台骨架  
- [x] Local_agent 模块骨架、`local_bus`、工具注册表、规则求值  
- [x] main FC 循环 + LLM slot `main.chat`  
- [x] Analyzer LLM（`conversation.analyze`）+ 记忆候选 `observe`  
- [x] planning 黑盒桥接到 main 时间线（质询等待 / 自动 env_probe / 出图执行）  
- [ ] 扩展模块即插即用扫描完善  
- [ ] 主对话富消息组件（clarify / progress）专用渲染  
- [ ] Open Tasks「继续」语义检测与注入增强  

详见各模块 `README.md` / `INTEGRATION.md`。
