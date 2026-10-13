"""stdlib: python -m unittest test_edge"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QObject, QRect
from PySide6.QtWidgets import QApplication

from edge_probe import (
    EDGE_ENGAGE_EXPOSURE,
    EDGE_ENTER_MS,
    EDGE_IDLE_SECONDS,
    EDGE_PEEK_EXPOSURE,
    EDGE_PROBE_ANGLE,
    EDGE_RETURN_MS,
    EDGE_STRAIGHTEN_MS,
    PEEKING,
    STRAIGHTENED,
    EdgeProbeController,
    edge_side_at_rest,
    probe_window_x,
    rotated_region_bounds,
)


def _qapp():
    return QApplication.instance() or QApplication([])


class Avail:
    def availableGeometry(self):
        return QRect(0, 0, 1000, 800)


class FakeWin(QObject):
    def __init__(self):
        super().__init__()
        self._x = 0
        self._y = 100
        self._w = 400
        self._h = 300
        self.anim = "drag"
        self.idles = ["idle"]
        self.turns = ["turn"]
        self.switched = []

    def frameGeometry(self):
        return QRect(self._x, self._y, self._w, self._h)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def move(self, x, y):
        self._x = int(x)
        self._y = int(y)

    def update(self):
        return None

    def screen_available(self, *_args):
        return Avail()

    def character_local_region(self):
        return QRect(100, 0, 200, 200)

    def _frame_draw_rect(self):
        return QRect(0, 0, self._w, self._h)

    def _switch(self, name):
        self.switched.append(name)
        self.anim = name
        return True

    def _pick(self, pool):
        return pool[0]

    def _cancel_move(self):
        return None


class GeometryTests(unittest.TestCase):
    def test_probe_window_x_left_and_right(self) -> None:
        local = QRect(100, 0, 200, 200)
        avail = QRect(0, 0, 1000, 800)
        self.assertEqual(probe_window_x("left", EDGE_PEEK_EXPOSURE, local, avail), -190)
        self.assertEqual(probe_window_x("left", EDGE_ENGAGE_EXPOSURE, local, avail), -136)
        self.assertEqual(probe_window_x("right", EDGE_PEEK_EXPOSURE, local, avail), 790)

    def test_edge_side_requires_sprite_on_the_edge(self) -> None:
        win = FakeWin()
        avail = Avail().availableGeometry()
        win.move(-100, 100)
        self.assertEqual(edge_side_at_rest(win, avail), "left")
        win.move(700, 100)
        self.assertEqual(edge_side_at_rest(win, avail), "right")
        win.move(0, 100)
        self.assertIsNone(edge_side_at_rest(win, avail))

    def test_padding_is_not_the_edge(self) -> None:
        win = FakeWin()
        avail = Avail().availableGeometry()
        win.move(12, 80)
        self.assertIsNone(edge_side_at_rest(win, avail))

    def test_rotated_identity(self) -> None:
        region = QRect(10, 20, 30, 40)
        self.assertEqual(rotated_region_bounds(region, QRect(0, 0, 100, 100), 0), region)


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _qapp()

    def _controller(self):
        times = [0.0]

        def clock():
            return times[0]

        ctrl = EdgeProbeController(FakeWin(), clock=clock)
        ctrl.enabled = True
        return ctrl, times

    def test_release_at_left_edge_enters_peek_pose(self) -> None:
        ctrl, times = self._controller()
        ctrl.win.move(-100, 100)
        ctrl.win.anim = "drag"
        ctrl.on_release(was_dragging=True)
        self.assertTrue(ctrl.active)
        self.assertEqual(ctrl.side, "left")
        self.assertEqual(ctrl.win.anim, "idle")
        times[0] += EDGE_ENTER_MS / 1000.0
        ctrl._on_timer()
        self.assertEqual(ctrl.mode, PEEKING)
        self.assertEqual(ctrl.win.x(), -220)
        self.assertEqual(ctrl.current_angle_deg(), EDGE_PROBE_ANGLE)
        self.assertAlmostEqual(ctrl.current_exposure(), EDGE_PEEK_EXPOSURE)
        ctrl.cancel(restore=True)

    def test_release_at_right_edge_enters_peek_pose(self) -> None:
        ctrl, times = self._controller()
        ctrl.win.move(700, 100)
        ctrl.win.anim = "idle"
        ctrl.on_release(was_dragging=True)
        self.assertTrue(ctrl.active)
        self.assertEqual(ctrl.side, "right")
        times[0] += EDGE_ENTER_MS / 1000.0
        ctrl._on_timer()
        self.assertEqual(ctrl.mode, PEEKING)
        self.assertEqual(ctrl.win.x(), 821)
        self.assertEqual(ctrl.current_angle_deg(), -EDGE_PROBE_ANGLE)
        self.assertAlmostEqual(ctrl.current_exposure(), EDGE_PEEK_EXPOSURE)
        ctrl.cancel(restore=True)

    def test_click_straightens_then_returns_after_idle(self) -> None:
        ctrl, times = self._controller()
        ctrl.win.move(-100, 100)
        ctrl.win.anim = "idle"
        ctrl.on_release(was_dragging=True)
        times[0] += EDGE_ENTER_MS / 1000.0
        ctrl._on_timer()
        ctrl.on_clicked()
        self.assertEqual(ctrl.mode, "STRAIGHTENING")
        times[0] += EDGE_STRAIGHTEN_MS / 1000.0
        ctrl._on_timer()
        self.assertEqual(ctrl.mode, STRAIGHTENED)
        self.assertEqual(ctrl.current_angle_deg(), 0.0)
        self.assertAlmostEqual(ctrl.current_exposure(), EDGE_ENGAGE_EXPOSURE)
        self.assertAlmostEqual(ctrl._idle_remaining, EDGE_IDLE_SECONDS)
        self.assertEqual(ctrl.win.x(), -136)
        times[0] += EDGE_IDLE_SECONDS + 0.1
        ctrl._on_timer()
        self.assertEqual(ctrl.mode, "RETURNING")
        times[0] += EDGE_RETURN_MS / 1000.0
        ctrl._on_timer()
        self.assertEqual(ctrl.mode, PEEKING)
        self.assertEqual(ctrl.current_angle_deg(), EDGE_PROBE_ANGLE)
        ctrl.cancel(restore=True)

    def test_drag_away_cancels_without_snap_back(self) -> None:
        ctrl, times = self._controller()
        ctrl.win.move(-100, 100)
        ctrl.win.anim = "idle"
        ctrl.on_release(was_dragging=True)
        times[0] += EDGE_ENTER_MS / 1000.0
        ctrl._on_timer()
        self.assertEqual(ctrl.win.x(), -220)
        ctrl.on_drag_started()
        self.assertFalse(ctrl.active)
        self.assertEqual(ctrl.win.x(), -220)
        ctrl.cancel(restore=True)

    def test_feature_off_cancels_and_restores_position(self) -> None:
        ctrl, times = self._controller()
        ctrl.win.move(-100, 100)
        ctrl.win.anim = "idle"
        ctrl.on_release(was_dragging=True)
        times[0] += EDGE_ENTER_MS / 1000.0
        ctrl._on_timer()
        self.assertEqual(ctrl.win.x(), -220)
        ctrl.set_enabled(False)
        self.assertFalse(ctrl.active)
        self.assertEqual(ctrl.win.x(), -100)

    def test_hidden_pause_freezes_countdown(self) -> None:
        ctrl, times = self._controller()
        ctrl.win.move(-100, 100)
        ctrl.win.anim = "idle"
        ctrl.on_release(was_dragging=True)
        times[0] += EDGE_ENTER_MS / 1000.0
        ctrl._on_timer()
        ctrl.on_clicked()
        times[0] += EDGE_STRAIGHTEN_MS / 1000.0
        ctrl._on_timer()
        self.assertEqual(ctrl.mode, STRAIGHTENED)
        remaining = ctrl._idle_remaining
        ctrl.pause()
        times[0] += 10.0
        ctrl._on_timer()
        self.assertEqual(ctrl.mode, STRAIGHTENED)
        self.assertAlmostEqual(ctrl._idle_remaining, remaining)
        ctrl.resume()
        self.assertTrue(ctrl.active)
        ctrl.cancel(restore=True)


if __name__ == "__main__":
    unittest.main()
