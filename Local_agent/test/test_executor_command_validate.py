from __future__ import annotations

from modules.executor.command_validate import validate_shell_command
from modules.executor.environment import ExecEnvironment


def _env(shell: str, os_name: str = "Windows") -> ExecEnvironment:
    return ExecEnvironment(
        os_name=os_name,
        shell=shell,
        shell_label=f"test-{shell}",
        default_cwd="C:/workspace",
    )


class TestValidateShellCommand:
    def test_powershell_rejects_bash_chain_without_blocking_ampersand(self):
        err = validate_shell_command(
            "python app.py & wait 2 seconds && pytest test_api.py -v",
            _env("powershell"),
        )
        assert err is not None
        assert "&&" in err
        assert "wait" in err
        assert "包含不兼容语法（&&、wait）" in err or "wait" in err

    def test_powershell_allows_call_operator(self):
        assert validate_shell_command("& { Get-Process }", _env("powershell")) is None
        assert (
            validate_shell_command(
                'powershell.exe -Command "& { Write-Output 1 }"',
                _env("powershell"),
            )
            is None
        )

    def test_powershell_allows_ampersand_between_commands(self):
        assert validate_shell_command("python app.py & pytest", _env("powershell")) is None

    def test_powershell_accepts_simple_command(self):
        assert validate_shell_command("pytest test_api.py -v", _env("powershell")) is None

    def test_powershell_accepts_start_process_pattern(self):
        cmd = 'Start-Process python -ArgumentList "app.py" -WindowStyle Hidden'
        assert validate_shell_command(cmd, _env("powershell")) is None

    def test_powershell_rejects_sleep(self):
        err = validate_shell_command("sleep 2", _env("powershell"))
        assert err is not None
        assert "sleep" in err

    def test_powershell_allows_start_sleep(self):
        assert validate_shell_command("Start-Sleep -Seconds 2", _env("powershell")) is None

    def test_powershell_allows_wait_process(self):
        assert validate_shell_command("Wait-Process -Name python", _env("powershell")) is None

    def test_powershell_rejects_disown_bg_fg(self):
        for word in ("disown", "bg", "fg"):
            err = validate_shell_command(word, _env("powershell"))
            assert err is not None
            assert word in err

    def test_empty_command(self):
        assert validate_shell_command("  ", _env("powershell")) == "command 为空"

    def test_linux_skips_validation(self):
        env = _env("bash", os_name="Linux")
        assert validate_shell_command("a && b & sleep 1 && nohup cmd", env) is None

    def test_bash_on_windows_skips_validation(self):
        assert validate_shell_command("a && b", _env("bash")) is None
