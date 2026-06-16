# Server Center

HomeAgent 消息中转站：接收各模块 RSA 加密消息，按 `target` 路由，提供 Web UI 远程查看与审批。

## 功能概览

- REST API 接收/查询/回复消息
- WebSocket 按 `target` 实时推送
- SQLite 持久化
- 服务端统一 RSA 密钥对（OAEP-SHA256）
- Vue 3 前端（默认 `user_ui`）

## 目录结构

```
Server_center/
├── app/              # FastAPI 后端
├── frontend/         # Vue 3 前端源码
├── data/             # SQLite（运行时生成）
├── keys/             # RSA 密钥（首次启动自动生成）
├── requirements.txt
└── server-center.service
```

## 快速启动（开发）

### 1. 后端

```bash
cd Server_center
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8765
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev        # 开发：http://localhost:5173（代理到 8765）
npm run build      # 构建到 app/static，由后端直接托管
```

构建后访问 `http://<服务器IP>:8765/` 即可打开 Web UI。

API 文档：`http://<服务器IP>:8765/docs`

## 生产部署（systemd）

```bash
# 假设部署路径 /opt/homeagent/Server_center
sudo useradd -r -s /bin/false homeagent  # 若用户不存在
sudo cp -r Server_center /opt/homeagent/
cd /opt/homeagent/Server_center
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd frontend && npm install && npm run build

sudo cp server-center.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now server-center
sudo systemctl status server-center
```

环境变量（可选，前缀 `SC_`）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `SC_HOST` | `0.0.0.0` | 监听地址 |
| `SC_PORT` | `8765` | 端口 |

---

## 消息格式

### 输入（发送端 → 服务端）

外层 JSON 结构固定，`message` 内层可自由扩展：

```json
{
  "id": "sec_20260615_001",
  "name": "安全检查模块",
  "target": "user_ui",
  "msg_type": "approval_request",
  "message": {
    "text": "执行模块申请运行危险命令：`rm -rf ./tmp`，是否允许？",
    "payload": {
      "command": "rm -rf ./tmp",
      "risk_level": "high"
    }
  },
  "timestamp": 1781528400
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 全局唯一消息 ID |
| `name` | string | 发送方标识，用于回复路由 |
| `target` | string | 接收方标识（如 `user_ui`） |
| `msg_type` | string | 消息类型（如 `approval_request`） |
| `message` | object | 业务内容，`text` + 任意 `payload` |
| `timestamp` | int | Unix 秒级时间戳 |

**HTTP 提交格式**（RSA 加密后，超长自动分块）：

单块：
```json
{ "encrypted": "<base64 ciphertext>" }
```

分块（明文超过约 190 字节时）：
```json
{ "encrypted_chunks": ["<base64>", "<base64>", "..."] }
```

服务端与 Local Agent `shared/server_center` 均支持单块与分块互操作。

### 输出（服务端 → 查询方 / Web UI）

单条消息查询结果：

```json
{
  "id": "sec_20260615_001",
  "name": "安全检查模块",
  "target": "user_ui",
  "msg_type": "approval_request",
  "message": {
    "text": "执行模块申请运行危险命令：`rm -rf ./tmp`，是否允许？",
    "payload": { "command": "rm -rf ./tmp", "risk_level": "high" }
  },
  "timestamp": 1781528400,
  "status": "pending",
  "response": null,
  "created_at": "2026-06-15T12:00:00+00:00",
  "updated_at": "2026-06-15T12:00:00+00:00"
}
```

`status` 取值：`pending` | `approved` | `rejected` | `handled`

列表查询：`GET /api/v1/messages?target=user_ui` → `{ "messages": [...] }`

加密列表查询：`GET /api/v1/messages?target=user_ui&encrypted_for=<client_id>`

### 回复（Consumer → 发送方）

```json
{
  "ref_id": "sec_20260615_001",
  "msg_type": "approval_response",
  "message": {
    "approved": true,
    "reason": "已确认目录为空"
  },
  "timestamp": 1781528400
}
```

- 外部客户端：`POST /api/v1/messages/{id}/respond`，body 为 `{ "encrypted": "..." }`
- 内置 Web UI：`POST /api/v1/messages/{id}/respond/local`，body 为明文 JSON

回复后，原消息 `status` 变为 `approved` 或 `rejected`（`approval_response` 类型），并通过 WebSocket 向 `target` 和 `name` 广播。

---

## RSA 加密对接

算法：**RSA-OAEP**，MGF1-SHA256，主哈希 SHA256。密文 **Base64** 编码。

### 1. 获取服务端公钥

```
GET /api/v1/keys/public
```

响应：

```json
{
  "public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
}
```

### 2. 加密发送消息（Python 示例）

```python
import base64
import json
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

SERVER = "http://your-server:8765"
OAEP = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)

# 获取公钥
pub_pem = requests.get(f"{SERVER}/api/v1/keys/public").json()["public_key"]
pub_key = serialization.load_pem_public_key(pub_pem.encode())

# 构造消息
msg = {
    "id": "sec_20260615_001",
    "name": "安全检查模块",
    "target": "user_ui",
    "msg_type": "approval_request",
    "message": {
        "text": "执行模块申请运行危险命令：`rm -rf ./tmp`，是否允许？",
        "payload": {"command": "rm -rf ./tmp", "risk_level": "high"},
    },
    "timestamp": 1781528400,
}

# 加密并发送
plaintext = json.dumps(msg, ensure_ascii=False).encode("utf-8")
cipher = pub_key.encrypt(plaintext, OAEP)
resp = requests.post(
    f"{SERVER}/api/v1/messages",
    json={"encrypted": base64.b64encode(cipher).decode()},
)
print(resp.json())
```

> RSA 单次加密有长度上限（2048 位密钥约 190 字节明文）。消息较大时请拆分 `payload` 或后续改用 RSA+AES 混合加密。

### 3. 注册客户端公钥（拉取加密回复）

```
POST /api/v1/clients/register
Content-Type: application/json

{
  "client_id": "安全检查模块",
  "public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
}
```

### 4. 加密拉取消息

```
GET /api/v1/messages?name=安全检查模块&status=pending&encrypted_for=安全检查模块
```

响应：

```json
{ "encrypted": "<base64>" }
```

用客户端私钥解密即可得到 `{ "messages": [...] }`。

### 5. 加密发送回复

与发送消息相同：将 `ResponseBody` JSON 序列化 → 服务端公钥加密 → `POST /api/v1/messages/{ref_id}/respond`。

### 6. WebSocket 订阅（明文，供 UI 或内网客户端）

```
ws://your-server:8765/ws/{target}
```

事件：

| event | 说明 |
|-------|------|
| `connected` | 连接成功 |
| `new_message` | 新消息，`data` 为完整消息对象 |
| `message_updated` | 消息状态变更（含回复） |
| `response_ready` | 向 `name` 频道推送，发送方可监听自己的 `name` 获取回复 |

示例：

```json
{
  "event": "new_message",
  "data": { "id": "sec_20260615_001", "status": "pending", ... }
}
```

---

## API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/v1/keys/public` | 服务端公钥 |
| POST | `/api/v1/messages` | 提交加密消息 |
| GET | `/api/v1/messages` | 查询消息列表 |
| GET | `/api/v1/messages/{id}` | 单条消息 |
| POST | `/api/v1/messages/{id}/respond` | 加密回复 |
| GET | `/api/v1/modules` | 已注册模块列表 |
| GET | `/api/v1/modules/{id}` | 单个模块元数据 |
| POST | `/api/v1/messages/local` | 明文发送（Web UI） |
| POST | `/api/v1/messages/{id}/respond/local` | 明文回复（Web UI） |
| POST | `/api/v1/clients/register` | 注册客户端公钥 |
| WS | `/ws/{target}` | 实时推送 |

查询参数（`GET /messages`）：

- `target` — 按接收方过滤
- `name` — 按发送方过滤
- `status` — `pending` / `approved` / `rejected` / `handled`
- `msg_type` — 消息类型
- `limit` — 条数上限（默认 100）
- `encrypted_for` — 指定客户端 ID，返回加密结果

---

## 已注册模块

服务端与前端均已注册以下 9 个模块。各模块推送消息时，`name` 使用下表「发送名」之一，`target` 固定为 `user_ui`。

| 模块 ID | 显示名 | 发送名（name 字段） | 常用 msg_type |
|---------|--------|---------------------|---------------|
| `jarvis` | 主对话 | `jarvis` / `主对话` | `text` |
| `emotion` | 情感与性格状态 | `情感与性格状态模块` / `emotion` | `persona_state` |
| `security` | 安全检查 | `安全检查模块` / `security` | `approval_request` |
| `env` | 环境感知 | `环境感知模块` / `env_sense` | `system_status` |
| `memory` | 长期记忆 | `长期记忆模块` / `memory` | `memory_record` |
| `crawler` | 网页爬取 | `网页爬取模块` / `crawler` | `execution_log` |
| `rag` | RAG | `RAG模块` / `rag` | `rag_result` |
| `executor` | 执行 | `执行模块` / `executor` | `execution_log` |
| `reflection` | 自省与纠错 | `自省与纠错模块` / `reflection` | `reflection_note` |

查询模块元数据：`GET /api/v1/modules`

消息接收后服务端会：
1. 根据 `name` / `target` 解析 `channel`（归属哪个 UI 频道）
2. 按 `msg_type` 设置初始 `status`（`approval_request` → `pending`，其余 → `delivered`）
3. 通过 WebSocket 向 `target`（`user_ui`）推送 `new_message`

---

## 与其他模块集成建议

1. **发送模块**：启动时缓存服务端公钥；发送前加密；`id` 自行保证唯一（建议 `{module}_{date}_{seq}`）。
2. **等待回复**：WebSocket 连接 `/ws/{自己的name}`，监听 `response_ready`；或轮询 `GET /api/v1/messages?id=...`。
3. **Web UI**：`target` 固定为 `user_ui`；审批类消息使用 `msg_type: approval_request`。
4. **后续 mTLS**：在反向代理（Nginx/Caddy）或 uvicorn 层挂载双向 TLS，API 层无需改动。

---

## 开发说明

- 密钥首次启动自动生成于 `keys/`，**勿提交到版本库**。
- 数据库文件：`data/messages.db`。
- **每次启动服务时会自动清空 `messages` 表**（客户端注册 `clients` 表保留）；重启后 Web UI 历史消息为空。
- 前端构建产物输出到 `app/static/`，由 FastAPI 托管 SPA。

---

## 前端 Web UI

### 布局

- **桌面端**：左侧 300px 智能体列表 + 右侧对话工作区（消息流 + 输入框）。
- **移动端**（Tailwind `md:` 断点）：首屏仅列表，点击进入对话，左上角返回。

左侧列表项包含：模块名称、最后消息摘要、⚪闲置 / 🔵工作中、`system_status` 除外未读红点；安全检查模块待审批显示红色圆点。

### 消息类型与 UI 映射

前端根据 `msg_type` 条件渲染，当前已实现：

| msg_type | UI 组件 | 说明 |
|----------|---------|------|
| `text` | `TextBubble.vue` | 聊天气泡；`name=user_ui` 或 `message.role=user` 靠右（靛蓝），否则靠左（深灰） |
| `approval_request` | `ApprovalCard.vue` | 通宽警告卡片，高亮命令代码，批准/拒绝按钮 |
| `execution_log` | `ExecutionLog.vue` | 可折叠手风琴，展开为黑底绿字控制台 |
| `system_status` | `SystemStatus.vue` | 环境指标卡片；`alert=true` 时左侧红灯 |
| `desktop_screenshot` | `DesktopScreenshot.vue` | 远程桌面截图预览 |
| `camera_capture` | `DesktopScreenshot.vue` | 摄像头拍照预览 |
| `persona_state` | `PersonaState.vue` | 情感/性格状态卡片，**不触发**未读 |
| `rag_result` | `RagResult.vue` | RAG 查询、回答与来源列表 |
| `reflection_note` | `ReflectionNote.vue` | 自省：问题 / 分析 / 纠正 |
| `memory_record` | `MemoryRecord.vue` | 记忆键与摘要 |

### 各类型 message 字段约定

**text**
```json
{ "text": "你好", "role": "agent", "mood": "平静" }
```

**approval_request**
```json
{
  "text": "是否允许执行危险命令？",
  "payload": { "command": "rm -rf ./tmp", "risk_level": "high" }
}
```

**execution_log**
```json
{
  "summary": "爬取 example.com 完成",
  "status": "running",
  "log": ["[12:00:01] connecting...", "[12:00:05] done"]
}
```

**system_status**（环境感知模块，字段细化见 Local_agent `modules/env/README.md`）
```json
{
  "report_type": "snapshot",
  "text": "CPU 42% · 内存 68% · 网络正常",
  "alert": false,
  "alert_reason": "",
  "snapshot": {
    "cpu_percent": 42,
    "memory_percent": 68,
    "network": { "upload_mbps": 0.1, "download_mbps": 1.2, "ping": { "latency_ms": 35, "packet_loss_percent": 0 } },
    "disks": [],
    "top_processes": []
  },
  "llm_summary": { "summary": "…", "health_score": 88, "alert": false }
}
```

**desktop_screenshot**（环境感知模块，按需远程截图）
```json
{
  "text": "远程桌面截图",
  "capture_type": "desktop",
  "format": "jpeg",
  "width": 1920,
  "height": 1080,
  "image_base64": "..."
}
```

**camera_capture**（环境感知模块，按需摄像头拍照）
```json
{
  "text": "摄像头拍照",
  "capture_type": "camera",
  "camera_index": 0,
  "format": "jpeg",
  "width": 1280,
  "height": 720,
  "image_base64": "..."
}
```

**persona_state**
```json
{
  "mood": "愉悦",
  "personality": "温和",
  "text": "当前对话氛围积极",
  "traits": ["耐心", "幽默"]
}
```

**rag_result**
```json
{
  "query": "HomeAgent 架构是什么？",
  "answer": "HomeAgent 由多个模块组成…",
  "sources": [
    {
      "title": "README",
      "url": "...",
      "score": 0.87,
      "snippet": "召回的原文片段…",
      "doc_id": "doc_abc",
      "chunk_id": "doc_abc__xyz",
      "chunk_index": 0
    }
  ]
}
```

**reflection_note**
```json
{
  "issue": "执行了错误的路径",
  "analysis": "未校验 cwd 导致",
  "correction": "执行前先 pwd 确认"
}
```

**memory_record**
```json
{
  "key": "user_pref_theme",
  "summary": "用户偏好深色主题"
}
```

### 新增 msg_type 的步骤

1. 在 `frontend/src/components/messages/` 新建 Vue 组件（如 `MyNewType.vue`）。
2. 在 `frontend/src/components/MessageItem.vue` 的 `renderers` 对象中注册：
   ```js
   const renderers = {
     text: TextBubble,
     approval_request: ApprovalCard,
     execution_log: ExecutionLog,
     system_status: SystemStatus,
     my_new_type: MyNewType,  // 新增
   }
   ```
3. 若需自定义未读规则，修改 `frontend/src/utils/messages.js` 中的 `countsAsUnread()`。
4. 若需新智能体频道，在 `app/modules.py` 与 `frontend/src/config/agents.js` 同步追加模块定义。
5. 在 `messageSummary()` 中补充摘要逻辑，便于左侧列表预览。

### 智能体路由规则

消息归属左侧哪个模块，由 `belongsToAgent()` 判定：

- 模块发出：`name` 匹配 `agents.names` 或 `agents.id`
- 用户发出：`name === "user_ui"` 且 `target` 指向对应模块

用户从 Web UI 发送时，调用 `POST /api/v1/messages/local`，`target` 为模块 `names[0]`。
