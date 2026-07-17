"""
LLM-Note: First-run network robustness of authenticate().

What it tests:
- authenticate() with an unreachable backend returns False (no exception escapes) —
  a raw requests traceback here used to abort `co init` before ANY scaffolding,
  which is the worst possible first-install experience (caught by the windows-e2e
  offline first-run step).
- A successful response still returns True (control case, backend mocked).

Component under test: connectonion.cli.commands.auth_commands.authenticate
"""

import pytest
import requests

from connectonion.cli.commands import auth_commands


@pytest.fixture
def fake_identity(monkeypatch):
    """authenticate() needs a keypair; the network layer is what's under test."""
    monkeypatch.setattr(auth_commands.address, "load",
                        lambda d: {"address": "0x" + "a" * 64})
    monkeypatch.setattr(auth_commands.address, "sign", lambda d, m: b"\x00" * 64)


@pytest.mark.parametrize("exc", [
    requests.exceptions.ConnectionError("refused"),
    requests.exceptions.ProxyError("dead proxy"),
    requests.exceptions.Timeout("slow network"),
])
def test_authenticate_offline_returns_false_without_raising(tmp_path, monkeypatch, fake_identity, exc):
    def boom(*args, **kwargs):
        raise exc
    monkeypatch.setattr(auth_commands.requests, "post", boom)

    assert auth_commands.authenticate(tmp_path) is False  # graceful, no traceback


def test_authenticate_success_still_returns_true(tmp_path, monkeypatch, fake_identity):
    class FakeResponse:
        status_code = 200
        def json(self):
            return {"token": "tok", "user": {"balance_usd": 5.0,
                    "email": {"address": "0xaaaaaaaaaa@mail.openonion.ai"}}}
    monkeypatch.setattr(auth_commands.requests, "post", lambda *a, **k: FakeResponse())

    assert auth_commands.authenticate(tmp_path) is True


def test_authenticate_sends_a_timeout(tmp_path, monkeypatch, fake_identity):
    """No timeout means an offline-but-not-refusing network hangs first run forever."""
    seen = {}
    def capture(*args, **kwargs):
        seen.update(kwargs)
        raise requests.exceptions.Timeout("slow")
    monkeypatch.setattr(auth_commands.requests, "post", capture)

    auth_commands.authenticate(tmp_path)
    assert seen.get("timeout"), "requests.post must carry a timeout"
