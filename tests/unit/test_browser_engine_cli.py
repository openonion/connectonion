import json

from connectonion.cli.browser_agent import client
from connectonion.cli.browser_agent.daemon import BrowserDaemon
from connectonion.cli.commands import browser_commands


class _FakeConnection:
    def __init__(self, reply=b""):
        self.reply = reply
        self.sent = b""
        self.closed = False

    def sendall(self, data):
        self.sent += data

    def shutdown(self, _how):
        pass

    def recv(self, _size):
        reply, self.reply = self.reply, b""
        return reply

    def close(self):
        self.closed = True


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
    initial = _FakeConnection()
    probe = _FakeConnection(b"ERR\nunknown command: engine_status")
    connections = iter([initial, probe])
    monkeypatch.setattr(client, "_connect", lambda _path: next(connections))
    monkeypatch.setattr(client, "_caller", lambda: "test")
    monkeypatch.setattr(client, "_caller_account", lambda: "0xtest")

    code, message = client._request(
        "go_to https://example.com",
        engine_mode="onion",
    )

    assert code == 1
    assert "predates 1.8 engine pinning" in message
    assert initial.closed
    probe_request = json.loads(probe.sent)
    assert probe_request["line"] == "engine_status"
    assert probe_request["engine"] == "onion"
    assert b"go_to" not in probe.sent


def test_client_sends_command_only_after_successful_protocol_probe(monkeypatch):
    initial = _FakeConnection()
    probe = _FakeConnection(b'OK\n{"requested": "onion"}')
    command = _FakeConnection(b"OK\ndone")
    connections = iter([initial, probe, command])
    monkeypatch.setattr(client, "_connect", lambda _path: next(connections))
    monkeypatch.setattr(client, "_caller", lambda: "test")
    monkeypatch.setattr(client, "_caller_account", lambda: "0xtest")

    assert client._request(
        "go_to https://example.com",
        engine_mode="onion",
    ) == (0, "done")

    assert json.loads(probe.sent)["line"] == "engine_status"
    command_request = json.loads(command.sent)
    assert command_request["line"] == "go_to https://example.com"
    assert command_request["engine"] == "onion"
