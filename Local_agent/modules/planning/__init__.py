"""规划模块 — 信息收集后生成静态任务图；可选拓扑执行（由调用方编排）。"""

MODULE_ID = "planning"
MODULE_NAME = "规划模块"
MODULE_ALIASES = ("规划模块", "planning", "planner")
DEFAULT_MSG_TYPE = "plan_result"

GOAL_BLOCK_ID = "goal"
GOAL_BLOCK_TYPE = "goal"
MAX_NODE_ATTEMPTS = 3

# 环境探测产出的初始 DataBlock 前缀（env1、env2…）
ENV_BLOCK_PREFIX = "env"
ENV_BLOCK_TYPE = "env"
# 信息收集（质询 + 环境探测）最多自动进行的轮数
MAX_COLLECT_ROUNDS = 8
