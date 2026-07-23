"""Unit tests for `co call` — remote one-shot command execution (cli/commands/call_commands.py).

The network is mocked: connect() returns a fake RemoteAgent whose .call() yields a
canned ExecResult, so these tests cover argument parsing, the exit-code contract,
and image-vs-text output handling without touching a real agent.
"""

import base64
import pytest

from connectonion import ExecResult
from connectonion.cli.commands import call_commands
from connectonion.cli.commands.call_commands import handle_call


class FakeRemote:
    """Stand-in for RemoteAgent: records the last call and returns a canned result."""
    def __init__(self, result):
        self._result = result
        self.calls = []

    def call(self, tool, command=None, timeout=60.0, **kw):
        self.calls.append({"tool": tool, "command": command, "timeout": timeout})
        return self._result


def install_fake(monkeypatch, result):
    """Patch connect() (looked up as connectonion.connect inside handle_call) and
    silence key loading so tests don't depend on a local .co."""
    fake = FakeRemote(result)
    monkeypatch.setattr("connectonion.connect", lambda address, **kw: fake, raising=False)
    monkeypatch.setattr(call_commands, "_load_keys", lambda: None)
    return fake


# ─────────────────────────── usage / exit codes ───────────────────────────

class TestUsage:
    def test_no_args_is_usage_error(self, capsys):
        assert handle_call([]) == 2
        assert "co call" in capsys.readouterr().err

    def test_help_is_success(self, capsys):
        assert handle_call(["help"]) == 0
        assert "remote agent" in capsys.readouterr().out

    def test_address_without_command_is_usage_error(self, capsys):
        assert handle_call(["0xabc"]) == 2
        assert "usage" in capsys.readouterr().err.lower()

    def test_unknown_option_is_usage_error(self, capsys):
        assert handle_call(["--nope", "x", "0xabc", "co", "status"]) == 2
        assert "unknown option" in capsys.readouterr().err

    def test_out_without_value_is_usage_error(self, capsys):
        assert handle_call(["--out"]) == 2


# ─────────────────────────── text result ───────────────────────────

class TestTextResult:
    def test_prints_text_and_returns_zero(self, monkeypatch, capsys):
        install_fake(monkeypatch, ExecResult(text="balance: $4.20", status="success"))
        assert handle_call(["0xabc", "co", "status"]) == 0
        assert capsys.readouterr().out.strip() == "balance: $4.20"

    def test_command_is_forwarded_verbatim(self, monkeypatch):
        fake = install_fake(monkeypatch, ExecResult(text="ok", status="success"))
        handle_call(["0xabc", "co", "browser", "go_to", "https://x.com"])
        # everything after the address is joined into one bash command
        assert fake.calls[0]["tool"] == "bash"
        assert fake.calls[0]["command"] == "co browser go_to https://x.com"

    def test_remote_command_keeps_its_own_flags(self, monkeypatch):
        fake = install_fake(monkeypatch, ExecResult(text="ok", status="success"))
        handle_call(["0xabc", "ls", "-la"])
        assert fake.calls[0]["command"] == "ls -la"


# ─────────────────────────── error result ───────────────────────────

class TestErrorResult:
    def test_error_result_goes_to_stderr_exit_one(self, monkeypatch, capsys):
        install_fake(monkeypatch, ExecResult(text="", status="error", error="blocked: not whitelisted"))
        assert handle_call(["0xabc", "rm", "-rf", "/"]) == 1
        assert "blocked" in capsys.readouterr().err

    def test_connection_exception_is_exit_one(self, monkeypatch, capsys):
        def boom(address, **kw):
            raise ConnectionError("relay unreachable")
        monkeypatch.setattr("connectonion.connect", boom, raising=False)
        monkeypatch.setattr(call_commands, "_load_keys", lambda: None)
        assert handle_call(["0xabc", "co", "status"]) == 1
        assert "connection failed" in capsys.readouterr().err


# ─────────────────────────── image result ───────────────────────────

class TestImageResult:
    def test_screenshot_saved_to_out_path(self, monkeypatch, capsys, tmp_path):
        png = base64.b64encode(b"\x89PNG_fake").decode()
        install_fake(monkeypatch, ExecResult(text=f"data:image/png;base64,{png}", status="success"))
        dest = tmp_path / "shot.png"
        assert handle_call(["--out", str(dest), "0xabc", "co", "browser", "take_screenshot"]) == 0
        assert dest.read_bytes() == b"\x89PNG_fake"
        assert capsys.readouterr().out.strip() == str(dest)

    def test_timeout_option_parsed(self, monkeypatch):
        fake = install_fake(monkeypatch, ExecResult(text="ok", status="success"))
        handle_call(["--timeout", "5", "0xabc", "co", "status"])
        assert fake.calls[0]["timeout"] == 5.0
