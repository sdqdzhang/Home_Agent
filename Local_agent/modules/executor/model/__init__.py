"""向后兼容：模型解析已迁至 capabilities.command。"""

from modules.executor.capabilities.command.assistant import CommandAssistant, ExecutorAssistant
from modules.executor.capabilities.command.prompts import render_parse_system, render_parse_user

__all__ = ["CommandAssistant", "ExecutorAssistant", "render_parse_system", "render_parse_user"]
