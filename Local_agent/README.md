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
│   └── llm/                # OpenAI 兼容本地模型（默认 Ollama，各模块复用）
├── modules/
│   └── crawler/            # 网页爬取模块
│       ├── strategies/     # feedparser / httpx+BS4 / Playwright 自适应路由
│       ├── filters/        # 预设过滤算法
│       ├── pipeline/       # 爬取编排流程
│       ├── model/          # 模块内本地模型助手
│       ├── logging/        # 任务独立日志
│       ├── storage/        # 任务记录与产物
│       └── chat/           # 对话记忆
├── data/                   # 运行时数据（勿提交）
├── keys/                   # 客户端 RSA 密钥（勿提交）
└── test/                   # 各模块图形界面测试（tkinter）
```

## 测试

见 [test/README.md](test/README.md)。快速启动：

```bash
python test/test_llm_gui.py      # LLM 调用
python test/test_crawler_gui.py  # 爬取（可勾选是否使用模型）
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

- 模块名：`网页爬取模块` / `crawler`
- 上报类型：`execution_log`
- 用户从 Web UI 发往爬取模块的 `text` 消息会触发对话；`payload.url` 会触发爬取任务
- 执行过程通过 RSA 加密推送到 `user_ui`

## 配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `LA_PORT` | `8770` | 本地服务端口 |
| `LA_SERVER_CENTER_URL` | `http://127.0.0.1:8765` | Server Center |
| `LA_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Ollama OpenAI 端点 |
| `LA_LLM_MODEL` | `llama3.2` | 模型名 |
| `LA_CRAWLER_MAX_RETRIES` | `3` | 爬取重试次数 |

## 数据位置

- 日志：`data/crawler/logs/{job_id}.log`
- 产物：`data/crawler/artifacts/{job_id}.json`
- 数据库：`data/crawler/crawler.db`（任务记录 + 对话记忆）
