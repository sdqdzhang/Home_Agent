# 安全检查模块 — 执行模块对接说明

## 职责

- **输入**：`command`（必填）+ `purpose`（可选）
- **输出**：`allowed: bool`（是否同意执行）

执行模块在真正执行命令前必须调用本模块；`allowed=false` 时不得执行。

## 进程内调用（推荐）

```python
from modules.security.schemas import CheckRequest
from app.main import security_service  # 或依赖注入

result = await security_service.check(
    CheckRequest(
        command="rm -rf ./tmp",
        purpose="清理临时文件",
        caller_module="executor",
        caller_request_id="job_001",
    )
)

if not result.allowed:
  # 中止执行，记录日志
  ...

# result.allowed == True 时方可执行
```

## HTTP 调试（Local Agent 已启动时）

```bash
curl -X POST http://127.0.0.1:8770/security/check \
  -H "Content-Type: application/json" \
  -d '{"command": "ls", "purpose": "查看目录", "caller_module": "executor"}'
```

## 返回值字段

| 字段 | 说明 |
|------|------|
| `allowed` | 是否允许执行 |
| `risk_level` | `green` / `yellow` / `red` |
| `check_id` | 本次检查 ID |
| `reason` | 判定原因 |
| `approval_id` | 红色审批消息 ID（若有） |
| `risk_source` | `rule` / `model` / `user` / `timeout` |

## 阻塞语义

- **绿色**：立即返回 `allowed=true`
- **黄色**：记录后由模型判断是否升红；不升红则 `allowed=true`
- **红色**：推送 `approval_request` 到 Server Center，**阻塞**直到用户批准/拒绝或超时（默认 5 分钟，`LA_SECURITY_APPROVAL_TIMEOUT_SECONDS`）

未连接 Server Center 时，红色请求返回 `allowed=false`。

## 风险规则（摘要）

1. 涉及**黑目录** → 红
2. **白命令**且不涉及黑目录 → 绿
3. **黑命令**且仅在白目录内 → 黄（模型可升红）
4. **黑命令**且不限于白目录 → 红
5. 其余 → 黄（模型可升红）

四列表文件位置见 `modules/security/README.md`。

## 时序（红色）

```
执行模块          SecurityService          Server Center / Web UI
    |                    |                         |
    |-- check(cmd) ----->|                         |
    |                    |-- approval_request ---->|
    |                    |                         |-- 用户审批
    |                    |<-- response_ready ------|
    |<-- CheckResult ----|                         |
```

## 注意事项

- 不支持会话级「记住允许」
- 仅黄色路径使用本地模型；红/绿不走模型
- 审计日志持久化在 `data/security/security.db`（不受 Server Center 重启影响）
