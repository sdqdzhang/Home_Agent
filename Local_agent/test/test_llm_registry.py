from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# 引导路径：支持 python test/test_llm_registry.py 直接运行
_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.llm.errors import EndpointInUseError
from shared.llm.registry import ModelRegistry, reset_model_registry
from shared.llm.storage import LlmConfigStore


def test_seed_and_resolve() -> None:
    reset_model_registry()
    tmpdir = Path(tempfile.mkdtemp())
    store = LlmConfigStore(tmpdir / "test_llm.db")
    reg = ModelRegistry(store)

    assert reg.ensure_seeded()
    assert not reg.ensure_seeded()
    assert len(reg.list_endpoints()) == 3
    assert len(reg.list_bindings()) == 8

    cfg = reg.resolve("rag.summarize")
    assert cfg.source == "binding"
    assert cfg.model

    cfg_embed = reg.resolve("rag.embed")
    assert cfg_embed.capability == "embed"


def test_delete_endpoint_blocked_when_in_use() -> None:
    reset_model_registry()
    tmpdir = Path(tempfile.mkdtemp())
    store = LlmConfigStore(tmpdir / "test_llm.db")
    reg = ModelRegistry(store)
    reg.ensure_seeded()

    try:
        reg.delete_endpoint("ep_default_chat")
        raise AssertionError("expected EndpointInUseError")
    except EndpointInUseError as exc:
        assert "default.chat" in exc.slot_keys
        assert "无法删除" in str(exc)


def test_resolve_fallback_chain() -> None:
    reset_model_registry()
    tmpdir = Path(tempfile.mkdtemp())
    store = LlmConfigStore(tmpdir / "test_llm.db")
    reg = ModelRegistry(store)
    reg.ensure_seeded()

    reg.delete_binding("rag.summarize")
    cfg = reg.resolve("rag.summarize")
    assert cfg.source == "default_fallback"

    reg.delete_binding("default.chat")
    cfg = reg.resolve("rag.summarize")
    assert cfg.source == "env_fallback"


def test_create_and_delete_unused_endpoint() -> None:
    reset_model_registry()
    tmpdir = Path(tempfile.mkdtemp())
    store = LlmConfigStore(tmpdir / "test_llm.db")
    reg = ModelRegistry(store)
    reg.ensure_seeded()

    ep = reg.create_endpoint(
        name="Test",
        capability="chat",
        base_url="http://x/v1",
        api_key="k",
        default_model="m",
    )
    assert reg.delete_endpoint(ep.id) is True


def test_cannot_delete_endpoint_while_slot_bound() -> None:
    reset_model_registry()
    tmpdir = Path(tempfile.mkdtemp())
    store = LlmConfigStore(tmpdir / "test_llm.db")
    reg = ModelRegistry(store)
    reg.ensure_seeded()

    ep = reg.create_endpoint(
        name="Bound",
        capability="chat",
        base_url="http://x/v1",
        api_key="k",
        default_model="m",
    )
    reg.upsert_binding("crawler.chat", ep.id)

    try:
        reg.delete_endpoint(ep.id)
        raise AssertionError("expected EndpointInUseError")
    except EndpointInUseError as exc:
        assert "crawler.chat" in exc.slot_keys

    reg.upsert_binding("crawler.chat", "ep_default_chat")
    assert reg.delete_endpoint(ep.id) is True


if __name__ == "__main__":
    test_seed_and_resolve()
    test_delete_endpoint_blocked_when_in_use()
    test_resolve_fallback_chain()
    test_create_and_delete_unused_endpoint()
    test_cannot_delete_endpoint_while_slot_bound()
    print("all ok")
