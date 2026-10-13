"""stdlib: python -m unittest test_wander"""

from __future__ import annotations

import unittest
from unittest import mock

from wander import choose_facing, pick_move_clip, plan_walk


class WanderTests(unittest.TestCase):
    def test_turns_away_from_near_wall(self) -> None:
        room = {"cx": 80, "left": 0, "right": 1920, "margin": 28}
        self.assertEqual(choose_facing("left", room), "right")
        room = {"cx": 1840, "left": 0, "right": 1920, "margin": 28}
        self.assertEqual(choose_facing("right", room), "left")

    def test_picks_left_run_clip(self) -> None:
        with mock.patch("wander.random.choice", side_effect=lambda xs: xs[0]):
            name = pick_move_clip(["螃蟹走路", "左转奔跑", "漂浮踏步"], "left")
        self.assertEqual(name, "左转奔跑")

    def test_plan_walk_stays_in_room(self) -> None:
        planned = plan_walk(
            wx=800,
            wy=400,
            width=460,
            height=260,
            facing="right",
            left=0,
            top=0,
            right=1920,
            bottom=1080,
        )
        self.assertIsNotNone(planned)
        assert planned is not None
        self.assertGreaterEqual(planned["target_x"], 28)
        self.assertLessEqual(planned["target_x"] + 460, 1920 - 28)


if __name__ == "__main__":
    unittest.main()
