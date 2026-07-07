"""执行模块 LLM 槽位键名。"""

EXECUTOR_PARSE_SLOT = "executor.parse"
EXECUTOR_CODEGEN_SLOT = "executor.codegen"

# 已废弃、启动时由 migrate_executor_slots 清理
LEGACY_EXECUTOR_PARSE_SLOTS = (
    "executor.chat",
    "executor.command.parse",
    "executor.read_file.parse",
    "executor.write_file.parse",
    "executor.delete_file.parse",
    "executor.browse_dir.parse",
    "executor.search_file.parse",
    "executor.search_content.parse",
)
