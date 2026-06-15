"""测试程序公共工具：路径引导、异步线程、简易日志框。"""

from __future__ import annotations

import asyncio
import sys
import threading
import traceback
from pathlib import Path
from tkinter import END, Text, Tk, ttk
from typing import Any, Callable

# 将 Local_agent 根目录加入 sys.path，便于直接运行 test/ 下脚本
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_async(coro_factory: Callable[[], Any], on_done: Callable[[Any], None], on_error: Callable[[str], None]) -> None:
    """在后台线程执行 asyncio 协程，完成后回调主线程。"""

    def worker() -> None:
        try:
            result = asyncio.run(coro_factory())
            on_done(result)
        except Exception:
            on_error(traceback.format_exc())

    threading.Thread(target=worker, daemon=True).start()


class LogPanel(ttk.Frame):
    def __init__(self, master: Tk, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self.text = Text(self, wrap="word", height=20, font=("Consolas", 10))
        scroll = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def append(self, msg: str) -> None:
        self.text.insert(END, msg + "\n")
        self.text.see(END)

    def clear(self) -> None:
        self.text.delete("1.0", END)
