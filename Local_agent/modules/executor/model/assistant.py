"""向后兼容。"""

from modules.executor.capabilities.command.assistant import CommandAssistant as ExecutorAssistant
from modules.executor.capabilities.command.prompts import render_parse_system, render_parse_user

__all__ = ["ExecutorAssistant", "render_parse_system", "render_parse_user"]
