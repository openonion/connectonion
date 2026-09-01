import inspect
import json

from typer.testing import CliRunner

from connectonion.cli import main as cli_main
from connectonion.cli.browser_agent import client
from connectonion.cli.browser_agent.daemon import BrowserDaemon
from connectonion.cli.commands import browser_commands
from connectonion.network.oip import browser_daemon_pb2 as wire
from connectonion.network.oip.framing import decode_frame, encode_frame
from connectonion.useful_tools.browser_tools import _async_browser as async_browser
from connectonion.useful_tools.browser_tools.browser import BrowserAutomation


class _FakeConnection:
    def __init__(self, reply=b""):
        self.reply = reply
        self.sent = b""
        self.closed = False

    def sendall(self, data):
        self.sent += data

    def shutdown(self, _how):
        pass

    def recv(self, size):
        reply, self.reply = self.reply[:size], self.reply[size:]
        return reply

    def close(self):
        self.closed = True


def _result(request_id: str, text: str, *, exit_code: int = 0) -> bytes:
    return encode_frame(
        wire.Envelope(
            protocol_version=2,
            request_id=request_id,
            result=wire.BrowserResult(exit_code=exit_code, text=text),
        )
    )


def test_cli_omission_passes_nonbilling_system_to_client(monkeypatch):
    calls = []
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda line, **kwargs: calls.append((line, kwargs)) or 0,
    )

    assert browser_commands.handle_browser(["status"]) == 0
    assert calls == [
        (
            "status",
            {"headless": False, "tab": None, "engine_mode": "system"},
        )
    ]


def test_all_local_browser_entry_points_default_to_system():
    assert inspect.signature(client.send).parameters["engine_mode"].default == "system"
    assert (
        inspect.signature(BrowserDaemon).parameters["engine_mode"].default
        == "system"
    )
    assert (
        inspect.signature(BrowserAutomation).parameters["engine_mode"].default
        == "system"
    )
    assert (
        inspect.signature(async_browser.AsyncBrowserCore)
        .parameters["engine_mode"]
        .default
        == "system"
    )


def test_typer_browser_omission_and_help_name_the_billing_boundary(monkeypatch):
    calls = []
    monkeypatch.setattr(
        browser_commands,
        "handle_browser",
        lambda args, **kwargs: calls.append((args, kwargs)) or 0,
    )

    result = CliRunner().invoke(cli_main.app, ["browser", "status"])
    auto_result = CliRunner().invoke(
        cli_main.app, ["browser", "--engine", "auto", "status"]
    )
    help_result = CliRunner().invoke(
        cli_main.app, ["browser", "--help"], env={"COLUMNS": "200"}
    )

    assert result.exit_code == 0
    assert auto_result.exit_code == 0
    assert calls == [
        (["status"], {"headless": False, "engine_mode": "system"}),
        (["status"], {"headless": False, "engine_mode": "auto"}),
    ]
    assert help_result.exit_code == 0
    assert "system (free default)" in help_result.output
    assert "auto (may select paid)" in help_result.output
    assert "onion (paid)" in help_result.output


def test_cli_passes_explicit_engine_to_client(monkeypatch):
    calls = []
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda line, **kwargs: calls.append((line, kwargs)) or 0,
    )
    assert browser_commands.handle_browser(
        ["go_to", "https://example.com"],
        headless=True,
        engine_mode="onion",
    ) == 0
    assert calls == [(
        "go_to https://example.com",
        {"headless": True, "tab": None, "engine_mode": "onion"},
    )]


def test_cli_rejects_unknown_engine_without_contacting_daemon(monkeypatch, capsys):
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("contacted daemon")),
    )
    assert browser_commands.handle_browser(["status"], engine_mode="default") == 2
    assert "auto, system, onion" in capsys.readouterr().err


def test_warm_daemon_refuses_engine_hot_swap():
    daemon = BrowserDaemon.__new__(BrowserDaemon)
    daemon.engine_mode = "system"
    daemon.browser = object()
    # __new__ skips __init__, so state the daemon always has must be set here.
    # Letting the gate read it through a falsy getattr default instead would
    # make a missing attribute skip the gateway-health check in production.
    daemon._remote_egress = False
    request = json.dumps({
        "caller": "test",
        "tab": None,
        "line": "go_to https://example.com",
        "raw": False,
        "engine": "onion",
    })
    code, message = daemon.dispatch(request)
    assert code == 6
    assert "pinned to engine=system" in message
    assert "asked for engine=onion" in message


def test_client_probes_warm_daemon_before_explicit_onion_command(monkeypatch):
    probe = _FakeConnection(b"ERR\nunknown command: engine_status")
    connections = iter([probe])
    monkeypatch.setattr(client, "_connect", lambda _path: next(connections))
    monkeypatch.setattr(client, "_caller", lambda: "test")
    monkeypatch.setattr(client, "_caller_account", lambda: "0xtest")

    code, message = client._request(
        "go_to https://example.com",
        engine_mode="onion",
    )

    assert code == 1
    assert "predates 1.8 engine pinning" in message
    assert probe.closed
    probe_request = decode_frame(probe.sent).command
    assert list(probe_request.argv) == ["engine_status"]
    assert probe_request.engine == "onion"
    assert b"go_to" not in probe.sent


def test_client_sends_command_only_after_successful_protocol_probe(monkeypatch):
    def result(request_id, text):
        return encode_frame(
            wire.Envelope(
                protocol_version=2,
                request_id=request_id,
                result=wire.BrowserResult(text=text),
            )
        )

    request_ids = iter(["probe-id", "command-id"])
    monkeypatch.setattr(client.uuid, "uuid4", lambda: type("U", (), {"hex": next(request_ids)})())
    # The outer command frame is built before its nested safety probe.
    probe = _FakeConnection(result("command-id", '{"requested": "onion"}'))
    command = _FakeConnection(result("probe-id", "done"))
    connections = iter([probe, command])
    monkeypatch.setattr(client, "_connect", lambda _path: next(connections))
    monkeypatch.setattr(client, "_caller", lambda: "test")
    monkeypatch.setattr(client, "_caller_account", lambda: "0xtest")

    assert client._request(
        "go_to https://example.com",
        engine_mode="onion",
    ) == (0, "done")

    assert list(decode_frame(probe.sent).command.argv) == ["engine_status"]
    command_request = decode_frame(command.sent).command
    assert list(command_request.argv) == ["go_to", "https://example.com"]
    assert command_request.engine == "onion"


def test_bare_onion_close_skips_the_page_action_protocol_probe(monkeypatch):
    monkeypatch.setattr(
        client.uuid,
        "uuid4",
        lambda: type("U", (), {"hex": "close-id"})(),
    )
    close = _FakeConnection(_result("close-id", "Browser closed"))
    connections = iter([close])
    monkeypatch.setattr(client, "_connect", lambda _path: next(connections))
    monkeypatch.setattr(client, "_caller", lambda: "test")
    monkeypatch.setattr(client, "_caller_account", lambda: "0xtest")

    assert client._request("close", engine_mode="onion") == (0, "Browser closed")
    request = decode_frame(close.sent).command
    assert list(request.argv) == ["close"]
    assert request.engine == "onion"
