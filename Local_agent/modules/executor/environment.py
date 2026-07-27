from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from functools import lru_cache

from modules.executor.config import executor_settings


@dataclass(frozen=True)
class ExecEnvironment:
    """当前执行环境，供 prompt 与命令校验共用。"""

    os_name: str
    shell: str
    shell_label: str
    default_cwd: str

    def path_rules(self) -> str:
        return (
            "## 路径规则（严格遵守）\n"
            f"- 默认工作目录为：`{self.default_cwd}` — 若使用，必须与该字符串**完全一致**\n"
            "- 用户消息里出现的任何路径必须**原样复制**到 JSON/command/cwd 中，不得改动任何字符\n"
            "- **禁止**翻译、替换或改写路径段（例如把中文目录名「项目」改成 project、homeagent 改成别的拼写）\n"
            "- **禁止**自行猜测路径；仅当用户未给出路径时，才可基于默认工作目录或用户明确提到的相对路径拼接"
        )

    def prompt_block(self) -> str:
        lines = [
            f"- 操作系统：{self.os_name}",
            f"- Shell：{self.shell_label}",
            f"- 默认工作目录：`{self.default_cwd}`",
        ]
        forbidden = self.forbidden_operators()
        if forbidden:
            lines.append(f"- 禁止在 command 中使用 Bash/Linux 专用写法：{', '.join(forbidden)}")
        lines.append(self.path_rules())
        return "\n".join(lines)

    def forbidden_operators(self) -> list[str]:
        shell = self.shell.lower()
        if shell == "powershell":
            return ["&&", "nohup", "sleep", "wait", "disown", "bg", "fg"]
        if shell == "cmd":
            return ["nohup", "sleep", "wait"]
        return []

    def shell_run_rules(self) -> str:
        shell = self.shell.lower()
        if shell == "powershell":
            return (
                "- command 必须是**单条** PowerShell 命令，可直接传给 `powershell.exe -Command`\n"
                "- `&` 是合法的调用运算符（如 `& { ... }`）；后台启动用 `Start-Process`，"
                "等待用 `Start-Sleep -Seconds N`\n"
                "- 禁止使用 Bash 写法：`&&`、`nohup`、裸 `sleep`/`wait`、`disown`、`bg`、`fg`\n"
                "- 串行多步请由规划模块拆成多步；此处只生成当前这一步的一条命令"
            )
        if shell == "cmd":
            return (
                "- command 必须是**单条** cmd 命令，可直接传给 `cmd.exe /c`\n"
                "- 后台与等待请用 Windows 原生命令（如 `start`、`timeout /t`），"
                "不要用 `nohup`、`sleep`、`wait`"
            )
        return (
            "- command 必须是**单条** shell 命令\n"
            "- 只输出可在当前 Shell 直接执行的语法，不要混用其他 Shell 的写法"
        )


@lru_cache(maxsize=1)
def _detect_powershell_label() -> str:
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$PSVersionTable.PSVersion.ToString()",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        version = (result.stdout or "").strip()
        if result.returncode == 0 and version:
            return f"Windows PowerShell {version}"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "Windows PowerShell"


def _shell_label(shell: str) -> str:
    key = shell.strip().lower()
    if key == "powershell":
        return _detect_powershell_label()
    if key == "cmd":
        return "Windows Command Prompt (cmd.exe)"
    if key in ("bash", "sh"):
        return "Bash"
    return shell


def get_exec_environment() -> ExecEnvironment:
    cwd = str(executor_settings.default_cwd.resolve())
    shell = executor_settings.shell.strip().lower() or "powershell"
    return ExecEnvironment(
        os_name=platform.system(),
        shell=shell,
        shell_label=_shell_label(shell),
        default_cwd=cwd,
    )
