"""stdlib: python -m unittest test_webm_player"""

from __future__ import annotations

import queue
import unittest

from catalog import FRAME_MS
from webm_player import stamp_source_indices, timer_interval_ms


class _FlakyQueue:
    """Every ``drop_every``-th put raises ``queue.Full`` (dropped frame)."""

    def __init__(self, drop_every: int) -> None:
        self._drop_every = drop_every
        self._puts = 0
        self.items: list = []

    def put(self, item, timeout=0):
        self._puts += 1
        if self._drop_every > 0 and self._puts % self._drop_every == 0:
            raise queue.Full
        self.items.append(item)


class StampTests(unittest.TestCase):
    def test_drops_keep_source_timeline(self) -> None:
        q = _FlakyQueue(drop_every=2)
        stamp_source_indices(
            iter([b"f0", b"f1", b"f2", b"f3", b"f4", b"f5"]),
            q,
            lambda: False,
        )
        self.assertEqual([item[0] for item in q.items], [b"f0", b"f2", b"f4"])
        self.assertEqual([item[1] for item in q.items], [0, 2, 4])

    def test_stops_before_enqueue(self) -> None:
        q = _FlakyQueue(drop_every=0)
        produced = {"n": 0}

        def frames():
            for i in range(20):
                produced["n"] += 1
                yield b"f%d" % i

        def is_stopped():
            return produced["n"] >= 3

        stamp_source_indices(frames(), q, is_stopped)
        self.assertEqual([item[1] for item in q.items], [0, 1])

    def test_throttle_retries_same_frame(self) -> None:
        attempts = {"n": 0}

        class _FullThenRoom:
            def __init__(self) -> None:
                self.items: list = []

            def put(self, item, timeout=0):
                attempts["n"] += 1
                if attempts["n"] < 3:
                    raise queue.Full
                self.items.append(item)

        q = _FullThenRoom()
        stamp_source_indices(
            iter([b"f0", b"f1"]),
            q,
            lambda: False,
            throttled=lambda: True,
        )
        self.assertEqual([item[0] for item in q.items], [b"f0", b"f1"])
        self.assertEqual([item[1] for item in q.items], [0, 1])
        self.assertEqual(attempts["n"], 4)

    def test_throttle_exits_while_full(self) -> None:
        class _AlwaysFull:
            def put(self, item, timeout=0):
                raise queue.Full

        checks = {"n": 0}

        def is_stopped():
            checks["n"] += 1
            return checks["n"] >= 3

        stamp_source_indices(iter([b"f0"]), _AlwaysFull(), is_stopped, throttled=lambda: True)
        self.assertGreaterEqual(checks["n"], 3)

    def test_unthrottled_still_drops(self) -> None:
        q = _FlakyQueue(drop_every=2)
        stamp_source_indices(
            iter([b"f0", b"f1", b"f2", b"f3"]),
            q,
            lambda: False,
            throttled=lambda: False,
        )
        self.assertEqual([item[1] for item in q.items], [0, 2])


class TimerIntervalTests(unittest.TestCase):
    def test_24fps_is_42ms(self) -> None:
        self.assertEqual(timer_interval_ms(24.0), 42)

    def test_throttle_doubles_interval(self) -> None:
        self.assertEqual(timer_interval_ms(24.0, throttle=2), 84)

    def test_missing_fps_uses_fallback(self) -> None:
        self.assertEqual(timer_interval_ms(0.0), FRAME_MS)


class ElapsedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_elapsed_follows_source_index_not_consume_count(self) -> None:
        from webm_player import WebmPlayer

        player = WebmPlayer()
        player._fps = 24.0
        player._src_idx = 12
        player._consumed = 3
        self.assertAlmostEqual(player.elapsed, 0.5)


if __name__ == "__main__":
    unittest.main()
