SYSTEM_PROMPT = """你是 HomeAgent 网页爬取模块的本地助手。
职责：
1. 判断爬取结果是否满足用户需求
2. 在失败时建议调整爬取参数（timeout、user_agent、wait_selector、playwright 配置等）
3. 从多种过滤结果中选出最合适的一项
4. 必要时对原始内容进行智能提炼

回复时请使用严格 JSON（当任务要求 json_mode 时）：
- 仅输出一个 JSON 对象，不要 Markdown 代码块
- 不要注释、不要尾随逗号、suggestions 的值只能是字符串/数字/布尔/null"""

JUDGE_CRAWL_PROMPT = """判断以下爬取是否成功满足任务。

任务描述: {task}
目标 URL: {url}
使用策略: {strategy}
标题: {title}
错误信息: {error}
内容预览:
{preview}

若页面已有标题或正文且与任务相关，success 应为 true。
返回 JSON:
{{
  "success": true,
  "reason": "简短理由",
  "suggestions": {{}}
}}"""

TUNE_CONFIG_PROMPT = """爬取未成功。请根据当前配置与错误，输出调整后的完整 config JSON（仅 JSON，无其他文字）。

URL: {url}
策略: {strategy}
当前配置: {config}
错误: {error}
模型建议: {suggestions}

可调整字段: timeout, user_agent, headers, wait_until, wait_selector, playwright_timeout_ms, playwright_headless, max_entries"""

PICK_FILTER_PROMPT = """从以下过滤结果中选出最满足任务的一项。

任务: {task}
URL: {url}

候选列表（JSON）:
{candidates}

返回 JSON:
{{
  "best_name": "过滤器名称",
  "success": true/false,
  "reason": "理由"
}}"""

CUSTOM_FILTER_PROMPT = """预设过滤器均未满足需求。请直接处理原始内容并输出最终结果。

任务: {task}
URL: {url}
标题: {title}
原始内容:
{content}

返回 JSON:
{{
  "success": true/false,
  "result": "提炼后的正文或结构化结果",
  "reason": "理由"
}}"""

CHAT_WITH_CONTEXT_PROMPT = """你是网页爬取模块助手。用户可能询问爬取任务、日志或产物文件。
已知上下文:
{context}

请基于上下文准确回答。若缺少信息请说明。"""
