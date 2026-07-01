# Local Agent 测试程序

各模块的简易图形界面测试（Python 内置 `tkinter`，无额外 UI 库）。

## 运行前

```bash
cd Local_agent
# 激活 venv 并安装依赖（若尚未安装）
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

## 测试程序

| 脚本 | 说明 | 依赖 |
|------|------|------|
| `test_llm_gui.py` | 测试 `shared/llm` OpenAI 兼容调用 | Ollama 运行中 |
| `test_crawler_gui.py` | 测试爬取（可切换是否使用模型） | 无模型模式仅需网络 |
| `test_env_gui.py` | 测试环境感知（含 Server 地址、测试连接、推送） | 推送需 Server Center 运行 |
| `test_rag_gui.py` | RAG 入库（规则/语义分块）、问答、向量库浏览与删除 | 语义分块需 `qwen2.5:3b` |
| `test_security_gui.py` | 安全检查：绿/红/黄命令、Server Center 审批 | Server Center + 黄色需 Ollama |
| `test_storage_gui.py` | **日志与记录清理**：查看/删除各模块 DB、日志、向量库、截图等 | 无（建议停止 Agent 后再清理） |

### 启动

```bash
# 在 Local_agent 目录下
python test/test_llm_gui.py
python test/test_crawler_gui.py
python test/test_env_gui.py
python test/test_rag_gui.py
python test/test_security_gui.py
python test/test_storage_gui.py
```

Windows 也可双击：

- `test/run_llm.bat`
- `test/run_crawler.bat`
- `test/run_env.bat`
- `test/run_rag.bat`
- `test/run_security_gui.bat`
- `test/run_storage_gui.bat`

## 爬取：使用模型 vs 不使用模型

| 阶段 | 不使用模型 | 使用模型 |
|------|-----------|----------|
| 引擎选择 | 自适应路由（feedparser / httpx+BS4 / Playwright） | 相同 |
| 成功判定 | 引擎返回 `success`（有正文/条目即成功） | **LLM** 根据任务描述判断 |
| 失败重试 | 换下一个引擎 | **LLM** 调参后重试（最多 3 轮） |
| 过滤 | 4 种预设过滤器 | 相同 |
| 结果选取 | **最高分**过滤器 | **LLM** 择优；不行则 LLM 自行提炼 |

建议测试顺序：

1. 先跑 **不使用模型** + `https://example.com`（无需 Ollama）
2. 再勾选 **使用模型** 对比结果与日志
3. 用 LLM 测试窗口确认 Ollama 连通后再测模型爬取

## RAG：四种分块策略

| split_mode | 名称 | 速度 | 依赖 |
|------------|------|------|------|
| `rule` | ① 规则贪婪合并 | 毫秒 | 无 |
| `semantic` | ② 3B 语义裁判 | 慢 | `qwen2.5:3b` |
| `semantic_embedding` | ③ 向量断点 | 中 | `nomic-embed-text` |
| `structural` | ④ 文档结构（推荐 .md） | 毫秒 | 无 |

测试窗口「入库与问答」→ 下拉选择分块 → 入库后在「向量库」查看块数、`split_mode`、`Header_*`。

建议对比：同一篇 Markdown 分别用 ① 与 ④ 入库，观察块边界与 metadata 差异。

## 常见失败原因

| 日志关键词 | 原因 | 处理 |
|-----------|------|------|
| `CERTIFICATE_VERIFY_FAILED` / `certificate has expired` | 目标站 HTTPS 证书过期或无效 | 勾选「忽略 SSL 证书错误」，或等无模型模式自动 SSL 重试 |
| `Executable doesn't exist` / `playwright install` | Playwright 浏览器未下载 | `playwright install chromium` |
| 仅 Playwright 失败、httpx 已成功 | 静态页不需要 Playwright | 正常，前两个引擎成功即可 |
