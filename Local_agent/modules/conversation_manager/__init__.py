"""会话管理模块 — 程序驱动的会话生命周期（非 LLM tool）。"""

MODULE_ID = "conversation_manager"
MODULE_NAME = "会话管理"
MODULE_ALIASES = ("会话管理", "conversation_manager", "cm")
DEFAULT_MSG_TYPE = "cm_snapshot"

# 规则默认阈值（可后续配置化）
CONTEXT_REMAINING_TRIGGER = 0.20
LONG_TURN_TOKENS = 2000
STALE_STATE_TURNS = 30
MODULE_LOG_TAIL = 50
