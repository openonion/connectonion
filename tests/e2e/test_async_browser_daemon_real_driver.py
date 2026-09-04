"""Installed/native acceptance for #499's complete daemon-to-driver path.

Run explicitly with the slow gate:

    python -m pytest tests/e2e/test_async_browser_daemon_real_driver.py -m slow -q
"""

import contextlib
import json
import os
import shlex
import threading
import time
import urllib.parse

import pytest

from connectonion.cli.browser_agent import client, daemon, transport
from connectonion.useful_tools.browser_tools._async_browser import (
    ASYNC_BROWSER_AVAILABLE,
    AsyncBrowserCore,
)


def endpoint() -> str:
    nonce = f"{os.getpid()}_{time.time_ns()}"
    if transport.IS_WINDOWS:
        return rf"\\.\pipe\co_async_native_{nonce}"
    return f"/tmp/co_async_native_{nonce}.sock"


@pytest.mark.slow
def test_real_daemon_keeps_a_second_tab_live_during_a_long_operation(
    tmp_path, monkeypatch
):
    if not ASYNC_BROWSER_AVAILABLE:
        pytest.skip("patchright async API is not installed")

    address = endpoint()
    monkeypatch.setenv("CO_BROWSER_SOCK", address)
    monkeypatch.setenv("CO_BROWSER_PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setattr(client, "_caller", lambda: "native-owner")
    server = daemon.BrowserDaemon(address, headless=True)
    server.browser = AsyncBrowserCore(
        headless=True,
        use_mock_keychain=True,
    )
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()

    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            if os.path.exists(transport.pid_path(address)):
                break
            time.sleep(0.02)
        else:
            raise AssertionError("daemon did not bind")

        for tab, marker in (("slow", "alpha"), ("live", "beta")):
            assert client._request(f"tab open {tab}", headless=True)[0] == 0
            url = "data:text/html," + urllib.parse.quote(
                f"<title>{marker}</title><main>{marker} page</main>"
            )
            code, payload = client._request(
                shlex.join(["go_to", url]), headless=True, tab=tab
            )
            assert code == 0, payload

        waiting = []
        worker = threading.Thread(
            target=lambda: waiting.append(
                client._request("wait 2", headless=True, tab="slow")
            )
        )
        worker.start()

        deadline = time.time() + 2
        while time.time() < deadline:
            code, payload = client._request("tab ls --json", headless=True)
            assert code == 0, payload
            slow = next(item for item in json.loads(payload) if item["tab"] == "slow")
            if slow["active_requests"]:
                break
            time.sleep(0.02)
        else:
            raise AssertionError("long operation never became active")

        started = time.monotonic()
        code, payload = client._request("get_text", headless=True, tab="live")
        elapsed = time.monotonic() - started

        assert code == 0, payload
        assert "beta page" in payload
        assert elapsed < 1.0
        assert (
            worker.is_alive()
        ), "the live-tab read waited for the two-second operation"
        worker.join(timeout=3)
        assert waiting == [(0, "Waited for 2.0 seconds")]

        code, payload = client._request("close", headless=True)
        assert code == 0, payload
        thread.join(timeout=3)
        assert not thread.is_alive()
    finally:
        server._cleanup()
        thread.join(timeout=3)
        for path in (
            address,
            transport.pid_path(address),
            transport.lock_path(address),
        ):
            with contextlib.suppress(OSError):
                if os.path.exists(path):
                    os.unlink(path)
