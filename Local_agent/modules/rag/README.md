# RAG 模块

手动文档入库、Chroma 向量检索、`nomic-embed-text` 嵌入；问答时可选择由本地小模型总结或直接返回召回片段。主对话可 `rag_query` / `rag_chat`，**不**往知识库写入。

## 配置（`.env` 前缀 `LA_RAG_`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `DEFAULT_COLLECTION` | `default` | 默认知识库 |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama 嵌入模型 |
| `CHUNK_SIZE` | `800` | 分块上限（字符） |
| `CHUNK_OVERLAP` | `120` | 硬切/递归切重叠 |
| `SPLIT_MODE` | `rule` | 见下表四种模式 |
| `SPLIT_MODEL` | `qwen2.5:3b` | 策略② 3B 裁判模型 |
| `MIN_CHUNK_SIZE` | `50` | 策略③ 小块合并下限 |
| `EMBED_BREAKPOINT_THRESHOLD` | `0.35` | 策略③ 相邻句向量余弦距离阈值 |
| `EMBED_BREAKPOINT_PERCENTILE` | `75` | 策略③ 距离百分位兜底（取 max(阈值, P75)） |
| `TOP_K` / `MIN_SCORE` / `SUMMARIZE` | `5` / `0.25` / `true` | 检索与问答 |

## 四种分块策略

入库时 `split_mode` 取值：`rule` | `semantic` | `semantic_embedding` | `structural`  
（`use_model_split=true` 等价于 `semantic`，`false` 等价于 `rule`）

| 维度 | ① `rule` | ② `semantic` | ③ `semantic_embedding` | ④ `structural` ⭐ |
|------|----------|----------------|------------------------|-------------------|
| **原理** | 段落/标题贪婪合并至 ~800 字 | 3B 模型 YES/NO 判主题切换 | 句子 Embedding 余弦距离找断点 | Markdown 标题树 + 标题路径 metadata |
| **依据** | 换行、字数 | 模型推理 | 向量数学距离 | `#` ~ `######` 结构 |
| **速度** | 毫秒级 | 秒~分钟 | 秒级（批量 embed 句子） | 毫秒级 |
| **硬件** | 无 | 3B 显存 | 嵌入模型（与入库共用 nomic） | 无 |
| **metadata** | 基础 | 基础 | 基础 | `Header_1`…、`source_ref` |
| **推荐场景** | 快速入库 | 长文语义原子 | 无 LLM 的语义切分 | `.md` / 教程文档 |

### 实现文件

| 策略 | 文件 |
|------|------|
| 调度 | `ingest/splitter.py` → `split_document()` |
| ① | `ingest/splitter_rule.py` |
| ② | `ingest/splitter_semantic.py` + `model/split_judge.py` |
| ③ | `ingest/splitter_semantic_embedding.py` |
| ④ | `ingest/splitter_structural.py` + `ingest/structure.py` + `ingest/recursive_split.py` |
| 共用 | `ingest/units.py`（句/段/标题）、`ingest/chunker.py`（硬切） |

**策略③说明：** 分块阶段对**句子**做 Embedding 找断点；入库时 Chroma 仍会对**最终 chunk 全文**再 Embed 一次。句子向量仅用于切分，不与 Chroma 向量复用（避免架构耦合）。

**策略④说明：** 章节超长时按 `\n\n` → `\n` → 空格递归细分；正文前注入 `[Header_1 > Header_2]` 面包屑，metadata 写入 `Header_1`、`Header_2`…

## LLM 槽位

| slot | 用途 |
|------|------|
| `rag.summarize` | 检索后阅读片段并生成回答 |
| `rag.split` | 语义分块裁判 |
| `rag.embed` | 入库 embedding |

## 本地 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/rag/status` | 知识库状态与分块配置 |
| POST | `/rag/ingest/file` | 导入文件（支持 `split_mode`） |
| POST | `/rag/ingest/text` | 导入文本 |
| POST | `/rag/query` | 检索问答 |
| POST | `/rag/chat` | 带会话的 RAG 对话 |
| GET | `/rag/documents` | 文档列表 |
| POST | `/rag/delete/chunks` | 删除指定块 |
| POST | `/rag/delete/document` | 删除文档 |
| POST | `/rag/delete/collection` | 清空集合 |

### 入库示例

```bash
# ④ 结构分块（Markdown 推荐）
curl -X POST http://127.0.0.1:8770/rag/ingest/file \
  -H "Content-Type: application/json" \
  -d '{"path":"README.md","split_mode":"structural"}'

# ③ 向量断点
curl -X POST http://127.0.0.1:8770/rag/ingest/text \
  -H "Content-Type: application/json" \
  -d '{"text":"……","split_mode":"semantic_embedding"}'

# ① 规则（默认）
curl -X POST http://127.0.0.1:8770/rag/ingest/text \
  -d '{"text":"……","split_mode":"rule"}'
```

响应与 chunk metadata 均含 `split_mode`；结构分块另有 `Header_1`、`Header_2` 等。

## 测试

```bash
python test/test_rag_gui.py
```

测试窗口下拉框可选四种分块；「向量库」页可查看 `split_mode` 与标题路径。

| 分块 | 额外依赖 |
|------|----------|
| ① rule | — |
| ② semantic | `ollama pull qwen2.5:3b` |
| ③ semantic_embedding | `nomic-embed-text` |
| ④ structural | 无（Markdown 效果更佳） |

## 数据目录

- `data/rag/chroma/` — 向量
- `data/rag/rag.db` — 元数据
