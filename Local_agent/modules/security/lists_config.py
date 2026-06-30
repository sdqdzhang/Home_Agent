from __future__ import annotations

import logging
from typing import Any

from modules.security import LISTS_CONFIG_MSG_TYPE, SECURITY_LISTS_ACTIONS
from modules.security.rules.lists_store import LIST_KEYS, snapshot_lists, write_list_items

logger = logging.getLogger(__name__)


class SecurityListsConfig:
    """四列表（黑白命令/目录）读写。"""

    def dispatch(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "security_lists_get":
            return {"lists": snapshot_lists(), "list_keys": sorted(LIST_KEYS)}
        if action == "security_lists_set":
            list_key = str(payload.get("list_key") or "")
            items = payload.get("items")
            if list_key not in LIST_KEYS:
                raise ValueError(f"未知 list_key: {list_key}")
            if not isinstance(items, list):
                raise ValueError("items 必须为字符串数组")
            saved = write_list_items(list_key, [str(x) for x in items])
            return {"lists": snapshot_lists(), "list_key": list_key, "items": saved}
        raise ValueError(f"未知 action: {action}")

    async def reply(
        self,
        server,
        *,
        request_id: str,
        action: str,
        ok: bool,
        data: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if server is None:
            return
        await server.send_message(
            msg_type=LISTS_CONFIG_MSG_TYPE,
            message={
                "request_id": request_id,
                "ok": ok,
                "action": action,
                "data": data,
                "error": error,
            },
        )

    async def handle(
        self,
        server,
        action: str,
        payload: dict[str, Any],
    ) -> None:
        request_id = str(payload.get("request_id") or "")
        try:
            if action not in SECURITY_LISTS_ACTIONS:
                raise ValueError(f"未知 action: {action}")
            result = self.dispatch(action, payload)
            await self.reply(server, request_id=request_id, action=action, ok=True, data=result)
        except ValueError as exc:
            await self.reply(
                server,
                request_id=request_id,
                action=action,
                ok=False,
                error={"code": "invalid_request", "message": str(exc)},
            )
        except Exception as exc:
            logger.exception("Security lists config failed: %s", action)
            await self.reply(
                server,
                request_id=request_id,
                action=action,
                ok=False,
                error={"code": "internal_error", "message": str(exc)},
            )
