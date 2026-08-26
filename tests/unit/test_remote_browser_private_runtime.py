"""Isolation and launch contracts for the Host-private browser runtime."""

import contextlib
import json
import os
import stat
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from connectonion.cli.browser_agent import client, transport
from connectonion.cli.browser_agent.daemon import BrowserDaemon
from connectonion.network.host.egress_gateway import ProxyEndpoint
from connectonion.network.host.private_browser_runtime import (
    PROXY_AUTH_REALM,
    REMOTE_BROWSER_CHROME_ARGS,
    PrivateBrowserTarget,
    canonical_proxy_auth,
    proxy_auth_path_for_profile,
    remote_browser_launch_policy,
    write_proxy_auth_file,
)
from connectonion.network.host.remote_browser import RemoteBrowserService
from connectonion.useful_tools.browser_tools import _async_browser as async_browser
from connectonion.useful_tools.browser_tools.launch_policy import BrowserProxySettings
from connectonion.useful_tools.browser_tools.native_egress import (
    NativeEgressPreflightError,
)


class LifecycleBrowser:
    def __init__(self, *, headless=True, launch_policy=None, events=None):
        self._headless = headless
        self.launch_policy = launch_policy
        self.events = events
        self._tab_meta = {}
        self._pages = {}

    def _bind_session(self, session):
        self.session = session

    def close_tab(self, name):
        self._tab_meta.pop(name, None)
        return f"Closed tab {name}"

    async def close(self):
        if self.events is not None:
            self.events.append("browser.stop")


class RecordingGateway:
    def __init__(self, events, password="A" * 43):
        self.events = events
        self.endpoint = ProxyEndpoint("127.0.0.1", 43123, "connectonion", password)
        self.is_running = False

    async def start(self):
        self.events.append("gateway.start")
        self.is_running = True
        return self.endpoint

    async def stop(self):
        self.events.append("gateway.stop")
        self.is_running = False


def _wait_for_daemon(address):
    deadline = time.time() + 5
    while time.time() < deadline:
        if Path(transport.pid_path(address)).exists():
            return
        time.sleep(0.02)
    raise RuntimeError("daemon did not bind")


def test_private_target_is_stable_short_and_separate_from_local(tmp_path, monkeypatch):
    monkeypatch.setattr(transport, "IS_WINDOWS", False)
    monkeypatch.setattr(transport, "_sidecar_dir", lambda: tmp_path / "ipc")
    short_root = tmp_path / "fallback"
    monkeypatch.setattr(transport, "_SHORT_RUNTIME_ROOT", short_root)
    state = tmp_path / ("deep-" * 40) / ".co" / "sessions.json"

    first = PrivateBrowserTarget.from_state_path(state)
    second = PrivateBrowserTarget.from_state_path(state)
    other = PrivateBrowserTarget.from_state_path(state.parent / "other-sessions.json")

    assert first == second
    assert first.address != other.address
    assert first.address != transport.default_address()
    assert Path(first.address).is_relative_to(short_root)
    assert first.profile_dir != other.profile_dir
    assert first.log_path.parent == first.authkey_path.parent
    assert first.proxy_auth_path == first.profile_dir.parent / "proxy-auth.json"
    assert transport.pid_path(first.address) != transport.pid_path(transport.default_address())
    assert transport.lock_path(first.address) != transport.lock_path(transport.default_address())
    if os.name != "nt":
        assert first.profile_dir.parent.stat().st_mode & 0o777 == 0o700
        assert Path(first.address).parent.stat().st_mode & 0o777 == 0o700


def test_windows_namespaces_include_user_and_stable_digest(monkeypatch):
    monkeypatch.setattr(transport, "IS_WINDOWS", True)
    monkeypatch.setattr(transport, "_current_user", lambda: "alice")

    one = transport.namespaced_address("host-one")
    two = transport.namespaced_address("host-two")

    assert one.startswith(r"\\.\pipe\co-browser-")
    assert one == transport.namespaced_address("host-one")
    assert one != two


def test_launch_policy_is_fixed_fail_closed_and_secret_safe(tmp_path):
    password = "A" * 43
    endpoint = ProxyEndpoint("127.0.0.1", 43123, "connectonion", password)
    auth_file = tmp_path / "proxy-auth.json"
    policy = remote_browser_launch_policy(tmp_path / "profile", endpoint, auth_file)
    options = policy.playwright_options()

    assert options["proxy"] == {"server": "http://127.0.0.1:43123"}
    assert options["service_workers"] == "block"
    assert options["accept_downloads"] is True
    assert policy.native_preflight == "remote-egress-v1"
    assert tuple(options["args"][:-1]) == REMOTE_BROWSER_CHROME_ARGS
    assert options["args"][-1] == f"--connectonion-proxy-auth-file={auth_file}"
    assert "--proxy-bypass-list=<-loopback>" in options["args"]
    assert "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1" in options["args"]
    assert "--disable-quic" in options["args"]
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in options["args"]
    assert "--disable-extensions" in options["args"]
    assert "direct" not in options["proxy"]["server"].lower()
    assert password not in repr(endpoint)
    assert password not in repr(policy)
    assert password not in repr(options)


def test_proxy_auth_file_matches_native_contract_and_is_private(tmp_path):
    password = "A" * 43
    endpoint = ProxyEndpoint("127.0.0.1", 43123, "connectonion", password)
    auth_file = tmp_path / "proxy-auth.json"

    written = write_proxy_auth_file(auth_file, endpoint)

    assert written == auth_file
    assert json.loads(auth_file.read_text(encoding="ascii")) == {
        "challenger": "127.0.0.1:43123",
        "password": password,
        "realm": PROXY_AUTH_REALM,
        "scheme": "basic",
        "username": "connectonion",
        "v": 1,
    }
    assert auth_file.read_bytes() == canonical_proxy_auth(endpoint)
    assert list(tmp_path.iterdir()) == [auth_file]
    if os.name != "nt":
        assert stat.S_IMODE(auth_file.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "endpoint",
    (
        ProxyEndpoint("localhost", 43123, "connectonion", "A" * 43),
        ProxyEndpoint("127.0.0.1", 0, "connectonion", "A" * 43),
        ProxyEndpoint("127.0.0.1", 43123, "other", "A" * 43),
        ProxyEndpoint("127.0.0.1", 43123, "connectonion", "short"),
    ),
)
def test_proxy_auth_file_rejects_noncanonical_native_credentials(tmp_path, endpoint):
    with pytest.raises(ValueError, match="native proxy credentials are not canonical"):
        write_proxy_auth_file(tmp_path / "proxy-auth.json", endpoint)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX private-directory modes")
def test_proxy_auth_file_rejects_public_parent(tmp_path):
    os.chmod(tmp_path, 0o755)

    with pytest.raises(ValueError, match="root must be private"):
        write_proxy_auth_file(
            tmp_path / "proxy-auth.json",
            ProxyEndpoint("127.0.0.1", 43123, "connectonion", "A" * 43),
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "server",
    (
        "https://127.0.0.1:43123",
        "http://localhost:43123",
        "http://127.0.0.1:43123/path",
        "http://127.0.0.1:43123@public.example",
        "http://127.0.0.1:43123,direct://",
    ),
)
def test_launch_proxy_rejects_every_noncanonical_or_fallback_server(server):
    with pytest.raises(ValueError, match="canonical loopback"):
        BrowserProxySettings(server)


@pytest.mark.asyncio
async def test_daemon_starts_gateway_before_browser_and_stops_it_after_browser(
    tmp_path,
):
    events = []
    gateway = RecordingGateway(events)

    def browser_factory(**kwargs):
        events.append("browser.create")
        return LifecycleBrowser(events=events, **kwargs)

    daemon = BrowserDaemon(
        str(tmp_path / "private.sock"),
        headless=True,
        profile_dir=tmp_path / "profile",
        remote_egress=True,
        gateway_factory=lambda: gateway,
        browser_factory=browser_factory,
    )

    await daemon._prepare_runtime()
    assert events == ["gateway.start", "browser.create"]
    assert daemon.browser.launch_policy.profile_dir == (tmp_path / "profile").resolve()
    auth_file = proxy_auth_path_for_profile(tmp_path / "profile")
    assert auth_file.is_file()
    assert gateway.endpoint.password in auth_file.read_text(encoding="ascii")
    assert gateway.endpoint.password not in repr(daemon.browser.launch_policy)
    await daemon._prepare_runtime()
    assert events == ["gateway.start", "browser.create"]
    await daemon._shutdown_async()
    assert events == [
        "gateway.start",
        "browser.create",
        "browser.stop",
        "gateway.stop",
    ]
    assert not auth_file.exists()


@pytest.mark.asyncio
async def test_browser_construction_failure_closes_gateway_before_ipc_bind(tmp_path):
    events = []
    gateway = RecordingGateway(events)

    def fail_browser(**_kwargs):
        events.append("browser.fail")
        raise RuntimeError("launch policy rejected")

    daemon = BrowserDaemon(
        str(tmp_path / "never-bound.sock"),
        profile_dir=tmp_path / "profile",
        remote_egress=True,
        gateway_factory=lambda: gateway,
        browser_factory=fail_browser,
    )
    with pytest.raises(RuntimeError, match="launch policy rejected"):
        await daemon._prepare_runtime()

    assert events == ["gateway.start", "browser.fail", "gateway.stop"]
    assert not proxy_auth_path_for_profile(tmp_path / "profile").exists()
    assert not Path(daemon.sock_path).exists()
    assert not Path(transport.pid_path(daemon.sock_path)).exists()


@pytest.mark.asyncio
async def test_gateway_loss_rejects_lifecycle_before_browser_mutation(tmp_path):
    events = []
    gateway = RecordingGateway(events)
    daemon = BrowserDaemon(
        str(tmp_path / "private.sock"),
        profile_dir=tmp_path / "profile",
        remote_egress=True,
        gateway_factory=lambda: gateway,
        browser_factory=LifecycleBrowser,
    )
    await daemon._prepare_runtime()
    gateway.is_running = False

    ok, message = await daemon.dispatch_async("tab open remote --who alice --for remote-browser")

    assert ok is False
    assert message == "EGRESS_GATEWAY_UNAVAILABLE"
    assert daemon.browser._tab_meta == {}
    await daemon._shutdown_async()


class FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False

    async def cookies(self):
        return []

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    async def close(self):
        self.closed = True


class FakePage:
    def is_closed(self):
        return False

    def set_default_navigation_timeout(self, _timeout):
        return None

    async def set_viewport_size(self, _viewport):
        return None


class FakePlaywright:
    def __init__(self):
        self.context = FakeContext()
        self.profile = None
        self.options = None
        self.stopped = False
        self.chromium = self

    async def launch_persistent_context(self, profile, **options):
        self.profile = profile
        self.options = options
        return self.context

    async def stop(self):
        self.stopped = True


class FailingLaunchPlaywright(FakePlaywright):
    def __init__(self, error):
        super().__init__()
        self.error = error

    async def launch_persistent_context(self, profile, **options):
        self.profile = profile
        self.options = options
        raise self.error


class FakeManager:
    def __init__(self, playwright):
        self.playwright = playwright

    async def start(self):
        return self.playwright


@pytest.mark.asyncio
async def test_async_core_uses_private_policy_not_environment_proxy(tmp_path, monkeypatch):
    playwright = FakePlaywright()
    preflight = AsyncMock()
    monkeypatch.setenv("BROWSER_PROXY", "http://environment.invalid:9999")
    monkeypatch.setattr(async_browser, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_browser, "async_playwright", lambda: FakeManager(playwright))
    monkeypatch.setattr(async_browser, "find_system_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(async_browser, "run_native_egress_preflight", preflight)
    policy = remote_browser_launch_policy(
        tmp_path / "private-profile",
        ProxyEndpoint("127.0.0.1", 43123, "connectonion", "A" * 43),
        tmp_path / "proxy-auth.json",
    )
    browser = async_browser.AsyncBrowserCore(headless=True, launch_policy=policy)

    await browser.open_browser()

    assert playwright.profile == str((tmp_path / "private-profile").resolve())
    assert playwright.options["proxy"]["server"] == "http://127.0.0.1:43123"
    assert "environment.invalid" not in repr(playwright.options)
    assert playwright.options["service_workers"] == "block"
    preflight.assert_awaited_once_with("remote-egress-v1", playwright.context)
    await browser.close()


@pytest.mark.asyncio
async def test_ordinary_async_core_keeps_environment_proxy_compatibility(tmp_path, monkeypatch):
    playwright = FakePlaywright()
    preflight = AsyncMock()
    monkeypatch.setenv("BROWSER_PROXY", "http://local-proxy.example:8080")
    monkeypatch.setenv("CO_BROWSER_PROFILE_DIR", str(tmp_path / "local-profile"))
    monkeypatch.setattr(async_browser, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_browser, "async_playwright", lambda: FakeManager(playwright))
    monkeypatch.setattr(async_browser, "find_system_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(async_browser, "run_native_egress_preflight", preflight)
    browser = async_browser.AsyncBrowserCore(headless=True)

    await browser.open_browser()

    assert playwright.profile == str((tmp_path / "local-profile").resolve())
    assert playwright.options["proxy"]["server"] == "http://local-proxy.example:8080"
    assert "service_workers" not in playwright.options
    preflight.assert_not_awaited()
    await browser.close()


@pytest.mark.asyncio
async def test_native_preflight_failure_closes_partial_context_and_driver(
    tmp_path, monkeypatch
):
    playwright = FakePlaywright()
    preflight = AsyncMock(
        side_effect=RuntimeError(
            f"driver echoed --connectonion-proxy-auth-file={tmp_path}/proxy-auth.json"
        )
    )
    monkeypatch.setattr(async_browser, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_browser, "async_playwright", lambda: FakeManager(playwright))
    monkeypatch.setattr(async_browser, "find_system_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(async_browser, "run_native_egress_preflight", preflight)
    policy = remote_browser_launch_policy(
        tmp_path / "private-profile",
        ProxyEndpoint("127.0.0.1", 43123, "connectonion", "A" * 43),
        tmp_path / "proxy-auth.json",
    )
    browser = async_browser.AsyncBrowserCore(headless=True, launch_policy=policy)

    with pytest.raises(NativeEgressPreflightError) as raised:
        await browser.open_browser()

    assert str(raised.value) == (
        "EGRESS_PREFLIGHT_FAILED: native browser egress boundary could not be proven"
    )
    assert str(tmp_path) not in str(raised.value)
    assert browser.browser is None
    assert browser.playwright is None
    assert playwright.context.closed is True
    assert playwright.stopped is True


@pytest.mark.asyncio
async def test_private_driver_launch_error_cannot_echo_auth_path(tmp_path, monkeypatch):
    auth_file = tmp_path / "proxy-auth.json"
    playwright = FailingLaunchPlaywright(
        RuntimeError(f"failed argv --connectonion-proxy-auth-file={auth_file}")
    )
    preflight = AsyncMock()
    monkeypatch.setattr(async_browser, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_browser, "async_playwright", lambda: FakeManager(playwright))
    monkeypatch.setattr(async_browser, "find_system_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(async_browser, "run_native_egress_preflight", preflight)
    policy = remote_browser_launch_policy(
        tmp_path / "private-profile",
        ProxyEndpoint("127.0.0.1", 43123, "connectonion", "A" * 43),
        auth_file,
    )
    browser = async_browser.AsyncBrowserCore(headless=True, launch_policy=policy)

    with pytest.raises(NativeEgressPreflightError) as raised:
        await browser.open_browser()

    assert str(raised.value) == (
        "EGRESS_PREFLIGHT_FAILED: native browser egress boundary could not be proven"
    )
    assert str(auth_file) not in str(raised.value)
    assert browser.browser is None
    assert browser.playwright is None
    assert playwright.context.closed is False
    assert playwright.stopped is True
    preflight.assert_not_awaited()


def test_default_remote_service_targets_private_daemon(tmp_path, monkeypatch):
    calls = []

    def request_target_as(target, line, **identity):
        calls.append((target, line, identity))
        return 0, line.split()[2]

    monkeypatch.setattr(client, "request_target_as", request_target_as)
    state_path = tmp_path / ".co" / "remote-browser-sessions.json"
    service = RemoteBrowserService(state_path, clock=lambda: 1000)
    result = service.handle(
        {
            "request_id": "private-start",
            "command": "start",
            "args": {"proxy": "direct", "headless": True},
        },
        owner="0xalice",
        transport="direct",
    )

    assert result["ok"] is True
    target, _, identity = calls[0]
    assert target == service.daemon_target
    assert target.remote_egress is True
    assert target.profile_dir != Path.home() / ".co" / "browser_profile"
    assert target.address != transport.default_address()
    assert identity["caller"] == identity["account"] == "0xalice"
    assert "password" not in service.state_path.read_text(encoding="utf-8")


def test_private_spawn_argv_and_log_never_contain_gateway_secret(tmp_path, monkeypatch):
    target = PrivateBrowserTarget(
        address=transport.namespaced_address(f"spawn-{time.time_ns()}"),
        profile_dir=tmp_path / "profile",
        log_path=tmp_path / "private.log",
        authkey_path=tmp_path / "authkey",
    )
    spawned = []
    connection = object()
    monkeypatch.setattr(
        transport,
        "spawn_detached",
        lambda command, _log: spawned.append(tuple(command)),
    )
    monkeypatch.setattr(
        client,
        "_connect",
        lambda _address, authkey_path=None: connection,
    )

    result = client._spawn_daemon(target.address, True, target=target)

    assert result is connection
    command = spawned[0]
    assert "--remote-egress" in command
    assert command[command.index("--profile-dir") + 1] == str(target.profile_dir)
    assert command[command.index("--authkey-file") + 1] == str(target.authkey_path)
    assert "gateway-secret" not in repr(command)
    assert target.log_path.read_text(encoding="utf-8") == ""


def test_local_and_private_native_daemons_run_and_stop_independently(tmp_path):
    local_address = transport.namespaced_address(f"test-local-{time.time_ns()}")
    local_target = PrivateBrowserTarget(
        address=local_address,
        profile_dir=tmp_path / "local-profile",
        log_path=tmp_path / "local.log",
        authkey_path=tmp_path / "local-authkey",
        remote_egress=False,
    )
    private_target = PrivateBrowserTarget.from_state_path(tmp_path / ".co" / "remote-browser-sessions.json")
    local = BrowserDaemon(local_address, headless=True, authkey_path=local_target.authkey_path)
    local.browser = LifecycleBrowser()
    private = BrowserDaemon(
        private_target.address,
        headless=True,
        profile_dir=private_target.profile_dir,
        authkey_path=private_target.authkey_path,
        remote_egress=True,
        gateway_factory=lambda: RecordingGateway([]),
        browser_factory=LifecycleBrowser,
    )
    threads = [
        threading.Thread(target=local.serve, daemon=True),
        threading.Thread(target=private.serve, daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        _wait_for_daemon(local_address)
        _wait_for_daemon(private_target.address)
        local_code, local_tab = client.request_target_as(
            local_target,
            "tab open local --who alice --for local",
            caller="alice",
            account="0xalice",
            headless=True,
        )
        private_code, private_tab = client.request_target_as(
            private_target,
            "tab open remote --who alice --for remote-browser",
            caller="alice",
            account="0xalice",
            headless=True,
        )
        assert (local_code, local_tab) == (0, "local")
        assert (private_code, private_tab) == (0, "remote")
        assert set(local.browser._tab_meta) == {"local"}
        assert set(private.browser._tab_meta) == {"remote"}

        private._cleanup()
        threads[1].join(timeout=2)
        assert not threads[1].is_alive()
        assert threads[0].is_alive()
        assert set(local.browser._tab_meta) == {"local"}
    finally:
        local._cleanup()
        private._cleanup()
        for thread in threads:
            thread.join(timeout=2)
        for address in (local_address, private_target.address):
            for path in (
                address,
                transport.pid_path(address),
                transport.lock_path(address),
            ):
                with contextlib.suppress(OSError):
                    Path(path).unlink()
