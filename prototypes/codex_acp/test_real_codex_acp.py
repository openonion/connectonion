"""
PROTOTYPE end-to-end test against the REAL codex-acp binary.

Not part of the shipped suite (pytest testpaths=tests). Skips unless a real
codex-acp binary is reachable, so it never breaks CI. Run explicitly:

    # protocol handshake only (no API key needed):
    CODEX_ACP_BIN=./path/to/codex-acp \
        python -m pytest prototypes/codex_acp/test_real_codex_acp.py -q

    # full model turn (needs auth):
    OPENAI_API_KEY=sk-... CODEX_ACP_BIN=./path/to/codex-acp \
        python -m pytest prototypes/codex_acp/test_real_codex_acp.py -q

Discovery order for the binary: $CODEX_ACP_BIN, then `codex-acp` on PATH.
"""

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from acp_client import ACPClient


def _find_binary():
    return os.environ.get("CODEX_ACP_BIN") or shutil.which("codex-acp")


BIN = _find_binary()
HAS_AUTH = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_API_KEY"))

pytestmark = pytest.mark.skipif(BIN is None, reason="codex-acp binary not found (set CODEX_ACP_BIN)")


def test_initialize_handshake_matches_client():
    """The real adapter negotiates the protocol our client speaks."""
    client = ACPClient(command=[BIN], cwd=".")
    client.start()
    try:
        info = client.initialize()
        assert info["protocolVersion"] == 1
        assert info["agentInfo"]["name"] == "codex-acp"
        # capabilities our client relies on for resume + streaming
        assert info["agentCapabilities"].get("loadSession") is True
    finally:
        client.close()


@pytest.mark.skipif(HAS_AUTH, reason="auth present; the no-auth error path does not apply")
def test_session_new_requires_auth_without_credentials():
    """Without credentials the adapter returns a real JSON-RPC error our
    client surfaces cleanly (proves error-frame handling against the binary)."""
    client = ACPClient(command=[BIN], cwd=".")
    client.start()
    try:
        client.initialize()
        with pytest.raises(RuntimeError) as exc:
            client.request("session/new", {"cwd": ".", "mcpServers": []}, timeout=30)
        assert "Authentication required" in str(exc.value)
    finally:
        client.close()


@pytest.mark.skipif(not HAS_AUTH, reason="needs OPENAI_API_KEY/CODEX_API_KEY for a real model turn")
def test_full_prompt_turn_streams_updates():
    """With credentials: a real session streams updates and ends cleanly."""
    events = []
    client = ACPClient(command=[BIN], cwd=".", on_event=events.append)
    client.start()
    try:
        client.initialize()
        session_id = client.new_session()
        assert session_id
        stop = client.prompt(session_id, "Reply with exactly the word: pong")
        assert stop  # some stopReason returned
        # at least one assistant message chunk streamed back
        assert any(e["acp_update"] == "agent_message_chunk" for e in events)
    finally:
        client.close()
