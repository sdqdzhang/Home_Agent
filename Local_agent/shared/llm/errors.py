from __future__ import annotations


class LLMRegistryError(Exception):
    """LLM 配置注册表基础异常。"""


class EndpointNotFoundError(LLMRegistryError):
    def __init__(self, endpoint_id: str) -> None:
        self.endpoint_id = endpoint_id
        super().__init__(f"模型端点不存在: {endpoint_id}")


class BindingNotFoundError(LLMRegistryError):
    def __init__(self, slot_key: str) -> None:
        self.slot_key = slot_key
        super().__init__(f"槽位未绑定: {slot_key}")


class InvalidSlotError(LLMRegistryError):
    def __init__(self, slot_key: str) -> None:
        self.slot_key = slot_key
        super().__init__(f"未知槽位: {slot_key}")


class EndpointInUseError(LLMRegistryError):
    """删除端点时仍有 binding 引用。"""

    def __init__(self, endpoint_id: str, slot_keys: list[str]) -> None:
        self.endpoint_id = endpoint_id
        self.slot_keys = slot_keys
        slots = "、".join(slot_keys)
        super().__init__(f"无法删除该模型：仍被以下槽位使用（{slots}）。请先在设置中将上述槽位改绑到其他模型后再删除。")
