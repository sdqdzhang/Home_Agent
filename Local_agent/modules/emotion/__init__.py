"""心智与状态（Mind）模块 — 人格行为上下文 / 情绪连续性（非 LLM tool）。"""

MODULE_ID = "emotion"
MODULE_NAME = "情感与性格状态模块"
MODULE_ALIASES = ("情感与性格状态模块", "emotion", "persona", "mind")
DEFAULT_MSG_TYPE = "persona_state"

# 规则阈值
LONG_TURN_TOKENS = 800
STALE_MIND_TURNS = 5
STATE_CHANGE_TAIL = 20
RECENT_EVENTS_TAIL = 12

# 情绪连续性（程序侧）
INTENSITY_FLOOR_RESET = 0.15
MAX_INTENSITY_STEP = 0.35
DEFAULT_MOOD = "平静"
DEFAULT_INTENSITY = 0.3
DEFAULT_WARMTH = 0.15
DEFAULT_INTERACTION_MODE = "chat"

# persistence → 无有效情绪事件时每轮 intensity 衰减
PERSISTENCE_DECAY: dict[str, float] = {
    "none": 0.12,
    "low": 0.05,
    "medium": 0.02,
    "high": 0.008,
}

# 短期亲近感：无温暖向事件时每轮回落；有事件时按类型 bump
WARMTH_DECAY = 0.035
WARMTH_BUMP: dict[str, float] = {
    "playful_interaction": 0.12,
    "user_appreciation": 0.08,
    "task_success": 0.05,
    "task_resolved": 0.06,
    "tool_success": 0.04,
    "affective_positive": 0.03,
    "affective_negative": -0.06,
    "tool_failure": -0.04,
}

# 有意义事件对熟悉度的增量
FAMILIARITY_BUMP: dict[str, float] = {
    "low": 0.01,
    "medium": 0.025,
    "high": 0.045,
}

# 可跳过自然衰减、并驱动 mood/intensity/warmth 的事件
EFFECTIVE_EMOTION_TYPES: frozenset[str] = frozenset(
    {
        "tool_success",
        "tool_failure",
        "task_resolved",
        "task_success",
        "user_appreciation",
        "playful_interaction",
        "affective_positive",
        "affective_negative",
    }
)
