# 记忆模块（memory）

观察打分、工作记忆压缩、向量归档、三维加权检索、反思升华。由会话管理写入记忆候选；**不对 main Function Calling 开放**。

- **模块 ID**：`memory`
- **发送名**：`记忆模块`
- **消息类型**：`memory_record`

## 分层

| 层 | 存储 | 说明 |
|----|------|------|
| 工作记忆 | SQLite | 近期观察；满员后压缩，保留高重要性 |
| 归档 | Chroma | 向量检索；内容 + tags |
| 核心记忆 | SQLite | 手动键值（偏好、长期事实） |

`conversation_manager` Analyzer 产出 Memory Candidates 后调用 `observe`；低于 `observe_min_importance` 的观察会被拒绝。

## 检索

`recall` 三维加权：近时性 + 重要性 + 相关性（向量分数与标签匹配混合，权重见 `LA_MEMORY_RELEVANCE_*`）。

## 本地 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/memory/status` | 工作记忆 / 核心记忆 / 归档统计 |
| POST | `/memory/observe` | 观察事件并打分入库 |
| POST | `/memory/ingest-dialogue` | 对话总结后归档 |
| POST | `/memory/recall` | 向量 + 标签加权检索 |
| GET | `/memory/context` | 当前工作记忆上下文 |
| POST | `/memory/reflect` | 从工作记忆提炼洞察 |
| GET | `/memory/core` | 核心记忆列表 |
| POST | `/memory/core` | 写入核心记忆 |
| DELETE | `/memory/core/{key}` | 删除核心记忆 |

```python
from shared.local_bus import call
from modules.memory.schemas import ObserveRequest, RecallRequest

await call("memory", "observe", ObserveRequest(content="用户偏好深色主题"))
hits = await call("memory", "recall", RecallRequest(query="主题偏好"))
```

## LLM 槽位

| slot | 用途 |
|------|------|
| `memory.assess` | 观察 1–10 重要性 |
| `memory.tag` | 主题标签 |
| `memory.summarize` | 对话总结入库 |
| `memory.reflect` | 从工作记忆提炼洞察 |
| `memory.embed` | 归档 embedding |

## 配置（`LA_MEMORY_`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `WORKING_MAX_SIZE` | `20` | 工作记忆上限 |
| `WORKING_KEEP_AFTER_CONSOLIDATE` | `10` | 压缩后保留条数 |
| `RECALL_TOP_K` | `5` | 召回条数 |
| `OBSERVE_MIN_IMPORTANCE` | `6` | 低于此分的观察不入库 |
| `RELEVANCE_VECTOR_WEIGHT` | `0.65` | 向量相关性权重 |
| `RELEVANCE_TAG_WEIGHT` | `0.35` | 标签匹配权重 |

## 数据

- `data/memory/` — 工作记忆 / 核心记忆 DB
- `data/memory/chroma/` — 归档向量库

## 测试

```bash
python test/test_memory_gui.py
```
