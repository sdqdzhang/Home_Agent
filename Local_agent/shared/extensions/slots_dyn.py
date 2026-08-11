"""动态 LLM 槽位注册（扩展 llm_slots）。"""

from __future__ import annotations

from shared.extensions.contract import LlmSlotDecl
from shared.llm.schemas import SlotDefinition
from shared.llm.slots import register_dynamic_slots, unregister_dynamic_slots_for_module


def slots_from_decls(module_id: str, decls: tuple[LlmSlotDecl, ...] | list[LlmSlotDecl]) -> list[SlotDefinition]:
    return [
        SlotDefinition(
            slot_key=d.key,
            label=d.label or d.key,
            module=module_id,
            capability=d.capability,  # type: ignore[arg-type]
            description=d.description,
        )
        for d in decls
    ]


def register_extension_llm_slots(module_id: str, decls: tuple[LlmSlotDecl, ...] | list[LlmSlotDecl]) -> None:
    register_dynamic_slots(slots_from_decls(module_id, decls))


def unregister_extension_llm_slots(module_id: str) -> None:
    unregister_dynamic_slots_for_module(module_id)
