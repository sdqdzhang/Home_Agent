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

### 启动

```bash
# 在 Local_agent 目录下
python test/test_llm_gui.py
python test/test_crawler_gui.py
python test/test_env_gui.py
```

Windows 也可双击：

- `test/run_llm.bat`
- `test/run_crawler.bat`
- `test/run_env.bat`

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

## 常见失败原因

| 日志关键词 | 原因 | 处理 |
|-----------|------|------|
| `CERTIFICATE_VERIFY_FAILED` / `certificate has expired` | 目标站 HTTPS 证书过期或无效 | 勾选「忽略 SSL 证书错误」，或等无模型模式自动 SSL 重试 |
| `Executable doesn't exist` / `playwright install` | Playwright 浏览器未下载 | `playwright install chromium` |
| 仅 Playwright 失败、httpx 已成功 | 静态页不需要 Playwright | 正常，前两个引擎成功即可 |
