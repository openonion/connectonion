"""Remote Browser lifecycle through the real native daemon transport."""

import asyncio
import contextlib
import json
import threading
import time
from pathlib import Path

from connectonion import address
from connectonion.cli.browser_agent import transport
from connectonion.cli.browser_agent.daemon import BrowserDaemon
from connectonion.network.connect import RemoteAgent
from connectonion.network.host.private_browser_runtime import PrivateBrowserTarget
from connectonion.network.host.remote_browser import RemoteBrowserService
from connectonion.network.host.server import _make_remote_browser
from connectonion.network.host.ws_router import session as ws_session


class LifecycleBrowser:
    """Small runtime seam: the test targets transport/claims, not Chrome."""

    def __init__(self, **_kwargs):
        self._tab_meta = {}
        self._pages = {}

    def _bind_session(self, session):
        self.session = session

    def close_tab(self, name):
        self._tab_meta.pop(name, None)
        return f"Closed tab {name}"

    async def close(self):
        return "Browser closed"


class ContactTrust:
    def is_admin(self, owner):
        return False

    def get_level(self, owner):
        return "contact"


async def _signed_start(service, monkeypatch):
    keys = address.generate()
    host = "0x" + "12" * 20
    command = RemoteAgent(host, keys=keys)._build_command_message(
        {
            "type": "REMOTE_BROWSER",
            "request_id": "native-start",
            "command": "start",
            "args": {"headless": True, "proxy": "direct"},
        },
        is_direct=True,
    )
    frames = [{"type": "CONNECT", "from": keys["address"]}, command]
    result_sent = asyncio.Event()
    sent = []

    async def fake_connect(data, send, conn, *args):
        conn.update(
            authenticated=True,
            agent_address=keys["address"],
            signed_commands=True,
            recipient_address=host,
            session_id="native-oip",
        )

    async def recv():
        if frames:
            return frames.pop(0)
        await result_sent.wait()
        return None

    async def send(message):
        sent.append(message)
        if message.get("type") == "REMOTE_BROWSER_RESULT":
            result_sent.set()

    monkeypatch.setattr(ws_session, "handle_connect", fake_connect)
    await ws_session.run_ws_session(
        send,
        recv,
        route_handlers={
            "remote_browser": _make_remote_browser(service, ContactTrust()),
        },
        storage=None,
        registry=None,
        trust=None,
        enable_ping=False,
        transport="direct",
    )
    result = next(
        message for message in sent if message.get("type") == "REMOTE_BROWSER_RESULT"
    )
    assert json.loads(json.dumps(result))["request_id"] == "native-start"
    return result, keys["address"]


def _wait_for_daemon(socket_path):
    deadline = time.time() + 5
    while time.time() < deadline:
        if Path(transport.pid_path(socket_path)).exists():
            return
        time.sleep(0.02)
    raise RuntimeError("daemon did not bind in time")


def test_remote_lifecycle_uses_one_native_daemon_and_survives_host_restart(
    tmp_path, monkeypatch
):
    state_path = tmp_path / "remote-browser-sessions.json"
    target = PrivateBrowserTarget.from_state_path(state_path)
    daemon = BrowserDaemon(
        target.address,
        headless=True,
        profile_dir=target.profile_dir,
        authkey_path=target.authkey_path,
        remote_egress=True,
        browser_factory=LifecycleBrowser,
    )
    thread = threading.Thread(target=daemon.serve, daemon=True)
    thread.start()
    try:
        _wait_for_daemon(target.address)
        service = RemoteBrowserService(state_path)
        started, owner = asyncio.run(_signed_start(service, monkeypatch))
        assert started["ok"] is True
        session_id = started["result"]["session_id"]
        assert len(daemon.browser._tab_meta) == 1
        assert next(iter(daemon.browser._tab_meta.values()))["opened_by"] == owner

        restarted_host_service = RemoteBrowserService(state_path)
        status = restarted_host_service.handle(
            {
                "request_id": "native-status",
                "command": "status",
                "session_id": session_id,
            },
            owner=owner,
            transport="direct",
        )
        assert status["state"]["session"] == "active"

        stopped = restarted_host_service.handle(
            {
                "request_id": "native-stop",
                "command": "stop",
                "session_id": session_id,
            },
            owner=owner,
            transport="direct",
        )
        assert stopped["state"]["session"] == "stopped"
        assert daemon.browser._tab_meta == {}
    finally:
        daemon._cleanup()
        thread.join(timeout=2)
        for path in (
            target.address,
            transport.pid_path(target.address),
            transport.lock_path(target.address),
        ):
            with contextlib.suppress(OSError):
                Path(path).unlink(missing_ok=True)
