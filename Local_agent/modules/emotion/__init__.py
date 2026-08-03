"""心智与状态（Mind）模块 — 人格行为上下文 / 情绪连续性（非 LLM tool）。"""

MODULE_ID = "emotion"
MODULE_NAME = "情感与性格状态模块"
MODULE_ALIASES = ("情感与性格状态模块", "emotion", "persona", "mind")
DEFAULT_MSG_TYPE = "persona_state"

# 规则阈值
LONG_TURN_TOKENS = 800
STALE_MIND_TURNS = 5
STATE_CHANGE_TAIL = 20

# 情绪连续性（程序侧）
INTENSITY_DECAY_PER_TURN = 0.05
INTENSITY_FLOOR_RESET = 0.15
MAX_INTENSITY_STEP = 0.35
DEFAULT_MOOD = "平静"
DEFAULT_INTENSITY = 0.3
