"""Edge probe — same pose machine as dsh-pet (enter / peek / straighten / return).

Collision reentry is omitted; this sandbox has no throw physics.
"""

from __future__ import annotations

import math
import time
from typing import Any

from PySide6.QtCore import QEasingCurve, QPointF, QRect, QRectF, Qt, QTimer

EDGE_PROBE_ANGLE = 45.0
EDGE_PEEK_EXPOSURE = 0.55
EDGE_ENGAGE_EXPOSURE = 0.82
EDGE_ENTER_MS = 300
EDGE_STRAIGHTEN_MS = 250
EDGE_RETURN_MS = 300
EDGE_IDLE_SECONDS = 5.0

OFF = "OFF"
ENTERING = "ENTERING"
PEEKING = "PEEKING"
STRAIGHTENING = "STRAIGHTENING"
STRAIGHTENED = "STRAIGHTENED"
RETURNING = "RETURNING"

_TRANSITION_MODES = {ENTERING, STRAIGHTENING, RETURNING}


def eased_progress(
    elapsed_ms: float,
    duration_ms: float,
    curve: QEasingCurve = QEasingCurve.Type.OutCubic,
) -> float:
    if duration_ms <= 0:
        return 1.0
    raw = max(0.0, min(1.0, float(elapsed_ms) / float(duration_ms)))
    easing = QEasingCurve(curve)
    return float(easing.valueForProgress(raw))


def rotated_region_bounds(region: QRect, pivot_rect: QRect, angle_deg: float) -> QRect:
    angle = float(angle_deg)
    if abs(angle) < 1e-6:
        return QRect(region)
    center = QPointF(pivot_rect.center())
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    corners = (
        QPointF(region.left(), region.top()),
        QPointF(region.left() + region.width(), region.top()),
        QPointF(region.left(), region.top() + region.height()),
        QPointF(region.left() + region.width(), region.top() + region.height()),
    )
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for point in corners:
        dx = point.x() - center.x()
        dy = point.y() - center.y()
        rx = center.x() + dx * cos_a - dy * sin_a
        ry = center.y() + dx * sin_a + dy * cos_a
        min_x = min(min_x, rx)
        max_x = max(max_x, rx)
        min_y = min(min_y, ry)
        max_y = max(max_y, ry)
    return QRectF(min_x, min_y, max_x - min_x, max_y - min_y).toAlignedRect()


def unrotate_point(point: QPointF, rect: QRect, angle_deg: float) -> QPointF:
    angle = float(angle_deg)
    if abs(angle) < 1e-6:
        return QPointF(point)
    center = QPointF(rect.center())
    rad = math.radians(-angle)
    dx = point.x() - center.x()
    dy = point.y() - center.y()
    return QPointF(
        center.x() + dx * math.cos(rad) - dy * math.sin(rad),
        center.y() + dx * math.sin(rad) + dy * math.cos(rad),
    )


def probe_window_x(side: str, exposure: float, vis_local: QRect, avail: QRect) -> int:
    exposure = max(0.0, min(1.0, float(exposure)))
    offscreen = (1.0 - exposure) * vis_local.width()
    if side == "left":
        return int(round(avail.left() - offscreen - vis_local.left()))
    if side == "right":
        return int(round(avail.right() + offscreen - vis_local.right()))
    raise ValueError(f"unknown edge side: {side!r}")


def edge_side_at_rest(win, avail: QRect) -> str | None:
    local = win.character_local_region()
    if local is None or local.isEmpty():
        return None
    frame = win.frameGeometry()
    left = frame.left() + local.left()
    right = frame.left() + local.right()
    if left <= avail.left():
        return "left"
    if right >= avail.right():
        return "right"
    return None


class EdgeProbeController:
    def __init__(self, win: Any, *, clock=None) -> None:
        self.win = win
        self._clock = clock if callable(clock) else time.monotonic
        self.enabled = True
        self._mode = OFF
        self._side: str | None = None
        self._angle_deg = 0.0
        self._exposure = 1.0
        self._vis_local: QRect | None = None
        self._restore_x: int | None = None
        self._idle_remaining = 0.0
        self._last_tick_time = 0.0
        self._transition_start = 0.0
        self._transition_duration_ms = 0
        self._transition_from_angle = 0.0
        self._transition_to_angle = 0.0
        self._transition_from_exposure = 1.0
        self._transition_to_exposure = 1.0
        self._hidden = False
        self._paused_at = 0.0
        self._timer = QTimer(win)
        self._timer.setInterval(16)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._on_timer)

    @property
    def active(self) -> bool:
        return self._mode != OFF

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def side(self) -> str | None:
        return self._side

    @property
    def ui_mode(self) -> str:
        if self._mode == OFF:
            return "off"
        if self._mode in {STRAIGHTENED, STRAIGHTENING}:
            return "out"
        return "peek"

    def current_angle_deg(self) -> float:
        return self._angle_deg if self.active else 0.0

    def current_exposure(self) -> float:
        return self._exposure if self.active else 1.0

    def set_enabled(self, on: bool) -> None:
        on = bool(on)
        if on == self.enabled:
            return
        self.enabled = on
        if not on:
            self.cancel("feature_off", restore=True)

    def on_release(self, was_dragging: bool) -> None:
        if not self.enabled or self._hidden:
            return
        if was_dragging:
            if self.active:
                self.cancel("drag_away", restore=False)
            self._maybe_enter()

    def on_drag_started(self) -> None:
        if self.active and self.enabled and not self._hidden:
            self.cancel("drag_away", restore=False)

    def on_clicked(self) -> None:
        if not self.active or self._hidden:
            return
        if self._mode == PEEKING:
            self._begin_transition(
                STRAIGHTENING,
                EDGE_STRAIGHTEN_MS,
                to_angle=0.0,
                to_exposure=EDGE_ENGAGE_EXPOSURE,
            )
        elif self._mode == STRAIGHTENED:
            self._idle_remaining = EDGE_IDLE_SECONDS
        elif self._mode == RETURNING:
            self._begin_transition(
                STRAIGHTENING,
                EDGE_STRAIGHTEN_MS,
                to_angle=0.0,
                to_exposure=EDGE_ENGAGE_EXPOSURE,
            )

    def consume_click(self) -> bool:
        if not self.active:
            return False
        self.on_clicked()
        return True

    def maybe_enter(self) -> None:
        self.on_release(was_dragging=True)

    def cancel(self, reason: str = "", restore: bool = False) -> None:
        was_active = self.active
        self._mode = OFF
        self._side = None
        self._angle_deg = 0.0
        self._exposure = 1.0
        self._idle_remaining = 0.0
        self._timer.stop()
        restore_x = self._restore_x
        self._restore_x = None
        self._vis_local = None
        if was_active and restore and restore_x is not None:
            try:
                self.win.move(restore_x, self.win.y())
            except Exception:
                pass
        if was_active:
            try:
                self.win.update()
            except Exception:
                pass

    def pause(self) -> None:
        if self._hidden:
            return
        self._hidden = True
        if self._timer.isActive():
            self._timer.stop()
        self._paused_at = self._clock()

    def resume(self) -> None:
        if not self._hidden:
            return
        self._hidden = False
        if not self.active:
            return
        now = self._clock()
        if self._mode in _TRANSITION_MODES:
            elapsed_at_pause = max(0.0, self._paused_at - self._transition_start)
            self._transition_start = now - elapsed_at_pause
        self._last_tick_time = now
        if self._mode in _TRANSITION_MODES or self._mode == STRAIGHTENED:
            self._timer.start()

    def _maybe_enter(self) -> None:
        if not self.enabled or self._hidden or self.active:
            return
        scr = self.win.screen_available()
        avail = scr.availableGeometry() if scr is not None else None
        if avail is None:
            return
        side = edge_side_at_rest(self.win, avail)
        if side is None:
            return
        self._side = side
        self._vis_local = QRect(self.win.character_local_region())
        self._restore_x = self.win.x()
        anim = getattr(self.win, "anim", None)
        idles = list(getattr(self.win, "idles", ()) or ())
        turns = list(getattr(self.win, "turns", ()) or ())
        if anim not in idles and anim not in turns:
            switch = getattr(self.win, "_switch", None)
            pick = getattr(self.win, "_pick", None)
            if callable(switch) and callable(pick) and idles:
                switch(pick(idles))
        cancel_move = getattr(self.win, "_cancel_move", None)
        if callable(cancel_move):
            cancel_move()
        sign = 1.0 if side == "left" else -1.0
        self._begin_transition(
            ENTERING,
            EDGE_ENTER_MS,
            to_angle=sign * EDGE_PROBE_ANGLE,
            to_exposure=EDGE_PEEK_EXPOSURE,
        )

    def _begin_transition(
        self,
        mode: str,
        duration_ms: int,
        *,
        to_angle: float,
        to_exposure: float,
    ) -> None:
        now = self._clock()
        self._mode = mode
        self._transition_duration_ms = duration_ms
        self._transition_start = now
        self._last_tick_time = now
        self._transition_from_angle = self._angle_deg
        self._transition_to_angle = float(to_angle)
        self._transition_from_exposure = self._exposure
        self._transition_to_exposure = float(to_exposure)
        self._timer.start()

    def _on_timer(self) -> None:
        if self._hidden:
            return
        now = self._clock()
        if self._mode in _TRANSITION_MODES:
            self._tick_transition(now)
        elif self._mode == STRAIGHTENED:
            dt = max(0.0, now - self._last_tick_time)
            self._last_tick_time = now
            self._idle_remaining = max(0.0, self._idle_remaining - dt)
            if self._idle_remaining <= 0.0:
                self._begin_return()

    def _tick_transition(self, now: float) -> None:
        elapsed_ms = max(0.0, (now - self._transition_start) * 1000.0)
        progress = eased_progress(elapsed_ms, self._transition_duration_ms)
        done = progress >= 1.0
        self._angle_deg = (
            self._transition_from_angle
            + (self._transition_to_angle - self._transition_from_angle) * progress
        )
        self._exposure = (
            self._transition_from_exposure
            + (self._transition_to_exposure - self._transition_from_exposure) * progress
        )
        self._apply_pose()
        if not done:
            return
        if self._mode == ENTERING:
            self._mode = PEEKING
            self._timer.stop()
        elif self._mode == STRAIGHTENING:
            self._mode = STRAIGHTENED
            self._idle_remaining = EDGE_IDLE_SECONDS
            self._last_tick_time = now
            self._timer.start()
        elif self._mode == RETURNING:
            self._mode = PEEKING
            self._timer.stop()

    def _begin_return(self) -> None:
        sign = 1.0 if self._side == "left" else -1.0
        self._begin_transition(
            RETURNING,
            EDGE_RETURN_MS,
            to_angle=sign * EDGE_PROBE_ANGLE,
            to_exposure=EDGE_PEEK_EXPOSURE,
        )

    def _apply_pose(self) -> None:
        if self._side is None or self._vis_local is None:
            return
        scr = self.win.screen_available()
        avail = scr.availableGeometry() if scr is not None else None
        if avail is None:
            return
        frame_fn = getattr(self.win, "_frame_draw_rect", None)
        pivot = frame_fn() if callable(frame_fn) else QRect(
            0, 0, int(getattr(self.win, "width", lambda: 0)()), int(getattr(self.win, "height", lambda: 0)())
        )
        bounds = rotated_region_bounds(self._vis_local, pivot, self._angle_deg)
        x = probe_window_x(self._side, self._exposure, bounds, avail)
        if x != self.win.x():
            self.win.move(x, self.win.y())
        try:
            self.win.update()
        except Exception:
            pass
