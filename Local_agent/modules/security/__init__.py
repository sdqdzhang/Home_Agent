"""安全检查模块 — 命令风险判定与用户审批。"""

MODULE_ID = "security"
MODULE_NAME = "安全检查模块"
MODULE_ALIASES = ("安全检查模块", "security")
DEFAULT_MSG_TYPE = "approval_request"
YELLOW_LOG_MSG_TYPE = "security_yellow_log"
LISTS_CONFIG_MSG_TYPE = "security_lists_result"

SECURITY_LISTS_ACTIONS = frozenset(
    {
        "security_lists_get",
        "security_lists_set",
    }
)
