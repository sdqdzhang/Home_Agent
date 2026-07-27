from __future__ import annotations

PROCESS_SYSTEM = """你是个人 AI Agent 的「处理」模块。
你的任务：根据用户给出的总要求，阅读若干上下文数据块，产出**一个**结果数据块。

规则：
1. 只输出一个 JSON 对象，不要输出其它文字。
2. JSON 字段：
   - type: 字符串，结果内容类型（如 code、file、text、summary 等；中英文均可）
   - content: 字符串，结果正文（主要内容都放这里）
   - producer: 字符串，填 "processor"
   - metadata: 对象，任意标签信息（没有就给 {}）
3. 不要生成或编造 id 字段。
4. 严格按「总要求」完成任务；上下文数据块仅作参考材料。
"""


def render_user(requirement: str, blocks_for_llm: list[dict]) -> str:
    import json

    blocks_json = json.dumps(blocks_for_llm, ensure_ascii=False, indent=2)
    return (
        f"## 总要求\n{requirement.strip()}\n\n"
        f"## 上下文数据块（已去掉 id）\n{blocks_json}\n\n"
        "请输出一个结果数据块 JSON。"
    )
