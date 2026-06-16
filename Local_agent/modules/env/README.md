# 环境感知模块

高频采集（20s）、统计压缩（10min）、低频 LLM 汇报、按需截图。作为主 Agent 附属模块，与 Server Center 通信参数由 `app/main.py` 统一配置。

## 采集指标（每 20 秒）

| 类别 | 字段 |
|------|------|
| 系统资源 | `cpu_percent`、`memory_percent`、`memory_used_gb`、`memory_total_gb`、`disks[]` |
| 网络 | `upload_mbps`、`download_mbps`、`ping`（延迟/丢包）、`proxy_enabled`、`vpn_active` |
| 进程 | `top_processes[]`（前 5：pid、name、cpu%、mem%） |

## 10 分钟压缩（`aggregated`）

- 数值型（CPU/内存/网速/Ping）：`avg` / `max` / `min`
- 代理/VPN：无变化只记当前状态；有变化记录 `changes[]` 事件
- Top 进程：窗口内出现频次 + 平均 CPU/内存，重排后保留前 5

## Server Center 消息格式

### `system_status`

```json
{
  "report_type": "snapshot | summary | alert | alert_cleared",
  "text": "人类可读摘要（列表预览用）",
  "alert": false,
  "alert_reason": "",
  "snapshot": {
    "cpu_percent": 42.1,
    "memory_percent": 68.5,
    "memory_used_gb": 10.9,
    "memory_total_gb": 16.0,
    "disks": [
      { "device": "C:\\", "mountpoint": "C:\\", "total_gb": 256, "used_gb": 180, "free_gb": 76, "percent": 70.3 }
    ],
    "network": {
      "upload_mbps": 0.12,
      "download_mbps": 1.45,
      "ping": { "target": "8.8.8.8", "latency_ms": 35, "packet_loss_percent": 0 },
      "proxy_enabled": false,
      "vpn_active": false
    },
    "top_processes": [
      { "pid": 1234, "name": "chrome.exe", "cpu_percent": 12.5, "memory_percent": 8.2 }
    ],
    "timestamp_iso": "2026-06-16T08:00:00+00:00"
  },
  "aggregated": { },
  "llm_summary": {
    "summary": "过去 10 分钟系统运行平稳…",
    "alert": false,
    "alert_reason": "",
    "health_score": 88,
    "source": "llm",
    "generated_at": "2026-06-16T08:10:00+00:00"
  }
}
```

- `report_type=summary` 时附带完整 `aggregated` 与 `llm_summary`
- `alert=true` 触发 Web UI 环境模块左侧红灯；后续 `alert=false` 消息熄灭

### `desktop_screenshot`

```json
{
  "text": "远程桌面截图",
  "format": "jpeg",
  "width": 1920,
  "height": 1080,
  "size_bytes": 245000,
  "image_base64": "..."
}
```

因 Base64 体积较大，使用 RSA 分块加密（`encrypted_chunks`）经 `POST /api/v1/messages` 发送；服务端已支持解密合并。

截图同时保存到本地 `data/env/screenshots/shot_*.jpg`。

截图保存：`data/env/screenshots/`；摄像头照片：`data/env/camera/`。

### 触发截图 / 拍照（用户 → 模块）

```json
{ "payload": { "action": "screenshot" } }
{ "payload": { "action": "camera" } }
```

## 本地 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/env/status` | 主 Agent 读取最新总状态 |
| POST | `/env/collect` | 手动采集 |
| POST | `/env/summary` | 手动压缩总结 |
| POST | `/env/screenshot` | 截图 |

## 告警阈值（`.env`）

| 变量 | 默认 |
|------|------|
| `LA_ENV_CPU_ALERT_PERCENT` | 90 |
| `LA_ENV_MEMORY_ALERT_PERCENT` | 90 |
| `LA_ENV_DISK_FREE_ALERT_GB` | 5 |
| `LA_ENV_PING_LOSS_ALERT_PERCENT` | 10 |
| `LA_ENV_PING_LATENCY_ALERT_MS` | 500 |

LLM 总结另可基于压缩数据独立判定 `alert`（每次新对话，不携带历史）。
