# RAG 模块

手动文档入库、Chroma 向量检索、`nomic-embed-text` 嵌入；问答时可选择由本地小模型总结或直接返回召回片段。

## 配置（`.env` 前缀 `LA_RAG_`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `DEFAULT_COLLECTION` | `default` | 默认知识库 |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama 嵌入模型 |
| `EMBED_BASE_URL` | `http://127.0.0.1:11434/v1` | 嵌入 API |
| `CHUNK_SIZE` | `800` | 分块大小（字符） |
| `CHUNK_OVERLAP` | `120` | 分块重叠 |
| `TOP_K` | `5` | 默认召回数 K |
| `MIN_SCORE` | `0.25` | 最低相似度（cosine） |
| `SUMMARIZE` | `true` | `true`=模型总结；`false`=直接返回片段 |

## 本地 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/rag/status` | 知识库统计与当前配置 |
| POST | `/rag/ingest/file` | 手动导入文件 |
| POST | `/rag/ingest/text` | 手动导入纯文本 |
| POST | `/rag/query` | 单次检索问答 |
| POST | `/rag/chat` | 带会话记忆的问答 |

### 问答请求示例

```bash
curl -X POST http://127.0.0.1:8770/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query":"文档主题是什么？","top_k":5,"min_score":0.25,"summarize":true}'
```

`top_k`、`min_score`、`summarize` 均可省略，使用 `.env` 默认值；请求级参数覆盖默认。

## Server Center 消息

- 模块名：`RAG模块` / `rag`
- 用户提问：`msg_type=text`，`target=RAG模块`
- 模块回复：`msg_type=rag_result`
- 入库进度：`msg_type=execution_log`

### `rag_result`

```json
{
  "query": "…",
  "answer": "…",
  "sources": [
    { "title": "README.md", "url": "…", "score": 0.87, "snippet": "…", "doc_id": "doc_abc", "chunk_id": "…", "chunk_index": 0 }
  ],
  "collection_id": "default",
  "session_id": "default",
  "mode": "summarized",
  "retrieval_meta": {
    "collection_id": "default",
    "top_k": 5,
    "min_score": 0.25,
    "chunks_retrieved": 3,
    "chunks_used": 3,
    "summarize": true,
    "latency_ms": 420
  }
}
```

`mode`：`summarized`（模型总结）或 `direct`（直接返回片段）。

## 数据目录

- `data/rag/chroma/` — Chroma 持久化
- `data/rag/rag.db` — 文档元数据与会话
- `data/rag/documents/` — 预留

## 测试

```bash
python test/test_rag_gui.py
```

需 Ollama 已拉取 `nomic-embed-text`；勾选「模型总结」时还需对话模型（如 `llama3.2`）。
