"""stdlib: python -m unittest test_catalog"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from catalog import build_categories, pick_from_pool, roll_next, scan


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"webm")


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _touch(self.root / "idle" / "待机呼吸休闲.webm")
        _touch(self.root / "turn" / "东张西望.webm")
        _touch(self.root / "move" / "螃蟹走路.webm")
        _touch(self.root / "move" / "原地踏步.webm")
        _touch(self.root / "click" / "点击回应-开心跃动.webm")
        _touch(self.root / "drag" / "被鼠标拖拽悬空反馈.webm")
        _touch(self.root / "random" / "写代码.webm")
        _touch(self.root / "events" / "balance" / "余额-钱袋满溢.webm")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_scan_folders(self) -> None:
        data = scan(self.root)
        cats = data["categories"]
        self.assertEqual(cats["idle"], "待机呼吸休闲")
        self.assertEqual(cats["turn"], "东张西望")
        self.assertEqual(cats["drag"], "被鼠标拖拽悬空反馈")
        self.assertIn("螃蟹走路", cats["moves"])
        self.assertNotIn("原地踏步", cats["moves"])
        self.assertIn("原地踏步", cats["acts"])
        self.assertIn("写代码", cats["acts"])
        self.assertIn("余额-钱袋满溢", cats["acts"])
        self.assertEqual(cats["clicks"], ["点击回应-开心跃动"])

    def test_list_groups(self) -> None:
        from catalog import Catalog

        groups = Catalog(self.root).list_groups()
        ids = [g["id"] for g in groups]
        self.assertEqual(ids[:7], ["idle", "turn", "move", "click", "drag", "random", "events"])
        events = next(g for g in groups if g["id"] == "events")
        self.assertEqual(events["label"], "事件")
        self.assertEqual(events["clips"][0]["name"], "余额-钱袋满溢")

    def test_themed_groups(self) -> None:
        from catalog import Catalog

        cat = Catalog(self.root)
        self.assertEqual(cat.theme_of("写代码"), "work")
        self.assertEqual(cat.theme_of("余额-钱袋满溢"), "event")
        self.assertEqual(cat.theme_of("待机呼吸休闲"), "idle")
        ids = [g["id"] for g in cat.list_themed_groups()]
        self.assertIn("work", ids)
        self.assertIn("event", ids)
        path = Catalog(self.root).file_path("写代码")
        self.assertEqual(path, self.root / "random" / "写代码.webm")

    def test_build_empty(self) -> None:
        cats = build_categories({})
        self.assertIsNone(cats["idle"])
        self.assertEqual(cats["acts"], [])

    def test_roll_idle_branch(self) -> None:
        pools = {
            "idles": ["待机"],
            "turns": ["转向"],
            "acts": ["写代码"],
            "moves": ["走路"],
        }
        with mock.patch("catalog.random.random", return_value=0.1):
            self.assertEqual(roll_next(pools), "待机")
        with mock.patch("catalog.random.random", return_value=0.25):
            self.assertEqual(roll_next(pools), "转向")
        with mock.patch("catalog.random.random", return_value=0.5):
            self.assertEqual(roll_next(pools), "写代码")
        with mock.patch("catalog.random.random", return_value=0.9):
            self.assertEqual(roll_next(pools), "走路")

    def test_pick_exclude(self) -> None:
        self.assertEqual(pick_from_pool(["a"], "a"), "a")
        self.assertIn(pick_from_pool(["a", "b"], "a"), ("b",))


if __name__ == "__main__":
    unittest.main()
