from __future__ import annotations

import logging
from typing import Any

from shared.llm.constants import LLM_CONFIG_ACTIONS, LLM_CONFIG_MSG_TYPE, MODULE_ALIASES
from shared.llm.errors import EndpointInUseError, EndpointNotFoundError, InvalidSlotError, LLMRegistryError
from shared.llm.registry import get_model_registry
from shared.server_center.client import ServerCenterClient

logger = logging.getLogger(__name__)


class LlmConfigService:
    """处理前端经 Server Center 转发的 LLM 配置请求。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        self.server = server_client
        self.registry = get_model_registry()
        self.registry.ensure_seeded()

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        if data.get("name") != "user_ui":
            return
        if data.get("target", "") not in MODULE_ALIASES:
            return
        if data.get("msg_type", "text") != "text":
            return

        message = data.get("message") or {}
        payload = message.get("payload") or {}
        action = payload.get("action")
        if not action or action not in LLM_CONFIG_ACTIONS:
            return

        request_id = str(payload.get("request_id") or "")
        try:
            result = self._dispatch(action, payload)
            await self._reply_ok(request_id, action, result)
        except EndpointInUseError as exc:
            await self._reply_err(
                request_id,
                action,
                "endpoint_in_use",
                str(exc),
                slot_keys=exc.slot_keys,
            )
        except (EndpointNotFoundError, InvalidSlotError, ValueError) as exc:
            await self._reply_err(request_id, action, "invalid_request", str(exc))
        except LLMRegistryError as exc:
            await self._reply_err(request_id, action, "registry_error", str(exc))
        except Exception as exc:
            logger.exception("LLM config action failed: %s", action)
            await self._reply_err(request_id, action, "internal_error", str(exc))

    def _dispatch(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "llm_config_list":
            return self._list_snapshot()
        if action == "llm_endpoint_create":
            self._create_endpoint(payload.get("endpoint") or {})
            return self._list_snapshot()
        if action == "llm_endpoint_update":
            endpoint_id = payload.get("endpoint_id")
            if not endpoint_id:
                raise ValueError("缺少 endpoint_id")
            self._update_endpoint(str(endpoint_id), payload.get("endpoint") or {})
            return self._list_snapshot()
        if action == "llm_endpoint_delete":
            endpoint_id = payload.get("endpoint_id")
            if not endpoint_id:
                raise ValueError("缺少 endpoint_id")
            self.registry.delete_endpoint(str(endpoint_id))
            return self._list_snapshot()
        if action == "llm_binding_upsert":
            self._upsert_binding(payload)
            return self._list_snapshot()
        raise ValueError(f"未知 action: {action}")

    def _list_snapshot(self) -> dict[str, Any]:
        snap = self.registry.snapshot()
        for ep in snap["endpoints"]:
            usage = self.registry.endpoint_usage(ep["id"])
            ep["slot_usage"] = usage
            ep["usage_count"] = len(usage)
        return snap

    def _create_endpoint(self, fields: dict[str, Any]) -> None:
        base_url = str(fields.get("base_url") or "").strip()
        default_model = str(fields.get("default_model") or "").strip()
        if not base_url or not default_model:
            raise ValueError("base_url 与 default_model 不能为空")
        self.registry.create_endpoint(
            name=str(fields.get("name") or "新模型"),
            capability=str(fields.get("capability") or "chat"),
            base_url=base_url,
            api_key=str(fields.get("api_key") or ""),
            default_model=default_model,
            timeout=float(fields.get("timeout") or 120),
            max_tokens=_optional_int(fields.get("max_tokens")),
            temperature=_optional_float(fields.get("temperature")),
            enabled=bool(fields.get("enabled", True)),
        )

    def _update_endpoint(self, endpoint_id: str, fields: dict[str, Any]) -> None:
        kwargs: dict[str, Any] = {}
        for key in ("name", "capability", "base_url", "api_key", "default_model", "enabled"):
            if key in fields and fields[key] is not None:
                kwargs[key] = fields[key]
        if "timeout" in fields and fields["timeout"] is not None:
            kwargs["timeout"] = float(fields["timeout"])
        if "max_tokens" in fields:
            if fields["max_tokens"] in (None, ""):
                kwargs["clear_max_tokens"] = True
            else:
                kwargs["max_tokens"] = int(fields["max_tokens"])
        if "temperature" in fields:
            if fields["temperature"] in (None, ""):
                kwargs["clear_temperature"] = True
            else:
                kwargs["temperature"] = float(fields["temperature"])
        self.registry.update_endpoint(endpoint_id, **kwargs)

    def _upsert_binding(self, payload: dict[str, Any]) -> None:
        slot_key = payload.get("slot_key")
        endpoint_id = payload.get("endpoint_id")
        if not slot_key or not endpoint_id:
            raise ValueError("缺少 slot_key 或 endpoint_id")

        kwargs: dict[str, Any] = {}
        if payload.get("clear_model_override"):
            kwargs["clear_model_override"] = True
        elif "model_override" in payload:
            override = payload.get("model_override")
            kwargs["model_override"] = str(override).strip() if override else None
            if not override:
                kwargs["clear_model_override"] = True

        self.registry.upsert_binding(str(slot_key), str(endpoint_id), **kwargs)

    async def _reply_ok(self, request_id: str, action: str, data: dict[str, Any]) -> None:
        if not self.server:
            return
        await self.server.send_message(
            msg_type=LLM_CONFIG_MSG_TYPE,
            message={
                "request_id": request_id,
                "ok": True,
                "action": action,
                "data": data,
            },
        )

    async def _reply_err(
        self,
        request_id: str,
        action: str,
        code: str,
        message: str,
        **extra: Any,
    ) -> None:
        if not self.server:
            return
        await self.server.send_message(
            msg_type=LLM_CONFIG_MSG_TYPE,
            message={
                "request_id": request_id,
                "ok": False,
                "action": action,
                "error": {"code": code, "message": message, **extra},
            },
        )


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
