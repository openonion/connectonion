"""Coverage tests for remaining modules with light-touch assertions."""

from pathlib import Path

import connectonion.core.events as events
import importlib

host_server = importlib.import_module("connectonion.network.host.server")
from connectonion.network.io.base import IO
from connectonion.network.io.websocket import WebSocketIO
import connectonion.network.relay as relay
from connectonion.network.trust.trust_agent import TrustAgent
import connectonion.tui.providers as tui_providers
from connectonion.useful_tools.memory import Memory
from connectonion.debug.runtime_inspector.agent import create_debug_agent


def test_event_decorators_tag_function():
    def fn(agent):
        return None

    events.after_user_input(fn)
    assert getattr(fn, "_event_type", None) == "after_user_input"


def test_parse_trust_config_inline():
    cfg = host_server._parse_trust_config("---\ndefault: allow\n---\n")
    assert cfg and cfg.get("default") == "allow"
    assert host_server.get_default_trust()


def test_io_classes():
    assert issubclass(WebSocketIO, IO)


def test_relay_module_exports():
    assert callable(relay.connect)
    assert callable(relay.send_announce)


def test_trust_agent_open():
    trust = TrustAgent("open")
    assert trust.trust == "open"


def test_tui_providers_static_search():
    provider = tui_providers.StaticProvider([("/help", "/help")])
    results = provider.search("help")
    assert results and results[0].value == "/help"


def test_memory_basic(tmp_path):
    mem_file = tmp_path / "memory.md"
    mem = Memory(memory_file=str(mem_file))
    assert "Memory saved" in mem.write_memory("key", "value")


def test_create_debug_agent(monkeypatch):
    class FakeLLM:
        model = "fake"

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    agent = create_debug_agent()
    assert agent.name == "debug_agent"
