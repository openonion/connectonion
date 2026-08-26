"""Remote Browser lifecycle through the real native daemon transport."""

import contextlib
import os
import threading
import time

from connectonion.cli.browser_agent import transport
from connectonion.cli.browser_agent.client import request_as
from connectonion.cli.browser_agent.daemon import BrowserDaemon
from connectonion.network.host.remote_browser import RemoteBrowserService


class LifecycleBrowser:
    """Small runtime seam: the test targets transport/claims, not Chrome."""

    def __init__(self):
        self._tab_meta = {}
        self._pages = {}

    def _bind_session(self, session):
        self.session = session

    def close_tab(self, name):
        self._tab_meta.pop(name, None)
        return f"Closed tab {name}"

    def close(self):
        return "Browser closed"


def _wait_for_daemon(socket_path):
    deadline = time.time() + 5
    while time.time() < deadline:
        if os.path.exists(transport.pid_path(socket_path)):
            return
        time.sleep(0.02)
    raise RuntimeError("daemon did not bind in time")


def test_remote_lifecycle_uses_one_native_daemon_and_survives_host_restart(
    tmp_path, monkeypatch
):
    socket_path = f"/tmp/co_remote_{os.getpid()}_{time.time_ns()}.sock"
    monkeypatch.setenv("CO_BROWSER_SOCK", socket_path)
    daemon = BrowserDaemon(socket_path, headless=True)
    daemon.browser = LifecycleBrowser()
    thread = threading.Thread(target=daemon.serve, daemon=True)
    thread.start()
    try:
        _wait_for_daemon(socket_path)
        state_path = tmp_path / "remote-browser-sessions.json"
        service = RemoteBrowserService(state_path, daemon_request=request_as)
        started = service.handle(
            {
                "request_id": "native-start",
                "command": "start",
                "args": {"headless": True, "proxy": "direct"},
            },
            owner="0xowner",
            transport="direct",
        )
        assert started["ok"] is True
        session_id = started["result"]["session_id"]
        assert len(daemon.browser._tab_meta) == 1

        restarted_host_service = RemoteBrowserService(
            state_path, daemon_request=request_as
        )
        status = restarted_host_service.handle(
            {
                "request_id": "native-status",
                "command": "status",
                "session_id": session_id,
            },
            owner="0xowner",
            transport="direct",
        )
        assert status["state"]["session"] == "active"

        stopped = restarted_host_service.handle(
            {
                "request_id": "native-stop",
                "command": "stop",
                "session_id": session_id,
            },
            owner="0xowner",
            transport="direct",
        )
        assert stopped["state"]["session"] == "stopped"
        assert daemon.browser._tab_meta == {}
    finally:
        daemon._cleanup()
        thread.join(timeout=2)
        for path in (
            socket_path,
            transport.pid_path(socket_path),
            transport.lock_path(socket_path),
        ):
            with contextlib.suppress(OSError):
                if os.path.exists(path):
                    os.unlink(path)
