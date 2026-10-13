"""stdlib 单测：python test_mapper.py"""

from __future__ import annotations

import unittest

from mapper import apply_event, map_mind_state


class MapperTests(unittest.TestCase):
    def test_default_is_idle_calm(self):
        intent = map_mind_state()
        self.assertEqual(intent.expression, "calm")
        self.assertEqual(intent.motion, "idle")
        self.assertEqual(intent.gaze, "user")
        self.assertEqual(intent.alert, "none")
        self.assertIsNone(intent.one_shot)

    def test_mood_and_work_mode(self):
        intent = map_mind_state(
            {
                "emotion": {"mood": "担忧", "intensity": 0.8},
                "work_mode": "executing",
                "interaction_mode": "task",
            }
        )
        self.assertEqual(intent.expression, "worried")
        self.assertGreaterEqual(intent.expression_weight, 0.8)
        self.assertEqual(intent.motion, "work")
        self.assertEqual(intent.gaze, "task")
        self.assertGreaterEqual(intent.motion_priority, 1)

    def test_alert_outranks_work(self):
        intent = map_mind_state({"work_mode": "executing", "alert": "approval"})
        self.assertEqual(intent.alert, "approval")
        self.assertEqual(intent.motion_priority, 4)

    def test_poke_event(self):
        state = apply_event({}, "playful_interaction")
        intent = map_mind_state(state)
        self.assertEqual(intent.one_shot, "poke")
        self.assertEqual(intent.motion_priority, 3)
        self.assertGreater(intent.closeness, 0.15)
        self.assertEqual(state["interaction_mode"], "playful")

    def test_idle_pool_unlocks_with_familiarity(self):
        low = map_mind_state({"relationship": {"familiarity": 0.05}})
        high = map_mind_state({"relationship": {"familiarity": 0.7}})
        self.assertEqual(low.idle_pool, ["idle_a"])
        self.assertIn("look_aside", high.idle_pool)

    def test_energy_from_load(self):
        tired = map_mind_state({"emotion": {"cognitive_load": 0.85, "focus": 0.4}})
        self.assertEqual(tired.energy, "low")


if __name__ == "__main__":
    unittest.main()
