"""A supervised task must not start or use a replacement browser daemon."""
from types import SimpleNamespace

import pytest

from connectonion.cli.browser_agent import client
from connectonion.cli.commands import browser_commands
from connectonion.network.oip import browser_daemon_pb2 as wire
from connectonion.network.oip.framing import decode_frame, encode_frame


class Connection:
    def __init__(self):
        self.sent = []
        self.reply = b""
        self.closed = False

    def settimeout(self, _timeout):
        pass

    def sendall(self, request):
        frame = decode_frame(request)
        self.sent.append(list(frame.command.argv))
        self.reply = encode_frame(wire.Envelope(
            protocol_version=2, request_id=frame.request_id,
            result=wire.BrowserResult(text="Browser ready")))

    def recv(self, size):
        part, self.reply = self.reply[:size], self.reply[size:]
        return part

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def managed(monkeypatch):
    monkeypatch.setenv("CO_BROWSER_DAEMON_PID", "424242")
    monkeypatch.setattr(client, "default_sock_path", lambda: "/private/test/browser.sock")
    monkeypatch.setattr(client, "_owner_pid", lambda _path: 424242)
    monkeypatch.setattr(client.transport, "IS_WINDOWS", False)
    for name in ("_spawn_daemon", "_ensure_browser_ready", "_finish_close", "_process_tree"):
        monkeypatch.setattr(client, name, forbidden)


def forbidden(*_args, **_kwargs):
    pytest.fail("managed endpoint started, provisioned or force-cleaned a browser")


def request(line="go_to https://example.com", **kwargs):
    return client._request_with_identity(line, caller="test", account="0xtest", **kwargs)


@pytest.mark.parametrize("value", ["", "0", "-1", "abc", "²"])
def test_invalid_pin_fails_before_connect(monkeypatch, value):
    monkeypatch.setenv("CO_BROWSER_DAEMON_PID", value)
    monkeypatch.setattr(client, "_connect", forbidden)
    code, message = request()
    assert code == 2 and "CO_BROWSER_DAEMON_PID" in message


@pytest.mark.parametrize("owner", [None, 424243])
def test_gone_or_replaced_daemon_is_not_contacted(monkeypatch, owner):
    monkeypatch.setattr(client, "_owner_pid", lambda _path: owner)
    monkeypatch.setattr(client, "_connect", forbidden)
    code, message = request()
    assert code == 1 and "managed browser daemon" in message


def test_loss_after_preflight_never_spawns(monkeypatch):
    monkeypatch.setattr(client, "_connect", lambda _path: None)
    code, message = request()
    assert code == 1 and "managed browser daemon" in message


def test_replacement_during_connect_receives_no_request(monkeypatch):
    connection = Connection()
    def connect(_path):
        monkeypatch.setattr(client, "_owner_pid", lambda _path: 424243)
        return connection
    monkeypatch.setattr(client, "_connect", connect)
    assert request()[0] == 1
    assert connection.closed and connection.sent == []


def test_supplied_connection_is_checked_and_closed(monkeypatch):
    connection = Connection()
    monkeypatch.setattr(client, "_owner_pid", lambda _path: 424243)
    monkeypatch.setattr(client, "_connect", forbidden)
    assert request(_connection=connection)[0] == 1
    assert connection.closed and connection.sent == []


def test_live_pinned_daemon_receives_the_command(monkeypatch):
    connection = Connection()
    monkeypatch.setattr(client, "_connect", lambda _path: connection)
    assert request() == (0, "Browser ready")
    assert connection.sent == [["go_to", "https://example.com"]]
    assert connection.closed


def test_engine_probe_cannot_reconnect_to_replacement(monkeypatch):
    probe, replacement = Connection(), Connection()
    connections = iter([probe, replacement])
    def connect(_path):
        connection = next(connections)
        if connection is replacement:
            monkeypatch.setattr(client, "_owner_pid", lambda _path: 424243)
        return connection
    monkeypatch.setattr(client, "_connect", connect)
    assert request(engine_mode="onion")[0] == 1
    assert probe.sent == [["engine_status"]]
    assert replacement.sent == [] and replacement.closed


def test_probe_pin_failure_is_not_old_protocol_advice(monkeypatch):
    connection = Connection()
    owners = iter([424242, 424242, 424243])
    monkeypatch.setattr(client, "_owner_pid", lambda _path: next(owners))
    monkeypatch.setattr(client, "_connect", lambda _path: connection)
    code, message = request(engine_mode="onion")
    assert code == 1 and "managed browser daemon" in message
    assert "kill" not in message and "predates" not in message
    assert connection.sent == [] and connection.closed


def test_replacement_after_probe_is_not_connected(monkeypatch):
    probe = Connection()
    def close_and_replace():
        probe.closed = True
        monkeypatch.setattr(client, "_owner_pid", lambda _path: 424243)
    probe.close = close_and_replace
    calls = []
    def connect(path):
        calls.append(path)
        assert len(calls) == 1, 'connected to replacement after successful probe'
        return probe
    monkeypatch.setattr(client, "_connect", connect)
    code, message = request(engine_mode="onion")
    assert code == 1 and "managed browser daemon" in message
    assert probe.sent == [["engine_status"]] and probe.closed


def test_close_connect_timeout_never_cleans_replacement(monkeypatch):
    def connect(_path):
        monkeypatch.setattr(client, "_owner_pid", lambda _path: 424243)
        raise client._DaemonNotAnswering("not answering")
    monkeypatch.setattr(client, "_connect", connect)
    assert request("close")[0] == 1


def test_close_reply_timeout_does_not_force_clean_replacement(monkeypatch):
    connection = Connection()
    def recv(_size):
        monkeypatch.setattr(client, "_owner_pid", lambda _path: 424243)
        raise TimeoutError("old connection stopped answering")
    connection.recv = recv
    monkeypatch.setattr(client, "_connect", lambda _path: connection)
    monkeypatch.setattr(client, "_process_tree", lambda pid: [pid])
    assert request("close")[0] == 1
    assert connection.closed


def test_close_reply_does_not_clean_a_replacement_owner(monkeypatch):
    connection = Connection()
    send = connection.sendall
    def send_then_replace(frame):
        send(frame)
        monkeypatch.setattr(client, "_owner_pid", lambda _path: 424243)
    connection.sendall = send_then_replace
    monkeypatch.setattr(client, "_connect", lambda _path: connection)
    monkeypatch.setattr(client, "_process_tree", lambda pid: [pid])
    code, message = request("close")
    assert code == 1 and "replacement left untouched" in message
    assert connection.closed


def test_loss_after_probe_does_not_reconnect_again(monkeypatch):
    probe = Connection()
    connections = iter([probe, None])
    monkeypatch.setattr(client, "_connect", lambda _path: next(connections))
    code, message = request(engine_mode="onion")
    assert code == 1 and "after its protocol probe" in message
    assert probe.sent == [["engine_status"]]


def test_keepalive_status_uses_the_same_pin(monkeypatch):
    monkeypatch.setattr(client, "_owner_pid", lambda _path: None)
    monkeypatch.setattr(client, "_connect", forbidden)
    assert not client._daemon_answers_status("test", "0xtest", None)


def test_explicit_host_target_ignores_local_pin(monkeypatch):
    connection = Connection()
    monkeypatch.setenv("CO_BROWSER_DAEMON_PID", "invalid-local-value")
    monkeypatch.setattr(client, "_owner_pid", forbidden)
    monkeypatch.setattr(client, "_connect", lambda _path, **_kwargs: connection)
    target = SimpleNamespace(address="other-endpoint", authkey_path="test-key", remote_egress=False)
    assert request(target=target) == (0, "Browser ready")
    assert connection.sent == [["go_to", "https://example.com"]]


def test_managed_cli_does_not_bootstrap_a_missing_paid_client(monkeypatch):
    calls = []
    monkeypatch.setattr(browser_commands, "_ensure_paid_client", forbidden)
    monkeypatch.setattr(browser_commands, "send", lambda *args, **kwargs: calls.append((args,kwargs)) or 1)
    assert browser_commands.handle_browser(["go_to", "https://example.com"], engine_mode="onion") == 1
    assert calls[0][1]['engine_mode'] == 'onion'
