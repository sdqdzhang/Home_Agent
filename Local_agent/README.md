# Local Agent

HomeAgent 本地智能体服务：单进程托管多个功能模块，与 Server Center 通过 RSA 加密 HTTP + WebSocket 通信。

## 目录结构

```
Local_agent/
├── app/                    # 主服务入口与 Server Center 客户端
│   ├── main.py
│   ├── config.py
│   └── server_client/      # RSA 加密 + WebSocket
├── shared/
│   ├── llm/                # OpenAI 兼容模型 + 注册表（SQLite）
│   │   ├── client.py       # LLMClient / get_llm_client(slot)
│   │   ├── registry.py     # ModelRegistry.resolve()
│   │   ├── storage.py      # llm_endpoints / llm_bindings
│   │   ├── service.py      # WebSocket 配置请求处理
│   │   └── slots.py        # 槽位定义
│   └── server_center/      # Server Center RSA 分块加密 + 消息发送（各模块复用）
├── modules/
│   ├── crawler/            # 网页爬取模块
│   ├── env/                # 环境感知模块（高频采集 / 低频汇报）
│   ├── rag/                # RAG 检索增强（Chroma + 手动入库）
│   └── security/           # 安全检查（四列表 + 审批）
│       ├── lists/          # 白/黑命令与目录（文本配置）
│       └── INTEGRATION.md  # 执行模块对接说明
├── data/                   # 运行时数据（勿提交）
├── keys/                   # 客户端 RSA 密钥（勿提交）
└── test/                   # 各模块图形界面测试（tkinter）
```

## 测试

见 [test/README.md](test/README.md)。快速启动：

```bash
python test/test_llm_gui.py      # LLM 调用（临时指定 URL/模型）
python test/test_llm_registry.py # 注册表单元测试
python test/test_llm_registry_gui.py  # 注册表 tk 可视化（本地直连 DB）
python test/test_crawler_gui.py  # 爬取（可勾选是否使用模型）
python test/test_env_gui.py      # 环境感知（可勾选是否使用模型）
python test/test_rag_gui.py      # RAG 入库与问答
python test/test_security_gui.py # 安全检查（需 Server Center）
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
playwright install chromium   # 可选，用于动态页面

cp .env.example .env
# 编辑 .env：Server Center 地址、Ollama 模型等

uvicorn app.main:app --reload --host 0.0.0.0 --port 8770
```

确保 Server Center 已在 `8765` 运行，且 Ollama 已拉取对应模型。

## 网页爬取流程

1. **自适应路由**：根据 URL 模式选择 `feedparser` / `httpx_bs4` / `playwright`，并可按响应头降级切换
2. **模型判断**：本地模型评估爬取是否成功
3. **失败调参**：模型建议并合并新的 `config` 后重试
4. **预设过滤**：`main_text` / `title_summary` / `link_list` / `metadata` 四种算法
5. **模型择优**：从过滤结果中选出最合适项
6. **兜底提炼**：若均不满足，由模型直接处理原始内容

## API（本地调试）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/crawler/crawl` | 提交爬取任务 |
| POST | `/crawler/chat` | 与模块本地模型对话（带记忆） |
| GET | `/crawler/jobs` | 任务列表 |
| GET | `/crawler/jobs/{id}/log` | 读取任务日志 |
| GET | `/crawler/artifacts` | 产物文件列表 |
| GET | `/env/status` | **主 Agent 读取**：最新快照 + 压缩统计 + LLM 总结 |
| POST | `/env/collect` | 手动触发一次采集 |
| POST | `/env/summary` | 手动触发 10 分钟窗口压缩与总结 |
| POST | `/env/screenshot` | 按需桌面截图 |
| GET | `/rag/status` | RAG 知识库状态 |
| POST | `/rag/ingest/file` | 手动导入文件到向量库 |
| POST | `/rag/ingest/text` | 手动导入文本 |
| POST | `/rag/query` | 检索问答（可指定 K、summarize） |
| POST | `/rag/chat` | 带会话的 RAG 对话 |
| GET | `/security/status` | 四列表、待审批与近期记录 |
| POST | `/security/check` | 命令安全检查（可阻塞至审批结束） |
| POST | `/security/chat` | 安全模块对话 |

### 主 Agent 读取环境状态

```bash
curl http://127.0.0.1:8770/env/status
```

返回 `snapshot`（最新 20s 采集）、`aggregated`（当前窗口压缩）、`llm_summary`（模型/规则总结）、`alert_active`。

### 爬取示例

```bash
curl -X POST http://127.0.0.1:8770/crawler/crawl \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "task": "提取主页正文"}'
```

### 对话示例

```bash
curl -X POST http://127.0.0.1:8770/crawler/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "最近一次爬取结果怎么样？", "session_id": "user-1"}'
```

## 与 Server Center 集成

### 网页爬取

- 模块名：`网页爬取模块` / `crawler`
- 上报类型：`execution_log`

### 环境感知

- 模块名：`环境感知模块` / `env_sense` / `env`
- 上报类型：`system_status`（20s 快照、10min 总结、告警）、`desktop_screenshot`（按需截图）
- 截图等大 payload 使用 RSA 分块加密（`shared/server_center` 统一发送）
- Web UI 可点「远程截图」；消息 `payload.action=screenshot` 亦可触发
- `system_status.message.alert=true` 时前端环境模块左侧显示红灯；恢复后 `alert=false` 自动熄灭

详见 [环境感知消息格式](modules/env/README.md)。

### RAG

- 模块名：`RAG模块` / `rag`
- 上报类型：`rag_result`（问答）、`execution_log`（入库）
- Web UI 左侧选「RAG 模块」可直接对话；`summarize` 控制模型总结或直接返回片段

详见 [RAG 模块文档](modules/rag/README.md)。

### 安全检查

- 模块名：`安全检查模块` / `security`
- 上报类型：`approval_request`（红色审批）、`security_yellow_log`（黄色记录）、`text`（对话）
- Web UI 左侧选「安全检查模块」：四块布局（待审批 / 黄色记录 / 审批界面 / 审批历史 + 对话）
- 四列表文件：`modules/security/lists/*.txt`

详见 [安全检查模块文档](modules/security/README.md)；执行模块对接见 [INTEGRATION.md](modules/security/INTEGRATION.md)。

### 模型配置（LLM 注册表）

- 模块名：`本地Agent` / `local_agent` / `llm`
- Web UI：Server Center 左侧 **模型配置**（`LlmConfigWorkspace`）
- 本地调试：`python test/test_llm_registry_gui.py` 或 `test/run_llm_registry_gui.bat`
- 响应类型：`llm_config_result`

前端经 `POST /api/v1/messages/local`（`target=本地Agent`）发配置 action，Local Agent 写 SQLite 后回推 `llm_config_result`。详见下文 [LLM 模型配置](#llm-模型配置sharedllm)。

### 测试推送到 Server Center

1. 启动 Server Center：`uvicorn app.main:app --port 8765`
2. 运行 `python test/test_env_gui.py`
3. 填写地址（如 `http://127.0.0.1:8765`），点 **测试连接**
4. 勾选 **推送到 Server Center**，点 **采集一次**
5. 打开 Web UI → 左侧点击 **环境感知模块**（不是主对话）
6. 可看到 `system_status` 卡片；截图需在前端点 **远程截图**（仅响应服务端请求，test 不主动截图）

### 通用

- 用户从 Web UI 发往各模块的 `text` 消息会触发对应对话或动作
- 执行过程通过 RSA 加密推送到 `user_ui`

## LLM 模型配置（shared/llm）

各模块的 LLM 调用统一走 **SQLite 注册表**（`data/llm.db`），支持 OpenAI 兼容后端（Ollama、vLLM、云 API 等）。运行时以 **DB 为准**；`.env` 仅用于 **首次 seed** 和 **槽位未绑定时的 fallback**。

### 数据库

路径：`data/llm.db`（`LLMSettings.db_path`）

**表 1：`llm_endpoints`** — 模型/端点档案

| 字段 | 说明 |
|------|------|
| `id` | 主键，如 `ep_default_chat` |
| `name` | 展示名 |
| `capability` | `chat` 或 `embed` |
| `base_url` / `api_key` / `default_model` | OpenAI 兼容连接信息 |
| `timeout` / `max_tokens` / `temperature` | 默认推理参数 |
| `enabled` | 是否启用 |

**表 2：`llm_bindings`** — 槽位绑定

| 字段 | 说明 |
|------|------|
| `slot_key` | 主键，如 `rag.summarize` |
| `endpoint_id` | 外键 → `llm_endpoints.id`（`ON DELETE RESTRICT`） |
| `model_override` | 可选，同端点下换模型名 |
| `temperature_override` / `max_tokens_override` | 可选覆盖 |

**删除约束**：端点仍被 binding 引用时禁止删除，并返回友好错误（需先在 UI 改绑槽位）。

**首次启动**：`app/main.py` 调用 `get_model_registry().ensure_seeded()`；DB 为空时按当前 `.env` 写入 3 个端点 + 11 个绑定。

### 槽位（Slot）

| slot_key | 模块 | 能力 | 用途 |
|----------|------|------|------|
| `default.chat` | shared | chat | 未绑定槽位的 chat 回退目标 |
| `rag.summarize` | rag | chat | RAG 问答总结 |
| `rag.split` | rag | chat | 语义分块裁判 |
| `rag.embed` | rag | embed | 文档向量化 |
| `crawler.pipeline` | crawler | chat | 爬取判断/调参/过滤 |
| `crawler.chat` | crawler | chat | 爬虫对话 |
| `env.summary` | env | chat | 监控周期总结 |
| `env.chat` | env | chat | 环境问答 |
| `security.judge` | security | chat | 黄色升红判定 |
| `security.chat` | security | chat | 安全模块对话 |
| `security.auto_approve` | security | chat | 模型自动审批 |

主对话（jarvis）暂未接入。

### 配置优先级（resolve）

```
1. slot 有 binding 且端点 enabled → 使用 binding + endpoint（source=binding）
2. 无 binding → 回退 default.chat（capability 一致时，source=default_fallback）
3. 仍无 → 读 .env 默认值（source=env_fallback）
```

### 代码调用

**Chat 类模块** — `get_llm_client(slot)`，每次请求从注册表解析最新配置：

```python
from shared.llm import get_llm_client

llm = get_llm_client("rag.summarize")
reply = await llm.chat(messages)           # → str
data = await llm.chat_json(messages)       # → dict（JSON 模式）
```

**Embed** — `OllamaEmbedder` 内部 `resolve("rag.embed")`：

```python
from modules.rag.index.embedder import OllamaEmbedder

embedder = OllamaEmbedder()  # slot 默认 rag.embed
vectors = embedder.embed(["文本"])
```

**各模块实际绑定**

| 组件 | slot |
|------|------|
| `RagAssistant` | `rag.summarize` |
| `SemanticSplitJudge` | `rag.split` |
| `OllamaEmbedder` | `rag.embed` |
| `CrawlerAssistant` 流水线 | `crawler.pipeline` |
| `CrawlerAssistant` 对话 | `crawler.chat` |
| `EnvAssistant` 总结 | `env.summary` |
| `EnvAssistant` 问答 | `env.chat` |
| `SecurityJudge` | `security.judge` |
| `SecurityAssistant` | `security.chat` |
| `SecurityAutoApprover` | `security.auto_approve` |

**注册表 CRUD（Python）**

```python
from shared.llm import get_model_registry

registry = get_model_registry()
registry.snapshot()                    # 端点 + 绑定 + 各 slot 解析结果
registry.resolve("rag.summarize")      # ResolvedLLMConfig
registry.create_endpoint(...)
registry.upsert_binding("rag.summarize", "ep_default_chat")
registry.delete_endpoint("ep_xxx")   # 有引用时 EndpointInUseError
```

**测试/临时覆盖** — 传入 `LLMSettings` 实例，不读 DB：

```python
from shared.llm import LLMClient, LLMSettings

client = LLMClient(LLMSettings(base_url="...", model="..."))
```

### Web UI 配置（Server Center）

1. 启动 Server Center 与 Local Agent
2. Web UI 左侧 → **模型配置**
3. 操作：刷新、新建/编辑/删除端点、改绑槽位、模型覆盖

**请求**（`POST /api/v1/messages/local`）：

```json
{
  "name": "user_ui",
  "target": "本地Agent",
  "msg_type": "text",
  "message": {
    "role": "user",
    "payload": {
      "request_id": "uuid",
      "action": "llm_config_list"
    }
  }
}
```

**action 列表**

| action | 说明 |
|--------|------|
| `llm_config_list` | 拉取完整 snapshot |
| `llm_endpoint_create` | `payload.endpoint` |
| `llm_endpoint_update` | `payload.endpoint_id` + `endpoint` |
| `llm_endpoint_delete` | `payload.endpoint_id` |
| `llm_binding_upsert` | `slot_key` + `endpoint_id` + 可选 `model_override` |

**响应**（`msg_type: llm_config_result`，`target: user_ui`）：

```json
{
  "request_id": "uuid",
  "ok": true,
  "action": "llm_config_list",
  "data": {
    "endpoints": [...],
    "bindings": [...],
    "slots": [...],
    "resolved": { "rag.summarize": { "model": "...", "source": "binding" } }
  }
}
```

失败时 `ok: false`，`error.code` 可为 `endpoint_in_use` / `invalid_request` 等。

### .env 与 seed 默认值

| 变量 | seed 用途 |
|------|-----------|
| `LA_LLM_BASE_URL` / `LA_LLM_API_KEY` / `LA_LLM_MODEL` | 默认 chat 端点、`default.chat` 等 |
| `LA_LLM_TIMEOUT` / `LA_LLM_MAX_TOKENS` / `LA_LLM_TEMPERATURE` | chat 默认参数 |
| `LA_RAG_EMBED_*` | `rag.embed` 端点 |
| `LA_RAG_SPLIT_MODEL` | `rag.split` 端点 |
| `LA_ENV_LLM_MODEL` / `LA_ENV_LLM_TEMPERATURE` | seed 时写入 `env.*` binding 的覆盖值 |

DB 有数据后，修改上述 `.env` **不会**覆盖已有端点；仅在没有 binding 的 fallback 路径生效。

## 配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `LA_PORT` | `8770` | 本地服务端口 |
| `LA_SERVER_CENTER_URL` | `http://127.0.0.1:8765` | Server Center |
| `LA_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Ollama OpenAI 端点（**seed / fallback**） |
| `LA_LLM_MODEL` | `llama3.2` | 默认 chat 模型名（**seed / fallback**） |
| `LA_LLM_TIMEOUT` | `120` | 请求超时（秒） |
| `LA_LLM_MAX_TOKENS` | `4096` | 默认 max_tokens |
| `LA_LLM_TEMPERATURE` | `0.2` | 默认 temperature |
| `LA_CRAWLER_MAX_RETRIES` | `3` | 爬取重试次数 |
| `LA_ENV_COLLECT_INTERVAL_SECONDS` | `20` | 环境采集间隔 |
| `LA_ENV_SUMMARY_INTERVAL_SECONDS` | `600` | LLM 总结间隔（10 分钟） |
| `LA_ENV_PING_TARGET` | `8.8.8.8` | Ping 目标 |
| `LA_RAG_TOP_K` | `5` | RAG 默认召回 K |
| `LA_RAG_MIN_SCORE` | `0.25` | RAG 最低相似度 |
| `LA_RAG_SPLIT_MODE` | `rule` | 分块：`rule` / `semantic` / `semantic_embedding` / `structural` |
| `LA_RAG_SPLIT_MODEL` | `qwen2.5:3b` | 语义分块裁判模型（**seed**） |
| `LA_RAG_EMBED_MODEL` | `nomic-embed-text` | 向量模型（**seed**） |
| `LA_RAG_EMBED_BASE_URL` | 同 Ollama | 向量 API（**seed**） |
| `LA_RAG_SUMMARIZE` | `true` | 是否由本地模型总结 |
| `LA_SECURITY_APPROVAL_TIMEOUT_SECONDS` | `300` | 安全审批超时（秒） |
| `LA_SECURITY_USE_MODEL_FOR_YELLOW` | `true` | 黄色是否调用模型升红 |
| `LA_ENV_LLM_MODEL` | — | 可选，seed 时写入 env 槽位覆盖 |
| `LA_ENV_LLM_TEMPERATURE` | `0.2` | seed 时 env 槽位温度覆盖 |

## 数据位置

- LLM 注册表：`data/llm.db`（端点 + 槽位绑定）
- 日志：`data/crawler/logs/{job_id}.log`
- 产物：`data/crawler/artifacts/{job_id}.json`
- 数据库：`data/crawler/crawler.db`（任务记录 + 对话记忆）
- RAG：`data/rag/chroma/`、`data/rag/rag.db`
- 安全审计：`data/security/security.db`
