from __future__ import annotations

from modules.executor.capabilities.codegen import CodegenCapability
from modules.executor.capabilities.command import CommandCapability
from modules.executor.capabilities.files import FILE_CAPABILITIES

EXECUTOR_MODES = (
    "command",
    "read_file",
    "write_file",
    "delete_file",
    "browse_dir",
    "search_file",
    "search_content",
    "codegen",
)

CAPABILITIES = {
    "command": CommandCapability(),
    "codegen": CodegenCapability(),
    **FILE_CAPABILITIES,
}

__all__ = [
    "EXECUTOR_MODES",
    "CAPABILITIES",
    "CommandCapability",
    "CodegenCapability",
]
