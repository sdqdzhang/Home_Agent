"""Frameless transparent desktop pet (PySide6 + ffmpeg RGBA frames)."""

from __future__ import annotations

import time
from typing import Any, Callable

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import (
    QBitmap,
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPixmap,
    QRegion,
    QWheelEvent,
)
from PySide6.QtWidgets import QMenu, QWidget

from catalog import CANVAS_H, CANVAS_W, DEFAULT_SCALE
from edge_probe import EdgeProbeController, unrotate_point
from windowing import cursor_pos, move_hwnd, set_click_through, set_no_activate, window_rect

_HIT_ALPHA = 16
_DRAG_PX = 8
IDLE_LOW_FPS_THRESHOLD = 30.0
IDLE_LOW_FPS_DIVISOR = 2


class PetWindow(QWidget):
    def __init__(self, hooks: dict[str, Callable], *, opaque: bool = False) -> None:
        super().__init__(None)
        self._hooks = hooks
        self._opaque = opaque
        self._pixmap: QPixmap | None = None
        self._hit: QImage | None = None
        self._source: QImage | None = None
        self._mask_bounds: QRect | None = None
        self._clip: dict[str, Any] | None = None
        self._scale = DEFAULT_SCALE
        self._press: QPoint | None = None
        self._grab = QPoint(0, 0)
        self._grab_phys = (0, 0)
        self._press_phys = (0, 0)
        self._dragging = False
        self._force_through = False
        self._through: bool | None = None
        self._frame_key: tuple | None = None
        self._active_at = time.monotonic()
        from webm_player import WebmPlayer

        self._player = WebmPlayer(self)
        self._player.frame_ready.connect(self._on_frame)
        self._player.finished.connect(self._on_finished)
        self._player.meta_ready.connect(self._on_meta)

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, not opaque)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.probe = EdgeProbeController(self)
        self.set_scale(self._scale)

        self._hit_timer = QTimer(self)
        self._hit_timer.setInterval(16)
        self._hit_timer.timeout.connect(self._refresh_hit)
        self._hit_timer.start()

    def character_local_region(self) -> QRect:
        """Opaque sprite box in widget coordinates (not the full 640×360 canvas)."""
        bounds = self._mask_bounds
        if bounds is None or bounds.isEmpty():
            return QRect()
        return QRect(bounds)

    def _frame_draw_rect(self) -> QRect:
        return QRect(0, 0, max(1, self.width()), max(1, self.height()))

    def screen_available(self, *_args):
        return self.screen()

    @property
    def anim(self) -> str | None:
        if not self._clip:
            return None
        return str(self._clip.get("name") or "") or None

    @property
    def idles(self) -> list[str]:
        fn = self._hooks.get("idle_names")
        return list(fn() or []) if callable(fn) else []

    @property
    def turns(self) -> list[str]:
        fn = self._hooks.get("turn_names")
        return list(fn() or []) if callable(fn) else []

    def _switch(self, name: str) -> None:
        fn = self._hooks.get("switch_clip")
        if callable(fn) and name:
            fn(name)

    def _pick(self, pool) -> str | None:
        entries = list(pool or [])
        return entries[0] if entries else None

    def _cancel_move(self) -> None:
        fn = self._hooks.get("cancel_walk")
        if callable(fn):
            fn()

    def show_clip(self, clip: dict[str, Any] | None) -> None:
        if not clip:
            return
        if self._clip and clip.get("play_id") == self._clip.get("play_id"):
            return
        self._clip = clip
        self._mask_bounds = None
        self._frame_key = None
        path = str(clip.get("path") or "")
        if not path:
            return
        self._player.play(path)
        self._sync_throttle()

    def set_scale(self, scale: float) -> None:
        self._scale = max(0.45, min(1.15, float(scale)))
        self.setFixedSize(*self._size())
        if self._source is not None:
            self._present(self._source)
        else:
            self.update()

    def set_on_top(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(enabled))
        self.show()
        self.setFixedSize(*self._size())
        self._arm_no_activate()

    def set_force_through(self, enabled: bool) -> None:
        self._force_through = bool(enabled)
        self._through = None
        self._refresh_hit()

    def shutdown(self) -> None:
        self._hit_timer.stop()
        self.probe.cancel(restore=False)
        self._player.shutdown()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._arm_no_activate()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._source is not None:
            self._present(self._source)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._opaque:
            painter.fillRect(self.rect(), QColor(16, 20, 28))
        if self._pixmap is None or self._pixmap.isNull():
            return
        rect = self._frame_draw_rect()
        angle = self.probe.current_angle_deg()
        if abs(angle) > 1e-6:
            painter.translate(rect.center())
            painter.rotate(angle)
            painter.translate(-rect.center())
        painter.drawPixmap(self.rect(), self._pixmap)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self._transparent_at(event.position().toPoint()):
            return
        self._mark_activity()
        self._press = event.globalPosition().toPoint()
        cx, cy = cursor_pos()
        wx, wy, _wr, _wb = window_rect(self._hwnd())
        self._grab_phys = (cx - wx, cy - wy)
        self._press_phys = (cx, cy)
        self._dragging = False
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        cx, cy = cursor_pos()
        if not self._dragging:
            if abs(cx - self._press_phys[0]) + abs(cy - self._press_phys[1]) < _DRAG_PX:
                return
            self._dragging = True
            self._mark_activity()
            hook = self._hooks.get("drag_start")
            if hook:
                hook()
        move_hwnd(self._hwnd(), cx - self._grab_phys[0], cy - self._grab_phys[1])
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        was_drag = self._dragging
        self._press = None
        self._dragging = False
        if was_drag:
            hook = self._hooks.get("drag_end")
            if hook:
                hook()
        else:
            hook = self._hooks.get("click")
            if hook:
                hook()
        self._sync_throttle()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        self._mark_activity()
        hook = self._hooks.get("scale")
        if hook:
            hook(0.08 if event.angleDelta().y() > 0 else -0.08)
        event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self._mark_activity()
        menu = QMenu(self)
        menu.addAction("戳一下", lambda: self._hooks.get("click") and self._hooks["click"]())
        menu.addAction("缩小", lambda: self._hooks.get("scale") and self._hooks["scale"](-0.08))
        menu.addAction("放大", lambda: self._hooks.get("scale") and self._hooks["scale"](0.08))
        menu.addAction("边缘探头 开/关", lambda: self._hooks.get("toggle_edge") and self._hooks["toggle_edge"]())
        menu.addAction("复位", lambda: self._hooks.get("restore") and self._hooks["restore"]())
        menu.addAction("唤出实验室", lambda: self._hooks.get("show_lab") and self._hooks["show_lab"]())
        menu.exec(event.globalPos())
        self._mark_activity()

    def _on_frame(self, image: QImage) -> None:
        if image is None or image.isNull():
            return
        self._present(image)
        self._sync_throttle()
        if self._clip and self._clip.get("want_walk") and not self.probe.active:
            tick = self._hooks.get("walk_tick")
            if tick:
                tick(self._player.elapsed)

    def _on_meta(self, duration: float) -> None:
        if self._clip and self._clip.get("want_walk") and not self.probe.active:
            begin = self._hooks.get("begin_walk")
            if begin:
                begin(float(duration or 0))

    def _on_finished(self) -> None:
        hook = self._hooks.get("ended")
        if hook:
            hook()

    def _present(self, image: QImage) -> None:
        """Premultiply + DPR scale, then cache a Qt alpha mask (dsh-pet rebuild)."""
        self._source = image
        scr = self.screen()
        dpr = float(scr.devicePixelRatio()) if scr is not None else 1.0
        dpr = dpr if dpr > 0 else 1.0
        phys_w = max(1, int(round(self.width() * dpr)))
        phys_h = max(1, int(round(self.height() * dpr)))
        key = (image.cacheKey(), phys_w, phys_h, round(dpr, 4))
        if key == self._frame_key and self._pixmap is not None:
            return
        img = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        if img.width() != phys_w or img.height() != phys_h:
            img = img.scaled(
                phys_w,
                phys_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        pixmap = QPixmap.fromImage(img)
        pixmap.setDevicePixelRatio(dpr)
        self._pixmap = pixmap
        self._hit = img
        self._frame_key = key
        self._sync_mask()
        self.update()

    def _sync_mask(self) -> None:
        # Qt C++ createAlphaMask; Python pixel scans are several times slower.
        img = self._hit
        if img is None or img.isNull():
            self._mask_bounds = QRect()
            return
        bounds = QRegion(QBitmap.fromImage(img.createAlphaMask())).boundingRect()
        if bounds.isEmpty():
            self._mask_bounds = QRect()
            return
        dpr = 1.0
        if self._pixmap is not None:
            dpr = float(self._pixmap.devicePixelRatio() or 1.0)
        if dpr <= 0:
            dpr = 1.0
        self._mask_bounds = QRect(
            int(bounds.x() / dpr),
            int(bounds.y() / dpr),
            max(1, int(round(bounds.width() / dpr))),
            max(1, int(round(bounds.height() / dpr))),
        )

    def _mark_activity(self) -> None:
        self._active_at = time.monotonic()
        self._player.set_decode_throttle(1)

    def _sync_throttle(self) -> None:
        walking = bool(self._clip and self._clip.get("want_walk"))
        busy = self._press is not None or self._dragging or walking
        idle = (not busy) and (time.monotonic() - self._active_at >= IDLE_LOW_FPS_THRESHOLD)
        self._player.set_decode_throttle(IDLE_LOW_FPS_DIVISOR if idle else 1)

    def _size(self) -> tuple[int, int]:
        s = self._scale
        return max(160, int(round(CANVAS_W * s))), max(90, int(round(CANVAS_H * s)))

    def _arm_no_activate(self) -> None:
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        set_no_activate(hwnd)

    def _hwnd(self) -> int:
        try:
            return int(self.winId())
        except Exception:
            return 0

    def _transparent_at(self, local: QPoint) -> bool:
        img = self._hit
        if img is None or img.isNull() or self.width() <= 0 or self.height() <= 0:
            return not self._opaque
        angle = self.probe.current_angle_deg()
        if abs(angle) > 1e-6:
            mapped = unrotate_point(QPointF(local), self._frame_draw_rect(), angle)
            local = QPoint(int(round(mapped.x())), int(round(mapped.y())))
        dpr = 1.0
        if self._pixmap is not None:
            dpr = float(self._pixmap.devicePixelRatio() or 1.0)
        px = int(round(local.x() * dpr))
        py = int(round(local.y() * dpr))
        if px < 0 or py < 0 or px >= img.width() or py >= img.height():
            return True
        return img.pixelColor(px, py).alpha() < _HIT_ALPHA

    def _refresh_hit(self) -> None:
        hwnd = self._hwnd()
        if not hwnd:
            return
        if self._force_through:
            want = True
        elif self._press is not None:
            want = False
        else:
            gx, gy = cursor_pos()
            local = self.mapFromGlobal(QPoint(gx, gy))
            if not self.rect().contains(local):
                want = False
            else:
                want = self._transparent_at(local)
        if want == self._through:
            return
        self._through = want
        set_click_through(hwnd, want)
        set_no_activate(hwnd)
