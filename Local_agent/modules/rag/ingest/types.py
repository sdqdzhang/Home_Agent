from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SplitPiece:
    """分块结果：正文 + 附加 metadata（如 Header_1）。"""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
