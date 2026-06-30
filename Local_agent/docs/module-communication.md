# 模块通信约定

> 现有各模块实现**不必改动**；规划、执行等新模块请遵循本文。

## Local 内：两条路径

| 场景 | 用法 | 底层 |
|------|------|------|
| 同步、本机、要快（如执行前安检） | `shared.local_bus.call()` / `security_check()` | 进程内直调 Service |
| 要 UI 看到、审批、留痕 | `shared.local_bus.push_to_ui()` | `ServerCenterClient.send_message`（RSA） |

```python
from shared.local_bus import call, push_to_ui, security_check

result = await security_check("ls", caller_module="executor")
await push_to_ui("rag", msg_type="text", message={"text": "...", "role": "agent"})
```

**禁止**用 `:8770` HTTP 做模块互调；HTTP 路由仅本地调试（curl / GUI）。

## Local ↔ Server

| 方向 | 方式 | 加密 |
|------|------|------|
| Local → Server 发消息/回复 | `POST /api/v1/messages` | RSA-OAEP body |
| Server → Local 拉取 | `GET /messages?encrypted_for=…` | RSA 加密响应 |
| Server → Local 实时推送 | WebSocket `/ws/{channel}` | 载荷明文；**生产请用 HTTPS/WSS** |
| Web UI → Server | `/messages/local` | 明文（同域 + HTTPS） |

### 远程部署（不改代码）

1. Server 前加 Nginx/Caddy，启用 **HTTPS/WSS**
2. Local `.env`：`LA_SERVER_CENTER_URL=https://你的域名`
3. Local 只监听本机：`LA_HOST=127.0.0.1`（默认）

`ws_listener` 会根据 `https://` 自动使用 `wss://`。

## 相关文件

- `shared/local_bus.py` — 新模块统一入口
- `shared/server_center/client.py` — RSA 消息客户端
- `modules/security/INTEGRATION.md` — 安全检查对接
