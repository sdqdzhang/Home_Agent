"""stdlib: python -m unittest test_player"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from catalog import Catalog
from mapper import map_mind_state
from player import Player
from test_catalog import _touch


class PlayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        _touch(root / "idle" / "待机呼吸休闲.webm")
        _touch(root / "turn" / "东张西望.webm")
        _touch(root / "move" / "螃蟹走路.webm")
        _touch(root / "click" / "点击回应-开心跃动.webm")
        _touch(root / "drag" / "被鼠标拖拽悬空反馈.webm")
        _touch(root / "random" / "写代码.webm")
        _touch(root / "random" / "吃Token.webm")
        _touch(root / "random" / "被吓一跳.webm")
        self.player = Player(Catalog(root))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_start_idle(self) -> None:
        clip = self.player.start()
        self.assertEqual(clip["name"], "待机呼吸休闲")
        self.assertEqual(clip["kind"], "idle")
        self.assertEqual(self.player.play_id, 1)

    def test_poke_interrupts(self) -> None:
        self.player.start()
        clip = self.player.poke()
        self.assertEqual(clip["kind"], "click")
        self.assertEqual(clip["name"], "点击回应-开心跃动")

    def test_link_does_not_interrupt_oneshot(self) -> None:
        self.player.start()
        self.player.poke()
        intent = map_mind_state({"work_mode": "executing"})
        self.assertIsNone(self.player.apply_intent(intent))
        self.assertEqual(self.player.pending_link, "写代码")
        nxt = self.player.on_ended()
        self.assertEqual(nxt["name"], "写代码")

    def test_idle_apply_does_not_restart(self) -> None:
        self.player.start()
        self.assertIsNone(self.player.apply_intent(map_mind_state()))
        self.assertEqual(self.player.clip.name, "待机呼吸休闲")

    def test_drag_then_idle(self) -> None:
        self.player.start()
        clip = self.player.drag_start()
        self.assertEqual(clip["kind"], "drag")
        back = self.player.drag_end()
        self.assertEqual(back["name"], "待机呼吸休闲")

    def test_preview_pins_until_unpin(self) -> None:
        self.player.start()
        clip = self.player.preview("写代码")
        self.assertEqual(clip["name"], "写代码")
        self.assertEqual(self.player.pinned, "写代码")
        again = self.player.on_ended()
        self.assertEqual(again["name"], "写代码")
        self.player.apply_intent(map_mind_state({"work_mode": "executing"}))
        self.assertEqual(self.player.clip.name, "写代码")
        freed = self.player.unpin()
        self.assertIsNone(self.player.pinned)
        self.assertIsNotNone(freed)

    def test_preview_unknown_is_none(self) -> None:
        self.assertIsNone(self.player.preview("没有这个动作"))

    def test_chain_move_sets_walk(self) -> None:
        self.player.start()
        with mock.patch("wander.roll_next", return_value="螃蟹走路"):
            clip = self.player.chain()
        self.assertEqual(clip["name"], "螃蟹走路")
        self.assertTrue(clip["want_walk"])

    def test_flinch_queues_during_act(self) -> None:
        self.player.start()
        self.player.apply_intent(map_mind_state({"work_mode": "executing"}))
        self.assertEqual(self.player.clip.name, "写代码")
        self.player.apply_intent(map_mind_state({"work_mode": "executing", "recent_events": [{"type": "tool_failure"}]}))
        self.assertEqual(self.player.pending_link, "被吓一跳")
        self.assertEqual(self.player.clip.name, "写代码")


if __name__ == "__main__":
    unittest.main()
