from __future__ import annotations

import logging
from typing import Any, cast

from shared.llm import get_llm_client
from modules.executor.capabilities import EXECUTOR_MODES
from modules.executor.content_extract import extract_fenced_blocks, strip_fenced_blocks
from modules.executor.llm_slots import EXECUTOR_ROUTE_SLOT
from modules.executor.schemas import ExecutorMode

logger = logging.getLogger(__name__)

_MODE_SET = frozenset(EXECUTOR_MODES)

_MODE_GUIDE = """
| mode | 何时选择（仅当意图非常明确时才选专用能力） |
|------|----------|
| read_file | 明确要「读取/打开某个文件的内容」并返回正文 |
| write_file | 明确要「创建/覆盖写入某个文件」（含把附件正文写到路径） |
| delete_file | 明确要「删除某个文件」 |
| browse_dir | 明确只要「看目录树结构」，且不要求跑 shell |
| search_file | 明确要「按文件名/通配符找文件路径」 |
| search_content | 明确要「在某个文件里搜一段文字」 |
| codegen | 明确只要「根据规格生成代码文本」，且不执行、不写盘 |
| command | **默认兜底**：凡不属于上面专用能力的，一律选 command（PowerShell/Shell 可查进程、系统信息、列目录、跑脚本、git 等） |
""".strip()

ROUTE_SYSTEM = f"""你是 HomeAgent 执行模块的「子能力路由」助手。
唯一任务：根据用户自然语言，判断应使用哪一个执行子能力（mode）。

## 核心原则（必须遵守）
1. **专用能力优先匹配，但不勉强**：只有用户意图清晰落在 read_file / write_file / delete_file / browse_dir / search_file / search_content / codegen 时才选它们。
2. **其余全部走 command**：command 是兜底。PowerShell/Shell 能力最全；查进程、服务、端口、环境变量、压缩、安装、跑程序、git、「查看/列出某某」但不是读文件正文/目录树专用意图等，都选 command。
3. **拿不准时选 command**，不要选错专用能力，也不要轻易 ok=false。
4. 只有真正无法当作单一可执行动作时才 ok=false（例如一次要求多个无关动作、关键路径完全缺失且无法默认）。

## 可选 mode
{_MODE_GUIDE}

## 其他规则
- 只能选择上表中的某一个 mode；不可发明其它值
- 不要执行动作，不要输出命令或代码，不要解释多余内容
- 有「已附带文件正文」标记时：只能选择 write_file；正文由系统注入，**禁止**以缺少正文为由返回 ok=false
- 若指令是写入路径且已标明有附件正文 → 必须 {{"ok": true, "mode": "write_file"}}
- 反例：不要把「查看正在运行的进程」「列出所有进程」路由到 browse_dir / read_file，应选 command

## 输出（仅 JSON）
可路由：{{"ok": true, "mode": "<mode>"}}
不可路由：{{"ok": false, "reason": "具体原因（中文）"}}
"""


def has_file_attachment(file_content: str | None) -> bool:
    return file_content is not None and file_content != ""


def route_instruction_text(action_text: str) -> tuple[str, bool]:
    """供路由使用的指令文本：去掉围栏代码块正文，避免大段内容干扰判断。"""
    has_fenced = bool(extract_fenced_blocks(action_text))
    instruction = strip_fenced_blocks(action_text).strip() or action_text.strip()
    return instruction, has_fenced


def render_route_user(
    action_text: str,
    *,
    has_file_attachment: bool = False,
    has_fenced_body: bool = False,
) -> str:
    flags: list[str] = []
    if has_file_attachment:
        flags.append(
            "【已附带文件正文】内容不在此消息中，但正文真实存在。"
            "必须选择 mode=write_file；禁止以缺少正文为由返回 ok=false。"
        )
    if has_fenced_body:
        flags.append(
            "【消息含代码块正文】代码块已从下方指令剥离；写入场景应选 write_file。"
        )
    flag_block = ("\n".join(flags) + "\n\n") if flags else ""
    return f"""{flag_block}【用户指令】
{action_text}
"""


class ModeRouter:
    """两阶段路由第一步：自然语言 → mode。"""

    def __init__(self) -> None:
        self.llm = get_llm_client(EXECUTOR_ROUTE_SLOT)

    async def route(
        self,
        action_text: str,
        *,
        has_file_attachment: bool = False,
        has_fenced_body: bool = False,
    ) -> tuple[ExecutorMode | None, str]:
        messages = [
            {"role": "system", "content": ROUTE_SYSTEM},
            {
                "role": "user",
                "content": render_route_user(
                    action_text,
                    has_file_attachment=has_file_attachment,
                    has_fenced_body=has_fenced_body,
                ),
            },
        ]
        try:
            data = await self.llm.chat_json(messages)
        except Exception as exc:
            return None, f"子能力路由失败: {exc}"

        return parse_route_response(data)


def parse_route_response(data: Any) -> tuple[ExecutorMode | None, str]:
    if not isinstance(data, dict):
        return None, "子能力路由返回格式无效"
    if data.get("ok") is False:
        return None, str(data.get("reason") or "无法确定应使用的执行子能力")
    mode = data.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        return None, "子能力路由未给出 mode"
    mode = mode.strip()
    if mode not in _MODE_SET:
        return None, f"子能力路由返回未知 mode: {mode!r}"
    return cast(ExecutorMode, mode), ""
