# Local Agent

HomeAgent 本地智能体服务：单进程托管多个功能模块，通过 RSA 加密 HTTP 与 WebSocket 与 Server Center 通信，为 Web UI 提供爬取、环境感知、RAG、执行、安全审查、记忆等能力。

**版本**：`0.2.0`（`app/main.py`）

## 架构概览

```mermaid
flowchart TB
    subgraph UI["Server Center / Web UI"]
        SC[Server Center :8765]
        UI[Web UI 各频道]
    end

    subgraph LA["Local Agent :8770"]
        APP[app/main.py]
        BUS[shared/local_bus]
        LLM[shared/llm 注册表]
        TERM[terminal/bridge PTY]

        subgraph MOD["功能模块"]
            CR[crawler]
            EN[env]
            RG[rag]
            SEC[security]
            MEM[memory]
            EX[executor]
        end
    end

    SC <-->|RSA HTTP + WS| APP
    UI <-->|消息频道| SC
    APP --> MOD
    MOD --> BUS
    BUS -->|进程内直调| MOD
    MOD --> LLM
    TERM <-->|/ws/terminal_agent| SC
```

| 模块 | ID | 职责 |
|------|-----|------|
| 网页爬取 | `crawler` | 自适应引擎爬取、过滤、模型判断与对话 |
| 环境感知 | `env` | 20s 采集、10min 压缩总结、告警、截图/摄像头 |
| RAG | `rag` | Chroma 向量库、多策略分块、检索问答 |
| 安全检查 | `security` | 四列表规则、黄/红审批、模型升红与自动审批 |
| 记忆 | `memory` | 观察打分、工作记忆、向量归档、三维检索、反思 |
| 执行 | `executor` | 自然语言自动路由子能力 → 安检 → 执行 |
| 处理 | `processor` | 要求 + DataBlock 上下文 → 产出一个 DataBlock |
| LLM 配置 | `llm` / `local_agent` | SQLite 端点与槽位绑定，供 Web UI 管理 |
| 远程终端 | — | Web 端 PTY 桥接（不经 AI 与安全检查） |
| 规划 | `planning` | 目标→质询/探测→TaskGraph→执行；Web UI 工作台 + `local_bus` |
| 主对话 | `main` | 聊天 + FC 编排（骨架）；见 [docs/main-conversation.md](docs/main-conversation.md) |
| 会话管理 | `conversation_manager` | 程序驱动 State/Analyzer；指标工作台；非 FC 工具 |

模块间同步调用走 `shared.local_bus`；需 UI 展示或审批留痕时走 `ServerCenterClient`。约定见 [docs/module-communication.md](docs/module-communication.md)。

## 目录结构

```
Local_agent/
├── app/                        # FastAPI 入口与 Server Center 客户端
│   ├── main.py
│   ├── config.py
│   └── server_client/
├── shared/
│   ├── llm/                    # OpenAI 兼容客户端 + SQLite 注册表
│   ├── server_center/          # RSA 加密消息 + WebSocket 监听
│   └── local_bus.py            # 模块进程内互调门面
├── modules/
│   ├── crawler/                # 网页爬取
│   ├── env/                    # 环境感知
│   ├── rag/                    # RAG 检索增强
│   ├── security/             # 安全检查（lists/ 四列表配置）
│   ├── memory/                 # 长期记忆
│   ├── executor/               # 执行（command / 文件操作）
│   ├── processor/              # 处理（要求 + DataBlock → DataBlock）
│   ├── terminal/               # 远程终端 PTY 桥
│   ├── planning/               # 规划（TaskGraph；见 INTEGRATION.md）
│   ├── main/                   # 主对话（FC 编排骨架）
│   └── conversation_manager/   # 会话管理（规则 + Analyzer 骨架）
├── docs/
│   ├── module-communication.md
│   └── main-conversation.md    # 主对话 / Manager 第一版设计
├── data/                       # 运行时数据（勿提交）
├── keys/                       # 客户端 RSA 密钥（勿提交）
├── test/                       # tkinter 图形测试（见 test/README.md）
├── requirements.txt
└── .env.example
```

## 快速启动

```bash
cd Local_agent
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium   # 可选，动态页面爬取

cp .env.example .env
# 编辑 .env：Server Center 地址、Ollama 模型等

uvicorn app.main:app --reload --host 127.0.0.1 --port 8770
```

前置条件：

- Server Center 已在 `8765` 运行（联调可用仓库根目录 `联调启动.bat`）
- Ollama 已拉取所需模型（如 `llama3.2`、`nomic-embed-text`、`qwen2.5:3b`）

健康检查：

```bash
curl http://127.0.0.1:8770/health
```

## 本地 API（调试）

HTTP 路由仅供 curl / GUI 调试；**模块互调禁止走 `:8770` HTTP**。

### 通用

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 各模块与终端桥接状态 |

### 网页爬取 `/crawler`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/crawl` | 提交爬取任务 |
| POST | `/chat` | 带记忆的模块对话 |
| GET | `/jobs` | 任务列表 |
| GET | `/jobs/{id}` | 单任务详情 |
| GET | `/jobs/{id}/log` | 任务日志 |
| GET | `/artifacts` | 产物列表 |
| GET | `/artifacts/{filename}` | 下载产物 |

爬取流水线：自适应引擎（feedparser / httpx+BS4 / Playwright）→ 成功判定 → 失败调参重试 → 四种预设过滤 → 模型择优或兜底提炼。

### 环境感知 `/env`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/status` | 最新快照 + 压缩统计 + LLM 总结 + 告警状态 |
| POST | `/collect` | 手动触发一次采集 |
| POST | `/summary` | 手动触发窗口压缩与总结 |
| POST | `/screenshot` | 桌面截图 |
| POST | `/camera` | 摄像头采集 |
| POST | `/chat` | 基于系统状态问答 |

### RAG `/rag`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/status` | 知识库状态 |
| POST | `/ingest/file` | 导入文件 |
| POST | `/ingest/text` | 导入文本 |
| POST | `/query` | 检索问答 |
| POST | `/chat` | 带会话的 RAG 对话 |
| GET | `/documents` | 文档列表 |
| POST | `/delete/chunks` | 删除指定块 |
| POST | `/delete/document` | 删除文档 |
| POST | `/delete/collection` | 清空集合 |

分块策略：`rule` / `semantic` / `semantic_embedding` / `structural`（见 `LA_RAG_SPLIT_MODE`）。

### 安全检查 `/security`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/status` | 四列表、待审批与近期记录 |
| POST | `/check` | 命令检查（可阻塞至审批结束） |
| GET | `/records/yellow` | 黄色记录 |
| GET | `/records/approvals` | 审批历史 |
| POST | `/chat` | 安全模块对话 |
| POST | `/auto-approve` | 模型自动审批 |
| POST | `/reload-lists` | 重载列表文件 |
| GET | `/lists` | 读取四列表 |
| PUT | `/lists/{list_key}` | 更新列表 |

四列表文件：`modules/security/lists/*.txt`。执行模块对接见 [modules/security/INTEGRATION.md](modules/security/INTEGRATION.md)。

### 记忆 `/memory`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/status` | 工作记忆 / 核心记忆 / 归档统计 |
| POST | `/observe` | 观察事件并打分入库 |
| POST | `/ingest-dialogue` | 对话总结后归档 |
| POST | `/recall` | 向量 + 标签加权检索 |
| GET | `/context` | 当前工作记忆上下文 |
| POST | `/reflect` | 从工作记忆提炼洞察 |
| GET | `/core` | 核心记忆列表 |
| POST | `/core` | 写入核心记忆 |
| DELETE | `/core/{key}` | 删除核心记忆 |

### 执行 `/executor`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/execute` | 提交动作（`mode` 可选；缺省由 LLM 自动路由） |
| POST | `/chat` | 对话式执行 |
| GET | `/jobs` | 任务列表 |
| GET | `/jobs/{id}` | 单任务详情 |
| POST | `/jobs/{id}/cancel` | 取消任务 |
| POST | `/jobs/cancel` | 批量取消 |

缺省只传自然语言；LLM 先选子能力（`command` / 文件类），再解析执行。`mode` 显式传入时可强制子能力。有 `file_content` 附件时必须走 `write_file`，附件正文不进 LLM。

```python
from shared.local_bus import call
from modules.executor.schemas import ExecuteRequest

result = await call("executor", "execute", ExecuteRequest(
    action_text="列出当前目录下所有 .py 文件",
    caller_module="planning",
))
```

详见 [modules/executor/README.md](modules/executor/README.md)。

## 与 Server Center 集成

各模块启动时向 Server Center 注册，并通过 WebSocket 频道接收 `text` 等消息；执行过程以 RSA 加密推送到 `user_ui`。

| 模块 | 发送名 / ID | 主要 `msg_type` | 文档 |
|------|-------------|-----------------|------|
| 网页爬取 | `网页爬取模块` / `crawler` | `execution_log` | — |
| 环境感知 | `环境感知模块` / `env` | `system_status`、`desktop_screenshot` | [modules/env/README.md](modules/env/README.md) |
| RAG | `RAG模块` / `rag` | `rag_result`、`execution_log` | [modules/rag/README.md](modules/rag/README.md) |
| 安全检查 | `安全检查模块` / `security` | `approval_request`、`security_yellow_log`、`text` | [modules/security/README.md](modules/security/README.md) |
| 记忆 | `记忆模块` / `memory` | `memory_record`、`text` | — |
| 执行 | `执行模块` / `executor` | `execution_log` | [modules/executor/README.md](modules/executor/README.md) |
| LLM 配置 | `本地Agent` / `local_agent` | `llm_config_result` | 下文 |
| 规划 | `规划模块` / `planning` | `plan_result`、`text` | [modules/planning/README.md](modules/planning/README.md) · [INTEGRATION.md](modules/planning/INTEGRATION.md) |
| 远程终端 | — | WebSocket `/ws/terminal_agent` | `LA_TERMINAL_ENABLED` |

**推送联调示例**（环境感知）：

1. 启动 Server Center 与 Local Agent
2. 运行 `python test/test_env_gui.py`，填写 Server 地址并测试连接
3. 勾选「推送到 Server Center」，点「采集一次」
4. Web UI 左侧进入「环境感知模块」查看 `system_status` 卡片

## LLM 模型配置

各模块 LLM 调用统一走 **SQLite 注册表**（`data/llm.db`），支持 OpenAI 兼容后端（Ollama、vLLM、云 API 等）。运行时以 **DB 为准**；`.env` 仅用于首次 seed 与槽位未绑定时的 fallback。

### 解析优先级

```
1. slot 有 binding 且端点 enabled → binding + endpoint（source=binding）
2. 无 binding → 回退 default.chat（source=default_fallback）
3. 仍无 → 读 .env（source=env_fallback）
```

### 槽位一览

| slot_key | 模块 | 用途 |
|----------|------|------|
| `default.chat` | shared | 未绑定槽位的 chat 回退 |
| `rag.summarize` / `rag.split` / `rag.embed` | rag | 问答总结 / 语义分块 / 向量化 |
| `crawler.pipeline` / `crawler.chat` | crawler | 爬取流水线 / 对话 |
| `env.summary` / `env.chat` | env | 周期总结 / 问答 |
| `security.judge` / `security.chat` / `security.auto_approve` | security | 升红判定 / 对话 / 自动审批 |
| `memory.assess` / `memory.reflect` / `memory.summarize` / `memory.tag` / `memory.embed` | memory | 打分 / 反思 / 对话总结 / 标签 / 向量化 |
| `executor.route` / `executor.parse` | executor | 子能力路由 / 动作解析 |

### 代码调用

```python
from shared.llm import get_llm_client, get_model_registry

llm = get_llm_client("rag.summarize")
reply = await llm.chat(messages)
data = await llm.chat_json(messages)

registry = get_model_registry()
registry.snapshot()                       # 端点 + 绑定 + 解析结果
registry.resolve("rag.summarize")         # ResolvedLLMConfig
```

### Web UI 配置

Server Center 左侧 **模型配置** 经 `POST /api/v1/messages/local`（`target=本地Agent`）下发 action：

| action | 说明 |
|--------|------|
| `llm_config_list` | 拉取完整 snapshot |
| `llm_endpoint_create` / `llm_endpoint_update` / `llm_endpoint_delete` | 端点 CRUD |
| `llm_binding_upsert` | 槽位绑定 |

本地调试：`python test/test_llm_registry_gui.py` 或 `test/run_llm_registry_gui.bat`。

首次启动时 `ensure_seeded()` 按 `.env` 写入默认端点与绑定；DB 已有数据后修改 `.env` 不会覆盖已有记录。

## 配置

复制 `.env.example` 为 `.env`。常用变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `LA_HOST` | `127.0.0.1` | 监听地址 |
| `LA_PORT` | `8770` | 本地服务端口 |
| `LA_SERVER_CENTER_URL` | `http://127.0.0.1:8765` | Server Center |
| `LA_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Ollama OpenAI 端点（seed / fallback） |
| `LA_LLM_MODEL` | `llama3.2` | 默认 chat 模型 |
| `LA_CRAWLER_MAX_RETRIES` | `3` | 爬取重试次数 |
| `LA_ENV_COLLECT_INTERVAL_SECONDS` | `20` | 环境采集间隔 |
| `LA_ENV_SUMMARY_INTERVAL_SECONDS` | `600` | LLM 总结间隔 |
| `LA_RAG_SPLIT_MODE` | `rule` | 分块策略 |
| `LA_RAG_TOP_K` / `LA_RAG_MIN_SCORE` | `5` / `0.25` | RAG 召回参数 |
| `LA_SECURITY_APPROVAL_TIMEOUT_SECONDS` | `300` | 审批超时 |
| `LA_EXECUTOR_DEFAULT_CWD` | Local_agent 根 | 执行默认工作目录 |
| `LA_TERMINAL_ENABLED` | `true` | 远程终端桥接 |

完整列表见 [.env.example](.env.example)。

## 数据位置

| 路径 | 内容 |
|------|------|
| `data/llm.db` | LLM 端点与槽位绑定 |
| `data/crawler/` | 爬取日志、产物、`crawler.db` |
| `data/rag/` | Chroma 向量库、`rag.db` |
| `data/memory/` | 记忆向量库与工作记忆 DB |
| `data/security/security.db` | 安全审计 |
| `data/executor/` | 执行任务与日志 |
| `keys/` | RSA 客户端密钥 |

清理工具：`python test/test_storage_gui.py`（建议先停止 Agent）。

## 测试

各模块提供 tkinter 图形测试，详见 [test/README.md](test/README.md)。

```bash
python test/test_llm_gui.py           # LLM 直连调用
python test/test_llm_registry_gui.py  # 注册表可视化
python test/test_crawler_gui.py       # 爬取（可切换是否用模型）
python test/test_env_gui.py           # 环境感知 + Server 推送
python test/test_rag_gui.py           # RAG 入库与问答
python test/test_security_gui.py      # 安全检查（需 Server Center）
python test/test_storage_gui.py       # 日志与数据清理
```

Windows 可双击 `test/` 下对应 `.bat` 启动。
