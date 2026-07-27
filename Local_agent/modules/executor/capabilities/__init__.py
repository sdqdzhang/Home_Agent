from __future__ import annotations

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
)

CAPABILITIES = {
    "command": CommandCapability(),
    **FILE_CAPABILITIES,
}

__all__ = [
    "EXECUTOR_MODES",
    "CAPABILITIES",
    "CommandCapability",
]
