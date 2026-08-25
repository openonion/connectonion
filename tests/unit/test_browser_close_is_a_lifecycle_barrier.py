"""A successful whole-browser close waits until that daemon has actually exited."""

from connectonion.cli.browser_agent import client


class _ReplyConnection:
    def __init__(self, reply=b"OK\nBrowser closed. Session saved for next time."):
        self.reply = reply

    def send_bytes(self, request):
        self.request = request

    def recv_bytes(self):
        return self.reply

    def close(self):
        pass


def _windows_client(monkeypatch):
    connection = _ReplyConnection()
    monkeypatch.setattr(client.transport, "IS_WINDOWS", True)
    monkeypatch.setattr(client, "default_sock_path", lambda: "pipe")
    monkeypatch.setattr(client, "_connect", lambda _path: connection)
    monkeypatch.setattr(client, "_caller_account", lambda: "")
    monkeypatch.setattr(client, "_owner_pid", lambda _path: 4242)
    return connection


def test_whole_browser_close_waits_for_the_old_daemon_pid(monkeypatch):
    _windows_client(monkeypatch)
    alive = iter((True, True, False))
    checked = []
    sleeps = []

    def pid_alive(pid):
        checked.append(pid)
        return next(alive)

    monkeypatch.setattr(client.transport, "pid_alive", pid_alive)
    monkeypatch.setattr(client.time, "sleep", sleeps.append)

    assert client._request("close") == (
        0,
        "Browser closed. Session saved for next time.",
    )
    assert checked == [4242, 4242, 4242]
    assert sleeps == [0.05, 0.05]


def test_targeted_tab_close_does_not_wait_for_daemon_exit(monkeypatch):
    _windows_client(monkeypatch)
    checked = []
    monkeypatch.setattr(
        client.transport, "pid_alive", lambda pid: checked.append(pid) or True
    )

    assert client._request("close", tab="work")[0] == 0
    assert checked == []


def test_other_successful_commands_do_not_wait_for_daemon_exit(monkeypatch):
    _windows_client(monkeypatch)
    checked = []
    monkeypatch.setattr(
        client.transport, "pid_alive", lambda pid: checked.append(pid) or True
    )

    assert client._request("status")[0] == 0
    assert checked == []
