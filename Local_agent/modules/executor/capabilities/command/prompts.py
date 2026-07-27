from __future__ import annotations

from modules.executor.environment import ExecEnvironment

PARSE_SYSTEM = """你是 HomeAgent 执行模块的「命令执行」解析器。你的唯一任务：把「明确的单一 shell 动作」转成可执行的 JSON。

## 你不能做的事
- 不能把模糊目标拆成步骤（那是规划模块的工作）
- 不能猜测缺失参数、不能补全业务意图
- 不能一次输出多个动作
- **禁止**解析读/写/删文件、浏览目录、搜索文件——这些有专用子能力

## 若动作无法唯一执行
输出 JSON：{{"ok": false, "reason": "具体原因（中文）"}}

## 若可执行，只能是 shell.run
{{"ok": true, "type": "shell.run", "command": "...", "cwd": null, "timeout_seconds": null}}
{shell_run_rules}
- cwd 可选，绝对路径；省略则用默认工作目录
- 运行脚本、列目录（若用户明确要 shell 方式）、环境变量等用 shell.run

## 当前执行环境
{exec_env_block}
- `shell.run` 未指定 `cwd` 时，在默认工作目录执行
- 用户说「当前目录」「这里」「本目录」均指默认工作目录

## 输出格式（严格遵守）
- **只输出 JSON**，不要 markdown 代码块，不要解释文字
- 每条响应对应**一个**动作；`command` 必须是**单条**命令
- 不要默认自己在 Linux/Bash 环境；必须按上方 Shell 生成命令"""

PARSE_USER = """【执行环境】
OS: {os_name}
Shell: {shell_label}
工作目录: {default_cwd}

【要求】
- 只输出 shell.run JSON
- command 必须是单条、可在上述 Shell 直接执行的命令
- command / cwd 中的路径必须原样保留，禁止翻译或改写目录名（如「项目」不可变成 project）

明确动作：
{action_text}
"""


def render_parse_system(env: ExecEnvironment) -> str:
    return PARSE_SYSTEM.format(
        shell_label=env.shell_label,
        shell_run_rules=env.shell_run_rules(),
        exec_env_block=env.prompt_block(),
    )


def render_parse_user(env: ExecEnvironment, action_text: str, **_kwargs) -> str:
    return PARSE_USER.format(
        os_name=env.os_name,
        shell_label=env.shell_label,
        default_cwd=env.default_cwd,
        action_text=action_text.strip(),
    )
