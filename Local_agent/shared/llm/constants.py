"""LLM 配置模块在 Server Center 中的路由标识。"""

MODULE_ID = "llm"
MODULE_NAME = "本地Agent"
MODULE_ALIASES = ("本地Agent", "local_agent", "llm")
LLM_CONFIG_MSG_TYPE = "llm_config_result"

LLM_CONFIG_ACTIONS = frozenset({
    "llm_config_list",
    "llm_endpoint_create",
    "llm_endpoint_update",
    "llm_endpoint_delete",
    "llm_binding_upsert",
})
