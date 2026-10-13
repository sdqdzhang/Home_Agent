"""live2d_test host: local HTTP + optional desktop-pet window.

Isolated sandbox. Default character is dsh-pet shenshen WebM (not Live2D).
"""

from __future__ import annotations

import argparse
import json
import queue
import socket
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import catalog as catalog_mod
from catalog import CANVAS_H, CANVAS_W, DEFAULT_SCALE, Catalog, MOVE_LEAD_SEC, MOVE_MARGIN, MOVE_TAIL_SEC
from mapper import apply_event, default_mind_state, map_mind_state
from player import Player
from windowing import (
    clamp_on_screen,
    enable_dpi,
    hwnd_of,
    move_hwnd,
    resize_hwnd,
    set_click_through,
    set_no_activate,
    set_topmost,
    window_rect,
    work_area,
)

ROOT = Path(__file__).resolve().parent
OVERLAY = ROOT / "overlay"
LAB_W, LAB_H = 420, 720


class _IdleEdge:
    """Placeholder until the Qt pet window owns a real probe controller."""

    enabled = True
    side = None
    active = False
    mode = "OFF"
    ui_mode = "off"

    def cancel(self, *args, **kwargs) -> None:
        return None

    def maybe_enter(self) -> None:
        return None

    def consume_click(self) -> bool:
        return False

    def on_drag_started(self) -> None:
        return None

    def on_release(self, was_dragging: bool = False) -> None:
        return None

    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)


def pet_size(scale: float) -> tuple[int, int]:
    s = max(0.4, min(1.2, float(scale)))
    return max(160, int(round(CANVAS_W * s))), max(90, int(round(CANVAS_H * s)))


class Store:
    def __init__(self, cat: Catalog) -> None:
        self.lock = threading.Lock()
        self.cat = cat
        self.player = Player(cat)
        self.state = default_mind_state()
        self.intent = map_mind_state(self.state)
        self.click_through = False
        self.on_top = True
        self.generation = 0
        self.scale = DEFAULT_SCALE
        self.pet_window = None
        self.lab_window = None
        self.edge = _IdleEdge()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            clip = self.player.snapshot_clip()
            return {
                "ok": True,
                "generation": self.generation,
                "state": json.loads(json.dumps(self.state)),
                "intent": self.intent.to_dict(),
                "click_through": self.click_through,
                "on_top": self.on_top,
                "scale": self.scale,
                "clip": clip,
                "pinned": self.player.pinned,
                "catalog": self.cat.to_public(),
                "edge": {
                    "mode": getattr(self.edge, "ui_mode", "off"),
                    "side": self.edge.side,
                    "enabled": bool(self.edge.enabled),
                },
            }

    def patch_state(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.state = _deep_merge(self.state, patch or {})
            self.intent = map_mind_state(self.state)
            self.generation += 1
            play = self.player.apply_intent(self.intent)
        if play:
            _push_clip(play)
        return self.snapshot()

    def event(self, event_type: str) -> dict[str, Any]:
        with self.lock:
            self.state = apply_event(self.state, event_type)
            self.intent = map_mind_state(self.state)
            self.player.intent = self.intent
            self.generation += 1
            if event_type == "playful_interaction":
                play = self.player.poke()
            else:
                play = self.player.apply_intent(self.intent)
            self._ack_oneshot()
        if play:
            _push_clip(play)
        return self.snapshot()

    def play_named(self, name: str) -> dict[str, Any]:
        with self.lock:
            play = self.player.preview(str(name or ""))
        if not play:
            snap = self.snapshot()
            snap["ok"] = False
            snap["error"] = "unknown clip"
            return snap
        _push_clip(play)
        return self.snapshot()

    def resume_auto(self) -> dict[str, Any]:
        _sync_room()
        with self.lock:
            play = self.player.unpin()
        if play:
            _push_clip(play)
        return self.snapshot()

    def ended(self) -> dict[str, Any]:
        _sync_room()
        with self.lock:
            play = self.player.on_ended()
        if play:
            _push_clip(play)
        return self.snapshot()

    def _ack_oneshot(self) -> None:
        events = list(self.state.get("recent_events") or [])
        if events:
            events.pop()
            self.state["recent_events"] = events
            self.intent = map_mind_state(self.state)
            self.generation += 1

    def set_scale(self, value: Any = None, delta: Any = None) -> dict[str, Any]:
        with self.lock:
            cur = float(self.scale)
            if delta is not None:
                cur += float(delta)
            elif value is not None:
                cur = float(value)
            self.scale = max(0.45, min(1.15, round(cur, 3)))
        _apply_pet_size()
        return self.snapshot()

    def set_window_flags(self, *, click_through: bool | None = None, on_top: bool | None = None) -> dict[str, Any]:
        with self.lock:
            if click_through is not None:
                self.click_through = bool(click_through)
            if on_top is not None:
                self.on_top = bool(on_top)
        win = self.pet_window
        hwnd = hwnd_of(win)
        if win is not None and hasattr(win, "set_on_top"):
            win.set_on_top(self.on_top)
        elif win is not None:
            try:
                win.on_top = self.on_top
            except Exception:
                set_topmost(hwnd, self.on_top)
        if click_through is not None:
            if win is not None and hasattr(win, "set_force_through"):
                win.set_force_through(self.click_through)
            else:
                set_click_through(hwnd, self.click_through)
                _sync_plate()
        if win is not None and hasattr(win, "_arm_no_activate"):
            win._arm_no_activate()
        else:
            set_no_activate(hwnd)
        return self.snapshot()


STORE: Store


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".webm": "video/webm",
        ".json": "application/json; charset=utf-8",
    }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(OVERLAY), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        try:
            rendered = fmt % args
        except Exception:
            rendered = str(fmt)
        if "/api/state" in rendered or "/api/intent" in rendered:
            return
        sys.stderr.write("[http] " + rendered + "\n")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/api/intent", "/api/state"}:
            self._json(200, STORE.snapshot())
            return
        if path == "/api/catalog":
            self._json(200, {"ok": True, **STORE.cat.to_public()})
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_json()
        if path == "/api/state":
            self._json(200, STORE.patch_state(body if isinstance(body, dict) else {}))
            return
        if path == "/api/event":
            self._json(200, STORE.event(str((body or {}).get("type") or "playful_interaction")))
            return
        if path == "/api/play":
            body = body or {}
            if body.get("auto"):
                self._json(200, STORE.resume_auto())
                return
            self._json(200, STORE.play_named(str(body.get("name") or "")))
            return
        if path == "/api/ended":
            self._json(200, STORE.ended())
            return
        if path == "/api/window":
            body = body or {}
            if body.get("action") == "restore":
                restore_windows()
            if "scale" in body or "scale_delta" in body:
                STORE.set_scale(value=body.get("scale"), delta=body.get("scale_delta"))
            if "click_through" in body or "on_top" in body:
                STORE.set_window_flags(
                    click_through=body.get("click_through") if "click_through" in body else None,
                    on_top=body.get("on_top") if "on_top" in body else None,
                )
            self._json(200, STORE.snapshot())
            return
        self._json(404, {"ok": False, "error": "unknown api"})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)


class Bridge:
    def poke(self) -> dict[str, Any]:
        if STORE.edge.consume_click():
            return STORE.snapshot()
        return STORE.event("playful_interaction")

    def on_ended(self) -> dict[str, Any]:
        return STORE.ended()

    def drag_start(self) -> dict[str, Any]:
        STORE.edge.on_drag_started()
        with STORE.lock:
            play = STORE.player.drag_start()
        if play:
            _push_clip(play)
        return STORE.snapshot()

    def drag_end(self) -> dict[str, Any]:
        with STORE.lock:
            play = STORE.player.drag_end()
        if play:
            _push_clip(play)
        STORE.edge.on_release(True)
        return STORE.snapshot()

    def begin_walk(self, duration: float = 0) -> bool:
        return _begin_walk(float(duration or 0))

    def walk_tick(self, t: float = 0) -> bool:
        return _walk_tick(float(t or 0))

    def set_click_through(self, enabled: bool) -> dict[str, Any]:
        return STORE.set_window_flags(click_through=bool(enabled))

    def restore_windows(self) -> dict[str, Any]:
        restore_windows()
        return STORE.snapshot()

    def nudge_scale(self, delta: float = 0.08) -> dict[str, Any]:
        return STORE.set_scale(delta=delta)

    def snapshot(self) -> dict[str, Any]:
        return STORE.snapshot()

    def peek_click(self) -> dict[str, Any]:
        return {"ok": True, "consumed": STORE.edge.consume_click()}

    def play(self, name: str = "") -> dict[str, Any]:
        return STORE.play_named(str(name or ""))

    def resume_auto(self) -> dict[str, Any]:
        return STORE.resume_auto()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_http(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


_JS_LOCK = threading.Lock()
_JS_QUEUE: queue.SimpleQueue[tuple[Any, str]] | None = None


def _eval_js(script: str, win: Any | None = None) -> None:
    """Run pywebview evaluate_js off the UI thread.

    EdgeChrome.evaluate_js does Control.Invoke + semaphore.acquire() and
    delivers the result on the WinForms sync context. Calling it from the
    UI thread deadlocks the pet window (HTTP /api/state still answers).
    """
    target = win if win is not None else STORE.pet_window
    if target is None or not script:
        return
    global _JS_QUEUE
    with _JS_LOCK:
        if _JS_QUEUE is None:
            pending: queue.SimpleQueue[tuple[Any, str]] = queue.SimpleQueue()
            _JS_QUEUE = pending

            def worker() -> None:
                while True:
                    w, code = pending.get()
                    try:
                        w.evaluate_js(code)
                    except Exception:
                        pass

            threading.Thread(target=worker, daemon=True, name="ha-eval-js").start()
        _JS_QUEUE.put((target, script))


def _qt_call(fn) -> None:
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, fn)
    except Exception:
        try:
            fn()
        except Exception:
            pass


def _push_clip(clip: dict[str, Any] | None) -> None:
    if not clip:
        return
    if getattr(STORE.edge, "active", False) and clip.get("kind") not in {"idle", "turn"}:
        with STORE.lock:
            STORE.player.pinned = None
            STORE.player.want_walk = False
            STORE.player.walk = None
            clip = STORE.player.play(STORE.cat.idle)
        if not clip:
            return
    win = STORE.pet_window
    show = getattr(win, "show_clip", None) if win is not None else None
    if callable(show):
        _qt_call(lambda: show(clip))
        return
    payload = json.dumps(clip, ensure_ascii=False)
    _eval_js(f"window.__play && window.__play({payload})")




def _push_scale() -> None:
    win = STORE.pet_window
    setter = getattr(win, "set_scale", None) if win is not None else None
    if callable(setter):
        _qt_call(lambda: setter(STORE.scale))
        return
    _eval_js(f"window.__setScale && window.__setScale({float(STORE.scale)})")


def _sync_plate() -> None:
    win = STORE.pet_window
    native = getattr(win, "native", None) if win is not None else None
    plate = getattr(native, "_ha_hit_plate", None) if native is not None else None
    if plate is None:
        return
    try:
        plate.Visible = not STORE.click_through
    except Exception:
        pass


def _apply_pet_size() -> None:
    win = STORE.pet_window
    if win is None:
        return
    setter = getattr(win, "set_scale", None)
    if callable(setter):
        setter(STORE.scale)
        return
    w, h = pet_size(STORE.scale)
    hwnd = hwnd_of(win)
    try:
        win.resize(w, h)
    except Exception:
        resize_hwnd(hwnd, w, h)
    _push_scale()


def _pet_slot() -> tuple[int, int]:
    left, top, right, bottom = work_area()
    w, h = pet_size(STORE.scale)
    x = left + 48 + LAB_W + 16
    y = top + 72
    max_x = max(left + 16, right - w - 16)
    max_y = max(top + 16, bottom - h - 16)
    return min(max(x, left + 16), max_x), min(max(y, top + 16), max_y)


def _lab_slot() -> tuple[int, int]:
    left, top, right, bottom = work_area()
    x = left + 32
    y = top + 48
    max_x = max(left + 16, right - LAB_W - 16)
    max_y = max(top + 16, bottom - LAB_H - 16)
    return min(max(x, left + 16), max_x), min(max(y, top + 16), max_y)


def _sync_room() -> None:
    hwnd = hwnd_of(STORE.pet_window)
    wx, _wy, wr, _wb = window_rect(hwnd)
    left, _top, right, _bottom = work_area()
    STORE.player.room = {
        "cx": (wx + wr) / 2 if wr > wx else 0,
        "left": left,
        "right": right,
        "margin": MOVE_MARGIN,
    }


def restore_windows() -> None:
    STORE.edge.cancel(restore=False)
    pet, lab = STORE.pet_window, STORE.lab_window
    if lab is not None:
        px, py = _lab_slot()
        try:
            lab.show()
            lab.move(px, py)
            if hasattr(lab, "raise_"):
                lab.raise_()
                if hasattr(lab, "activateWindow"):
                    lab.activateWindow()
        except Exception:
            pass
    if pet is not None:
        x, y = _pet_slot()
        try:
            pet.show()
            pet.move(x, y)
        except Exception:
            move_hwnd(hwnd_of(pet), x, y)
        hwnd = hwnd_of(pet)
        clamp_on_screen(hwnd, (x, y), pet_size(STORE.scale))
        if hasattr(pet, "set_on_top"):
            pet.set_on_top(STORE.on_top)
        else:
            try:
                pet.on_top = STORE.on_top
            except Exception:
                set_topmost(hwnd, STORE.on_top)
        if hasattr(pet, "_arm_no_activate"):
            pet._arm_no_activate()
        else:
            set_no_activate(hwnd)


def _begin_walk(duration: float) -> bool:
    from wander import plan_walk

    player = STORE.player
    if not player.want_walk or player.clip is None or player.clip.kind != "move":
        return False
    if getattr(STORE.edge, "active", False):
        player.want_walk = False
        return False
    hwnd = hwnd_of(STORE.pet_window)
    wx, wy, wr, wb = window_rect(hwnd)
    width, height = wr - wx, wb - wy
    left, top, right, bottom = work_area()
    _sync_room()
    planned = plan_walk(
        wx=wx,
        wy=wy,
        width=width,
        height=height,
        facing=player.facing,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
    )
    if not planned:
        player.want_walk = False
        return False
    player.facing = str(planned["facing"])
    player.walk = {
        "start_x": wx,
        "start_y": wy,
        "target_x": planned["target_x"],
        "target_y": planned["target_y"],
        "duration": max(duration, MOVE_LEAD_SEC + MOVE_TAIL_SEC + 0.4),
    }
    return True


def _walk_tick(t: float) -> bool:
    if STORE.player.dragging or getattr(STORE.edge, "active", False):
        return False
    plan = STORE.player.walk
    hwnd = hwnd_of(STORE.pet_window)
    if not plan or not hwnd:
        return False
    dur = float(plan["duration"])
    lead, tail = MOVE_LEAD_SEC, MOVE_TAIL_SEC
    if t <= lead:
        x, y = plan["start_x"], plan["start_y"]
    elif t >= dur - tail:
        x, y = plan["target_x"], plan["target_y"]
        STORE.player.walk = None
        STORE.player.want_walk = False
    else:
        progress = (t - lead) / max(0.1, dur - lead - tail)
        x = plan["start_x"] + (plan["target_x"] - plan["start_x"]) * progress
        y = plan["start_y"] + (plan["target_y"] - plan["start_y"]) * progress
    move_hwnd(hwnd, int(round(x)), int(round(y)))
    return True


def open_qt_windows(*, opaque: bool = False) -> int:
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication

    from lab_window import LabWindow
    from pet_window import PetWindow

    enable_dpi()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(16, 20, 28))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(232, 237, 245))
    pal.setColor(QPalette.ColorRole.Base, QColor(14, 20, 31))
    pal.setColor(QPalette.ColorRole.Text, QColor(232, 237, 245))
    pal.setColor(QPalette.ColorRole.Button, QColor(43, 59, 92))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(232, 237, 245))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(74, 107, 212))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(pal)

    def on_click() -> None:
        if STORE.edge.consume_click():
            return
        STORE.event("playful_interaction")

    def on_drag_start() -> None:
        STORE.edge.on_drag_started()
        with STORE.lock:
            play = STORE.player.drag_start()
        if play:
            _push_clip(play)

    def on_drag_end() -> None:
        with STORE.lock:
            play = STORE.player.drag_end()
        if play:
            _push_clip(play)
        STORE.edge.on_release(True)

    def toggle_edge() -> None:
        STORE.edge.set_enabled(not STORE.edge.enabled)

    def show_lab() -> None:
        lab = STORE.lab_window
        if lab is None:
            return
        lab.show()
        lab.raise_()
        lab.activateWindow()

    def switch_clip(name: str) -> None:
        with STORE.lock:
            STORE.player.pinned = None
            play = STORE.player.play(name)
            STORE.player.want_walk = False
            STORE.player.walk = None
        win = STORE.pet_window
        if play and win is not None:
            win.show_clip(play)

    def cancel_walk() -> None:
        with STORE.lock:
            STORE.player.want_walk = False
            STORE.player.walk = None

    hooks = {
        "click": on_click,
        "drag_start": on_drag_start,
        "drag_end": on_drag_end,
        "scale": lambda d: STORE.set_scale(delta=d),
        "toggle_edge": toggle_edge,
        "restore": restore_windows,
        "show_lab": show_lab,
        "ended": STORE.ended,
        "begin_walk": _begin_walk,
        "walk_tick": _walk_tick,
        "idle_names": lambda: list(STORE.cat.cats.get("idles") or []),
        "turn_names": lambda: list(STORE.cat.cats.get("turns") or []),
        "switch_clip": switch_clip,
        "cancel_walk": cancel_walk,
    }
    pet = PetWindow(hooks, opaque=opaque)
    lab = LabWindow(STORE, {"restore": restore_windows, "quit": app.quit})
    STORE.pet_window = pet
    STORE.lab_window = lab
    enabled = bool(STORE.edge.enabled)
    STORE.edge = pet.probe
    STORE.edge.enabled = enabled
    restore_windows()
    with STORE.lock:
        play = STORE.player.snapshot_clip() or STORE.player.start()
    if play:
        pet.show_clip(play)
    app.aboutToQuit.connect(pet.shutdown)
    return int(app.exec())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="桌宠沙盒（神神 WebM，不接入 HomeAgent）")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--transparent",
        action="store_true",
        help="兼容旧开关：Qt 桌宠默认就是透明抠像。",
    )
    parser.add_argument(
        "--opaque",
        action="store_true",
        help="桌宠铺深色底，不做透明抠像。",
    )
    return parser.parse_args()


def main() -> int:
    global STORE
    args = parse_args()
    enable_dpi()
    if not OVERLAY.is_dir():
        print(f"找不到 overlay 目录: {OVERLAY}", file=sys.stderr)
        return 1
    try:
        videos = catalog_mod.ensure_videos()
    except FileNotFoundError as err:
        print(err, file=sys.stderr)
        return 1
    cat = Catalog(videos)
    STORE = Store(cat)
    with STORE.lock:
        STORE.player.start()
    port = args.port or _free_port()
    server = start_http(port)
    base = f"http://127.0.0.1:{port}"
    print(f"live2d_test  {base}/")
    print(f"  实验室 Qt 窗口；桌宠是无边框透明小人")
    print(f"  浏览器实验室 {base}/lab.html")
    print(f"  素材  {videos}  ({len(cat.files)} webm)")
    print("  单测: python -m unittest discover -s . -p 'test_*.py'")
    code = 0
    try:
        if args.browser:
            webbrowser.open(f"{base}/lab.html")
            webbrowser.open(f"{base}/index.html")
            print("浏览器模式：Ctrl+C 结束")
            while True:
                time.sleep(1)
        else:
            try:
                code = open_qt_windows(opaque=bool(args.opaque))
            except ImportError as err:
                print(f"未安装 Qt 桌宠依赖: {err}")
                print("请运行: .venv\\Scripts\\python.exe -m pip install -r requirements.txt")
                webbrowser.open(f"{base}/lab.html")
                print("已改为只开浏览器实验室。Ctrl+C 结束")
                while True:
                    time.sleep(1)
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.shutdown()
    return int(code or 0)


if __name__ == "__main__":
    sys.exit(main())
