from __future__ import annotations

import re

from modules.executor.environment import ExecEnvironment, get_exec_environment

# Bash/Linux 专用词；排除 PowerShell cmdlet（如 Start-Sleep、Wait-Process）
_SLEEP = re.compile(r"(?<!Start-)\bsleep\b", re.IGNORECASE)
_WAIT = re.compile(r"(?<!Wait-)\bwait\b", re.IGNORECASE)
_NOHUP = re.compile(r"\bnohup\b", re.IGNORECASE)
_DISOWN = re.compile(r"\bdisown\b", re.IGNORECASE)
_BG = re.compile(r"\bbg\b", re.IGNORECASE)
_FG = re.compile(r"\bfg\b", re.IGNORECASE)


def validate_shell_command(
    command: str,
    env: ExecEnvironment | None = None,
) -> str | None:
    """校验 shell 命令是否与当前环境兼容。不兼容时返回原因，否则返回 None。"""
    env = env or get_exec_environment()
    text = command.strip()
    if not text:
        return "command 为空"

    if env.os_name.lower() == "linux":
        return None

    shell = env.shell.lower()
    if shell == "powershell":
        return _validate_powershell(text, env)
    if shell == "cmd":
        return _validate_cmd(text, env)
    return None


def _join_issue(issues: list[str], env: ExecEnvironment) -> str:
    detail = "、".join(issues)
    return f"Command incompatible with {env.shell_label}：包含不兼容语法（{detail}）"


def _validate_powershell(command: str, env: ExecEnvironment) -> str | None:
    issues: list[str] = []

    if "&&" in command:
        issues.append("&&")
    if _NOHUP.search(command):
        issues.append("nohup")
    if _SLEEP.search(command):
        issues.append("sleep")
    if _WAIT.search(command):
        issues.append("wait")
    if _DISOWN.search(command):
        issues.append("disown")
    if _BG.search(command):
        issues.append("bg")
    if _FG.search(command):
        issues.append("fg")

    if issues:
        return _join_issue(issues, env)
    return None


def _validate_cmd(command: str, env: ExecEnvironment) -> str | None:
    issues: list[str] = []

    if _SLEEP.search(command):
        issues.append("sleep")
    if _WAIT.search(command):
        issues.append("wait")
    if _NOHUP.search(command):
        issues.append("nohup")

    if issues:
        return _join_issue(issues, env)
    return None
