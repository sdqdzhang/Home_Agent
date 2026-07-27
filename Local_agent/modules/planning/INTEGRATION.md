# 规划模块对接说明（主对话 / 编排层 / Web UI）

规划模块提供**原子 API**（`local_bus`）与 **UI 消息入口**（Server Center）。  
多轮会话状态由**调用方**持有（前端工作台或主对话）。

参考：

- Web UI：`Server_center/frontend/src/components/PlanningWorkspace.vue`
- GUI 沙箱：`plan_test/test/test_planner_gui.py`

---

## 1. 其它模块调用（进程内）

```python
from shared.local_bus import call
from modules.planning.schemas import PlanRequest, ClarifyRequest

outcome = await call("planning", "clarify", ClarifyRequest(goal="…"))
plan = await call("planning", "plan", PlanRequest(goal="…", clarifications=[…]))
```

可用方法：`clarify` / `run_env_query` / `plan` / `run_graph`。  
依赖 `executor`、`processor` 已在 `local_bus` 注册。

---

## 2. Web UI 消息协议（stateless）

前端 → Local（`msg_type=planning_request`，`target=规划模块`）：

| `payload.action` | 主要字段 | 回推 `msg_type` |
|------------------|----------|----------------|
| `clarify` | `goal`, `history`, `env_records`, `round_index`, `request_id` | `clarify_result` |
| `env_probe` | `queries[{id,instruction,purpose,block_id}]`, `round_index`, `request_id` | `env_probe_result` |
| `plan` | `goal`, `clarifications`, `context_blocks`, `request_id` | `plan_result` |
| `run_graph` | `goal`, `graph`, `initial_blocks`, `request_id` | `plan_progress`* + `graph_run_result` |

\*执行中按节点推送进度。

所有回推均带同一 `request_id`，便于前端匹配。

### `plan_result` 载荷（TaskGraph）

```json
{
  "ok": true,
  "request_id": "…",
  "goal": "有效目标",
  "summary": "…",
  "status": "draft",
  "graph": { "summary": "…", "nodes": [/* ActionNode|ProcessNode */] },
  "error": "",
  "raw": null
}
```

旧 `steps[]` 已废弃；UI 卡片仍可兼容显示。

---

## 3. 推荐闭环

```
goal
  ↓
[循环] clarify → 展示 questions / 批准 env_queries
         ↓
       env_probe（仅批准项）→ 累积 env_records / env_blocks
         ↓
       round_index++ → clarify
  ↓ ready 或达 MAX_COLLECT_ROUNDS
plan → 展示 TaskGraph
  ↓
run_graph(compose_goal(goal, history), graph, initial_blocks=env_blocks)
```

常量：`MAX_COLLECT_ROUNDS = 8`（`modules.planning`）。

---

## 4. 类型索引（`modules.planning.schemas`）

| 类型 | 用途 |
|------|------|
| `ClarifyRequest` / `ClarifyOutcome` | 信息收集一轮 |
| `ClarifyQuestion` / `ClarifyAnswer` | 单题与回答 |
| `EnvQuery` / `EnvProbeRecord` | 探测请求与结果 |
| `PlanRequest` / `PlanOutcome` | 出图 |
| `TaskGraph` / `ActionNode` / `ProcessNode` | 静态图 IR |
| `GraphRunResult` / `NodeRunStatus` | 执行结果 |
| `compose_goal` | 合成有效目标 |
