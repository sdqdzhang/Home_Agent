from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import asyncio

from shared.llm.registry import ModelRegistry, reset_model_registry
from shared.llm.service import LlmConfigService
from shared.llm.storage import LlmConfigStore


class _FakeServer:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, *, msg_type: str, message: dict, target: str = "user_ui") -> dict:
        self.sent.append({"msg_type": msg_type, "message": message, "target": target})
        return {}


async def _run() -> None:
    reset_model_registry()
    tmpdir = Path(tempfile.mkdtemp())
    store = LlmConfigStore(tmpdir / "svc.db")
    reg = ModelRegistry(store)
    reg.ensure_seeded()

    server = _FakeServer()
    svc = LlmConfigService(server_client=server)  # type: ignore[arg-type]
    svc.registry = reg

    await svc.handle_incoming_message({
        "name": "user_ui",
        "target": "本地Agent",
        "msg_type": "text",
        "message": {
            "payload": {"action": "llm_config_list", "request_id": "r1"},
        },
    })
    assert server.sent[-1]["message"]["ok"] is True
    assert len(server.sent[-1]["message"]["data"]["endpoints"]) == 3

    await svc.handle_incoming_message({
        "name": "user_ui",
        "target": "llm",
        "msg_type": "text",
        "message": {
            "payload": {
                "action": "llm_endpoint_create",
                "request_id": "r2",
                "endpoint": {
                    "name": "Cloud",
                    "capability": "chat",
                    "base_url": "https://api.example.com/v1",
                    "api_key": "sk-test",
                    "default_model": "gpt-4o-mini",
                },
            },
        },
    })
    assert server.sent[-1]["message"]["ok"] is True
    assert len(server.sent[-1]["message"]["data"]["endpoints"]) == 4

    print("service ok")


if __name__ == "__main__":
    asyncio.run(_run())
