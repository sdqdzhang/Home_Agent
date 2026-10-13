"""stdlib: python -m unittest test_director"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from catalog import Catalog
from director import link_clip, next_busy, oneshot_name
from mapper import map_mind_state
from test_catalog import _touch


class DirectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        _touch(root / "idle" / "待机呼吸休闲.webm")
        _touch(root / "turn" / "东张西望.webm")
        _touch(root / "click" / "点击回应-开心跃动.webm")
        _touch(root / "random" / "写代码.webm")
        _touch(root / "random" / "吃Token.webm")
        _touch(root / "random" / "轻快记录.webm")
        _touch(root / "random" / "深度思考碎碎念.webm")
        _touch(root / "random" / "工作状态-清点归档.webm")
        _touch(root / "random" / "被吓一跳.webm")
        _touch(root / "random" / "工作状态-雀跃庆祝.webm")
        _touch(root / "random" / "工作状态-垂头叹气冒汗.webm")
        self.cat = Catalog(root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_busy_rotation(self) -> None:
        self.assertEqual(next_busy(self.cat, 1), "写代码")
        self.assertEqual(next_busy(self.cat, 2), "吃Token")
        self.assertEqual(next_busy(self.cat, 3), "轻快记录")
        self.assertEqual(next_busy(self.cat, 4), "吃Token")
        self.assertEqual(next_busy(self.cat, 5), "写代码")

    def test_oneshots(self) -> None:
        self.assertEqual(oneshot_name("poke", self.cat), "点击回应-开心跃动")
        self.assertEqual(oneshot_name("flinch", self.cat), "被吓一跳")
        self.assertEqual(oneshot_name("nod", self.cat), "工作状态-雀跃庆祝")

    def test_link_work_think_wrap(self) -> None:
        work = map_mind_state({"work_mode": "executing"})
        self.assertEqual(link_clip(work, self.cat, 1), "写代码")
        think = map_mind_state({"work_mode": "deep_tech"})
        self.assertEqual(link_clip(think, self.cat, 1), "深度思考碎碎念")
        wrap = map_mind_state({"work_mode": "wrapping_up"})
        self.assertEqual(link_clip(wrap, self.cat, 1), "工作状态-清点归档")
        idle = map_mind_state()
        self.assertIsNone(link_clip(idle, self.cat, 1))

    def test_alert_and_aside(self) -> None:
        alert = map_mind_state({"alert": "approval"})
        self.assertEqual(link_clip(alert, self.cat, 1), "工作状态-垂头叹气冒汗")
        aside = map_mind_state({"interaction_mode": "exploratory"})
        self.assertEqual(link_clip(aside, self.cat, 1), "东张西望")


if __name__ == "__main__":
    unittest.main()
