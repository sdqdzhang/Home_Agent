# HomeAgent

本地 AI Agent 系统：在本机执行任务、检索知识、管理记忆，经 Web 控制台远程编排与审批。

## 仓库结构

| 目录 | 角色 |
|------|------|
| [Local_agent](Local_agent/) | 本地智能体运行时：模块化工具、规划 DAG、执行与安全、RAG、记忆等 |
| [Server_center](Server_center/) | 消息中转 + Vue 3 控制台：频道路由、RSA 加密、WebSocket、审批与可视化 |
| [plan_test](plan_test/) | 规划/执行/安全沙箱（实验与手测；**以 Local_agent 为准**） |

联调：根目录 `联调启动.bat`（先起 Server Center `:8765`，再起 Local Agent `:8770`）。

## 架构（代码现状）

```text
浏览器 Vue UI
    │  明文 HTTP / WS（同机信任域）
    ▼
Server Center（FastAPI + SQLite）
    │  RSA 分块加密 HTTP + 按模块 WebSocket
    ▼
Local Agent（FastAPI 单进程）
    ├── main                  主对话 + Function Calling
    ├── conversation_manager  会话 State / Analyzer / 记忆候选
    ├── planning              质询 → TaskGraph → 拓扑执行
    ├── executor + security   单步本机动作 + 规则/审批门禁
    ├── processor             DataBlock 变换（供规划 Process 节点）
    ├── rag / memory          Chroma + SQLite
    ├── env / crawler         本机观测 / 网页爬取
    └── terminal              独立 PTY 中继（不经安检）
```

模块互调走进程内 `local_bus`；对用户可见的进度、审批、结果走 Server Center 消息通道。

## 技术栈

- **后端**：Python · FastAPI · Pydantic v2 · SQLAlchemy · SQLite · ChromaDB
- **LLM**：OpenAI 兼容客户端；槽位注册表按角色绑定（默认 Ollama）
- **前端**：Vue 3 · Vite · Tailwind · xterm.js · 自研 SVG 任务图画布
- **通信**：WebSocket 推送 · RSA-OAEP 分块加密（Agent ↔ Server）

## 文档入口

- [Local Agent README](Local_agent/README.md) — 模块、API、LLM 槽位、配置
- [主对话设计](Local_agent/docs/main-conversation.md) — FC 工具表与会话管理
- [模块通信约定](Local_agent/docs/module-communication.md)
- [Server Center README](Server_center/README.md) — 消息协议与 Web UI
- [远程 mTLS 部署与运维](docs/remote-mtls.md) — 域名 + 客户端证书（方案 A，目标态）
