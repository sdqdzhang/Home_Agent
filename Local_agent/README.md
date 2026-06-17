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
│   ├── llm/                # OpenAI 兼容本地模型
│   └── server_center/      # Server Center RSA 分块加密 + 消息发送（各模块复用）
├── modules/
│   ├── crawler/            # 网页爬取模块
│   ├── env/                # 环境感知模块（高频采集 / 低频汇报）
│   └── rag/                # RAG 检索增强（Chroma + 手动入库）
│       ├── collectors/     # 系统指标采集
│       ├── model/          # LLM 运营总结
│       ├── aggregator.py   # 10 分钟窗口统计压缩
│       └── screenshot.py   # 按需桌面截图
├── data/                   # 运行时数据（勿提交）
├── keys/                   # 客户端 RSA 密钥（勿提交）
└── test/                   # 各模块图形界面测试（tkinter）
```

## 测试

见 [test/README.md](test/README.md)。快速启动：

```bash
python test/test_llm_gui.py      # LLM 调用
python test/test_crawler_gui.py  # 爬取（可勾选是否使用模型）
python test/test_env_gui.py      # 环境感知（可勾选是否使用模型）
python test/test_rag_gui.py      # RAG 入库与问答
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

## 配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `LA_PORT` | `8770` | 本地服务端口 |
| `LA_SERVER_CENTER_URL` | `http://127.0.0.1:8765` | Server Center |
| `LA_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Ollama OpenAI 端点 |
| `LA_LLM_MODEL` | `llama3.2` | 模型名 |
| `LA_CRAWLER_MAX_RETRIES` | `3` | 爬取重试次数 |
| `LA_ENV_COLLECT_INTERVAL_SECONDS` | `20` | 环境采集间隔 |
| `LA_ENV_SUMMARY_INTERVAL_SECONDS` | `600` | LLM 总结间隔（10 分钟） |
| `LA_ENV_PING_TARGET` | `8.8.8.8` | Ping 目标 |
| `LA_RAG_TOP_K` | `5` | RAG 默认召回 K |
| `LA_RAG_MIN_SCORE` | `0.25` | RAG 最低相似度 |
| `LA_RAG_SPLIT_MODE` | `rule` | 分块：`rule` / `semantic` / `semantic_embedding` / `structural` |
| `LA_RAG_SPLIT_MODEL` | `qwen2.5:3b` | 语义分块裁判模型 |
| `LA_RAG_SUMMARIZE` | `true` | 是否由本地模型总结 |

## 数据位置

- 日志：`data/crawler/logs/{job_id}.log`
- 产物：`data/crawler/artifacts/{job_id}.json`
- 数据库：`data/crawler/crawler.db`（任务记录 + 对话记忆）
- RAG：`data/rag/chroma/`、`data/rag/rag.db`
