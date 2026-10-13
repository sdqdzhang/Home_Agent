"""Win32 window helpers. Never OR WS_EX_LAYERED on the pet form."""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000
GWL_EXSTYLE = -20

BAR_H = 36


def enable_dpi() -> None:
    """No-op: Qt 6 already sets DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2.

    Calling SetProcessDpiAwareness before QApplication makes Qt's later
    SetProcessDpiAwarenessContext fail with Access Denied (拒绝访问) and
    leaves the process on V1 awareness, so native vs Qt coordinates drift.
    """
    return


def work_area() -> tuple[int, int, int, int]:
    if os.name != "nt":
        return (0, 0, 1280, 720)
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def screen_work_area(window: Any = None) -> tuple[int, int, int, int]:
    """Work area of the monitor that currently holds ``window``."""
    hwnd = hwnd_of(window) if window is not None else 0
    area = _monitor_work(hwnd) if hwnd else None
    return area if area is not None else work_area()


def _monitor_work(hwnd: int) -> tuple[int, int, int, int] | None:
    if os.name != "nt" or not hwnd:
        return None
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)
    if not monitor:
        return None
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    rect = info.rcWork
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def hwnd_of(window) -> int:
    if window is None:
        return 0
    try:
        handle = window.winId()
        if hasattr(handle, "toInt64"):
            return int(handle.toInt64())  # type: ignore[attr-defined]
        return int(handle)
    except Exception:
        pass
    native = getattr(window, "native", None)
    for attr in ("Handle", "handle", "Hwnd", "hwnd"):
        try:
            handle = getattr(native, attr)
            if hasattr(handle, "ToInt64"):
                return int(handle.ToInt64())
            if hasattr(handle, "ToInt32"):
                return int(handle.ToInt32())
            value = int(handle)
            if value:
                return value
        except Exception:
            continue
    if os.name != "nt":
        return 0
    import ctypes

    title = str(getattr(window, "title", "") or "")
    if not title:
        return 0
    return int(ctypes.windll.user32.FindWindowW(None, title) or 0)


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    if os.name != "nt" or not hwnd:
        return (0, 0, 0, 0)
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_ASYNCWINDOWPOS = 0x4000


def move_hwnd(hwnd: int, x: int, y: int) -> None:
    if os.name != "nt" or not hwnd:
        return
    import ctypes

    ctypes.windll.user32.SetWindowPos(
        hwnd,
        0,
        int(x),
        int(y),
        0,
        0,
        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
    )


def resize_hwnd(hwnd: int, w: int, h: int) -> None:
    if os.name != "nt" or not hwnd:
        return
    import ctypes

    ctypes.windll.user32.SetWindowPos(
        hwnd, 0, 0, 0, int(w), int(h), SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS
    )


def show_hwnd(hwnd: int, *, activate: bool = False) -> None:
    if os.name != "nt" or not hwnd:
        return
    import ctypes

    ctypes.windll.user32.ShowWindow(hwnd, 9)
    ctypes.windll.user32.ShowWindow(hwnd, 5)
    if activate:
        ctypes.windll.user32.SetForegroundWindow(hwnd)


def clamp_on_screen(hwnd: int, fallback: tuple[int, int], size: tuple[int, int]) -> None:
    if not hwnd:
        return
    left, top, right, bottom = work_area()
    wx, wy, wr, wb = window_rect(hwnd)
    width = wr - wx if wr > wx else size[0]
    height = wb - wy if wb > wy else size[1]
    off = wr < left + 8 or wx > right - 8 or wb < top + 8 or wy > bottom - 8
    if off or width < 80 or height < 80:
        move_hwnd(hwnd, fallback[0], fallback[1])
        return
    x = min(max(wx, left + 8), max(left + 8, right - width - 8))
    y = min(max(wy, top + 8), max(top + 8, bottom - height - 8))
    if (x, y) != (wx, wy):
        move_hwnd(hwnd, x, y)


def set_topmost(hwnd: int, enabled: bool) -> None:
    if os.name != "nt" or not hwnd:
        return
    import ctypes

    ctypes.windll.user32.SetWindowPos(
        hwnd, -1 if enabled else -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040
    )


def set_no_activate(hwnd: int) -> None:
    if os.name != "nt" or not hwnd:
        return
    import ctypes

    get = ctypes.windll.user32.GetWindowLongW
    set_ = ctypes.windll.user32.SetWindowLongW
    style = get(hwnd, GWL_EXSTYLE)
    set_(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)


def set_click_through(hwnd: int, enabled: bool) -> None:
    if os.name != "nt" or not hwnd:
        return
    import ctypes

    get = ctypes.windll.user32.GetWindowLongW
    set_ = ctypes.windll.user32.SetWindowLongW
    style = get(hwnd, GWL_EXSTYLE)
    if enabled:
        style |= WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    style |= WS_EX_NOACTIVATE
    set_(hwnd, GWL_EXSTYLE, style)


def cursor_pos() -> tuple[int, int]:
    if os.name != "nt":
        return (0, 0)
    import ctypes
    from ctypes import wintypes

    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def _lmb_down() -> bool:
    if os.name != "nt":
        return False
    import ctypes

    return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)


def _run_bg(fn: Callable | None) -> None:
    if fn is None:
        return

    def run() -> None:
        try:
            fn()
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


def bind_move_drag(control, window, hooks: dict[str, Any], *, click: Callable | None = None) -> None:
    """Follow the cursor from a worker thread.

    Never SendMessage(HTCAPTION), never evaluate_js / Invoke on the UI
    thread: pywebview waits for WebView2 on a semaphore, which deadlocks
    the message pump ('未响应') while HTTP still answers /api/state.
    """
    try:
        from System.Windows.Forms import MouseButtons
    except Exception:
        return
    state = {"down": False, "moved": False, "gx": 0, "gy": 0, "ox": 0, "oy": 0, "hwnd": 0}
    lock = threading.Lock()

    def _release_capture() -> None:
        try:
            control.Capture = False
        except Exception:
            pass

    def finish(*, from_ui: bool) -> None:
        with lock:
            if not state["down"]:
                return
            state["down"] = False
            moved = bool(state["moved"])
        if from_ui:
            _release_capture()
        else:
            invoke_ui(window, _release_capture)
        if moved:
            _run_bg(hooks.get("drag_end"))
        elif click is not None:
            _run_bg(click)

    def loop() -> None:
        last: tuple[int, int] | None = None
        try:
            while True:
                with lock:
                    if not state["down"]:
                        return
                    hwnd = int(state["hwnd"])
                    gx, gy = int(state["gx"]), int(state["gy"])
                    ox, oy = int(state["ox"]), int(state["oy"])
                    moved = bool(state["moved"])
                if not _lmb_down():
                    finish(from_ui=False)
                    return
                cx, cy = cursor_pos()
                if not moved:
                    if abs(cx - ox) + abs(cy - oy) < 8:
                        time.sleep(0.016)
                        continue
                    fire_start = False
                    with lock:
                        if state["down"] and not state["moved"]:
                            state["moved"] = True
                            fire_start = True
                    if fire_start:
                        _run_bg(hooks.get("drag_start"))
                pos = (cx - gx, cy - gy)
                if pos != last:
                    move_hwnd(hwnd, pos[0], pos[1])
                    last = pos
                time.sleep(0.016)
        except Exception:
            finish(from_ui=False)

    def on_down(_s, evt) -> None:
        if evt.Button != MouseButtons.Left:
            return
        hwnd = hwnd_of(window)
        if not hwnd:
            return
        wx, wy, _wr, _wb = window_rect(hwnd)
        cx, cy = cursor_pos()
        with lock:
            if state["down"]:
                return
            state.update(down=True, moved=False, gx=cx - wx, gy=cy - wy, ox=cx, oy=cy, hwnd=hwnd)
        try:
            control.Capture = True
        except Exception:
            pass
        threading.Thread(target=loop, daemon=True, name="ha-drag").start()

    def on_up(_s, evt) -> None:
        if evt.Button != MouseButtons.Left:
            return
        finish(from_ui=True)

    control.MouseDown += on_down
    control.MouseUp += on_up


def control_hwnd(control) -> int:
    try:
        handle = control.Handle
        if hasattr(handle, "ToInt32"):
            return int(handle.ToInt32())
        return int(handle)
    except Exception:
        return 0


def set_child_layered_alpha(hwnd: int, alpha: int) -> None:
    """Hit-plate only. Do not call on the pet form."""
    if os.name != "nt" or not hwnd:
        return
    import ctypes

    user32 = ctypes.windll.user32
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        get = user32.GetWindowLongPtrW
        set_ = user32.SetWindowLongPtrW
    else:
        get = user32.GetWindowLongW
        set_ = user32.SetWindowLongW
    try:
        style = int(get(hwnd, GWL_EXSTYLE) or 0)
        set_(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
        user32.SetLayeredWindowAttributes(hwnd, 0, max(1, min(255, int(alpha))), 0x00000002)
    except Exception:
        pass


def invoke_ui(window, fn: Callable[[], None]) -> None:
    if window is None:
        try:
            fn()
        except Exception:
            pass
        return
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, fn)
        return
    except Exception:
        pass
    native = getattr(window, "native", None)
    if native is None:
        try:
            fn()
        except Exception:
            pass
        return
    try:
        from System.Windows.Forms import MethodInvoker

        native.BeginInvoke(MethodInvoker(fn))
    except Exception:
        try:
            fn()
        except Exception:
            pass


def install_hit_plate(window, hooks: dict[str, Any]) -> None:
    if os.name != "nt" or window is None:
        return
    native = getattr(window, "native", None)
    if native is None or getattr(native, "_ha_hit_plate", None) is not None:
        return
    try:
        from System.Drawing import Color
        from System.Windows.Forms import (
            ContextMenuStrip,
            Cursors,
            Panel,
            ToolStripMenuItem,
        )
    except Exception:
        return

    def on_ui() -> None:
        if getattr(native, "_ha_hit_plate", None) is not None:
            return
        plate = Panel()
        plate.BackColor = Color.FromArgb(255, 255, 0, 0)
        plate.Cursor = Cursors.Hand
        bind_move_drag(plate, window, hooks, click=hooks.get("click"))

        def on_wheel(_s, evt) -> None:
            delta = 0.08 if int(getattr(evt, "Delta", 0) or 0) > 0 else -0.08
            hooks["scale"](delta)

        try:
            plate.MouseWheel += on_wheel
        except Exception:
            pass

        menu = ContextMenuStrip()

        def add_item(label: str, handler) -> None:
            item = ToolStripMenuItem(label)

            def on_click(_s, _e, fn=handler) -> None:
                fn()

            item.Click += on_click
            menu.Items.Add(item)

        add_item("戳一下", hooks["click"])
        add_item("缩小", lambda: hooks["scale"](-0.08))
        add_item("放大", lambda: hooks["scale"](0.08))
        add_item("边缘探头 开/关", hooks["toggle_edge"])
        add_item("复位", hooks["restore"])
        plate.ContextMenuStrip = menu
        native.Controls.Add(plate)
        native._ha_hit_plate = plate
        try:
            native.Resize += lambda _s, _e: layout_hit_plate(window)
        except Exception:
            pass
        layout_hit_plate(window)

    try:
        from System.Windows.Forms import MethodInvoker

        native.BeginInvoke(MethodInvoker(on_ui))
    except Exception:
        try:
            on_ui()
        except Exception:
            pass


def layout_hit_plate(window) -> None:
    native = getattr(window, "native", None) if window is not None else None
    plate = getattr(native, "_ha_hit_plate", None) if native is not None else None
    if native is None or plate is None:
        return
    try:
        plate.Left = 0
        bar = getattr(native, "_ha_drag_bar", None)
        bar_h = int(getattr(bar, "Height", 0) or 0)
        plate.Top = bar_h
        plate.Width = int(native.ClientSize.Width)
        plate.Height = max(40, int(native.ClientSize.Height) - bar_h)
        plate.BringToFront()
        set_child_layered_alpha(control_hwnd(plate), 4)
        bar = getattr(native, "_ha_drag_bar", None)
        if bar is not None:
            bar.BringToFront()
    except Exception:
        pass


def install_drag_strip(window, hooks: dict[str, Any]) -> None:
    """Opaque top bar so the pet window is always findable (not chroma-keyed)."""
    if os.name != "nt" or window is None:
        return
    native = getattr(window, "native", None)
    if native is None or getattr(native, "_ha_drag_bar", None) is not None:
        return
    try:
        from System.Drawing import Color, Font, FontStyle
        from System.Windows.Forms import Button, Cursors, DockStyle, Label, Panel
    except Exception:
        return

    def on_ui() -> None:
        if getattr(native, "_ha_drag_bar", None) is not None:
            return
        bar = Panel()
        bar.Height = BAR_H
        bar.Dock = DockStyle.Top
        bar.BackColor = Color.FromArgb(255, 36, 48, 73)
        bar.Cursor = Cursors.SizeAll
        bind_move_drag(bar, window, hooks)

        label = Label()
        label.Text = "按住这里拖动 · 桌宠"
        label.ForeColor = Color.FromArgb(255, 232, 237, 245)
        try:
            label.Font = Font("Microsoft YaHei UI", 9, FontStyle.Regular)
        except Exception:
            pass
        label.AutoSize = True
        label.Left = 12
        label.Top = 9
        label.Cursor = Cursors.SizeAll
        bind_move_drag(label, window, hooks)
        bar.Controls.Add(label)

        reset = Button()
        reset.Text = "复位"
        reset.Width = 64
        reset.Dock = DockStyle.Right
        reset.BackColor = Color.FromArgb(255, 58, 78, 119)
        reset.ForeColor = Color.White
        reset.Cursor = Cursors.Hand
        reset.Click += lambda _s, _e: hooks["restore"]()
        bar.Controls.Add(reset)

        native.Controls.Add(bar)
        bar.BringToFront()
        native._ha_drag_bar = bar
        layout_hit_plate(window)

    try:
        from System.Windows.Forms import MethodInvoker

        native.BeginInvoke(MethodInvoker(on_ui))
    except Exception:
        try:
            on_ui()
        except Exception:
            pass
