# 安全检查模块

命令风险判定：规则（四列表）+ 黄色模型升红 + 红色用户审批。

## 四列表文件位置

编辑以下文件后，可调用 `POST /security/reload-lists` 或重启服务生效；也可在 Web UI「安全检查」→ **规则配置** 中增删改（保存后立即生效）。

| 列表 | 文件路径 |
|------|----------|
| 白命令 | `modules/security/lists/white_commands.txt` |
| 黑命令 | `modules/security/lists/black_commands.txt` |
| 白目录 | `modules/security/lists/white_directories.txt` |
| 黑目录 | `modules/security/lists/black_directories.txt` |

格式：每行一条，`#` 开头为注释（文件顶部说明行会保留）。

## 本地 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/security/status` | 列表、待审批、近期记录 |
| GET | `/security/lists` | 读取四列表 |
| PUT | `/security/lists/{list_key}` | 覆盖保存某一列表 |
| POST | `/security/check` | 提交检查（阻塞至审批结束） |
| GET | `/security/records/yellow` | 黄色记录 |
| GET | `/security/records/approvals` | 审批记录 |
| POST | `/security/chat` | 对话 |
| POST | `/security/reload-lists` | 重新加载四列表 |

### Web UI 规则配置（经 Server Center）

`target=安全检查模块`，`message.payload.action`：

| action | 说明 |
|--------|------|
| `security_lists_get` | 拉取四列表 |
| `security_lists_set` | `list_key` + `items[]` 覆盖保存 |

响应 `msg_type`: `security_lists_result`

## Server Center

- 模块名：`安全检查模块` / `security`
- 消息类型：`approval_request`（红色审批）、`security_yellow_log`（黄色记录）、`security_lists_result`（规则配置）、`text`（对话回复）

执行模块对接见 [INTEGRATION.md](INTEGRATION.md)。

## 配置（`.env` 前缀 `LA_SECURITY_`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `LA_SECURITY_APPROVAL_TIMEOUT_SECONDS` | `300` | 审批超时（秒） |
| `LA_SECURITY_USE_MODEL_FOR_YELLOW` | `true` | 黄色是否调用模型升红 |

## LLM 槽位

| slot | 用途 |
|------|------|
| `security.judge` | 黄色升红判定 |
| `security.chat` | 用户对话 |
| `security.auto_approve` | 模型自动审批（默认 `llama3.2`） |

## 测试

```bash
python test/test_security_gui.py
```

需先启动 Server Center；红色命令请在 Web UI「安全检查模块」中审批。

**模型自动审批**：Web UI 左侧「待审批」标题栏勾选「模型自动审批」；须同时运行 Local Agent（`uvicorn` 或 `test_security_gui.py` 已连接），否则请求无人处理。默认模型槽位 `security.auto_approve` → `llama3.2`（新 seed 生效；已有 `llm.db` 请在「模型配置」中手动改绑）。
