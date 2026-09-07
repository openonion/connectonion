import json

from connectonion.network.host.remote_browser import RemoteBrowserService
from connectonion.network.proxy_egress import ShareEndpoint

UNSET = object()


class AttachedShare:
    """What the registry holds once a laptop's `co proxy share` has attached:
    the loopback gateway the host opened for that laptop's channel."""

    def __init__(self, owner, port=43123, password="secret-value"):
        self.owner = owner
        self.endpoint = ShareEndpoint("127.0.0.1", port, "laptop", password)


def attach(remote, owner, **kwargs):
    remote.proxy_channels.attach(AttachedShare(owner, **kwargs))


class Daemon:
    def __init__(self):
        self.calls = []

    def __call__(self, line, **identity):
        self.calls.append((line, identity))
        tokens = line.split()
        if tokens[:2] == ["tab", "open"]:
            return 0, tokens[2]
        if tokens[:2] == ["tab", "close"]:
            return 0, f"Closed tab {tokens[2]}"
        if tokens == ["close"]:
            return 0, "Browser closed"
        raise AssertionError(line)


def service(tmp_path, daemon=None):
    daemon = daemon or Daemon()
    return (
        RemoteBrowserService(
            tmp_path / "sessions.json", daemon_request=daemon, clock=lambda: 1000
        ),
        daemon,
    )


def request(command, request_id="req-1", session_id=None, args=UNSET):
    value = {"request_id": request_id, "command": command}
    if session_id is not None:
        value["session_id"] = session_id
    if args is not UNSET:
        value["args"] = args
    return value


def test_start_is_idempotent_and_uses_authenticated_owner(tmp_path):
    remote, daemon = service(tmp_path)
    first = remote.handle(
        request("start", args={"proxy": "direct", "headless": True}),
        owner="0xalice",
        transport="direct",
    )
    retry = remote.handle(
        request("start", args={"proxy": "direct", "headless": True}),
        owner="0xalice",
        transport="direct",
    )

    assert first == retry
    assert first["ok"] is True
    assert first["result"]["session_id"].startswith("rb_")
    assert first["result"]["proxy_mode"] == "direct"
    assert len(daemon.calls) == 1
    _, identity = daemon.calls[0]
    assert identity["caller"] == identity["account"] == "0xalice"
    saved = json.loads((tmp_path / "sessions.json").read_text())
    assert len(saved["sessions"]) == 1
    assert "0xalice" not in repr(first)


def test_session_id_is_not_authority(tmp_path):
    remote, _ = service(tmp_path)
    started = remote.handle(request("start"), owner="0xalice", transport="direct")
    session_id = started["result"]["session_id"]

    for command in ("status", "diagnose", "stop"):
        result = remote.handle(
            request(command, request_id=f"req-{command}", session_id=session_id),
            owner="0xbob",
            transport="direct",
        )
        assert result["code"] == "REMOTE_SESSION_NOT_FOUND"
        assert session_id not in repr(result)

    listed = remote.handle(
        request("sessions", request_id="req-list"),
        owner="0xbob",
        transport="direct",
    )
    assert listed["result"]["sessions"] == []


def test_owner_can_reconnect_from_a_new_service_instance(tmp_path):
    first, daemon = service(tmp_path)
    started = first.handle(request("start"), owner="0xalice", transport="direct")
    session_id = started["result"]["session_id"]

    reconnected = RemoteBrowserService(
        tmp_path / "sessions.json", daemon_request=daemon, clock=lambda: 1001
    )
    status = reconnected.handle(
        request("status", request_id="req-status", session_id=session_id),
        owner="0xalice",
        transport="direct",
    )
    assert status["ok"] is True
    assert status["state"]["session"] == "active"


def test_restart_releases_sessions_when_the_browser_daemon_is_gone(tmp_path):
    first = RemoteBrowserService(tmp_path / "sessions.json")
    first.daemon_request = Daemon()
    attach(first, "0xalice", port=43123, password="old-proxy")
    started = first.handle(
        request("start", args={"proxy": "shared"}),
        owner="0xalice",
        transport="direct",
    )
    assert first.daemon_target.shared_proxy_path.is_file()

    restarted = RemoteBrowserService(tmp_path / "sessions.json", clock=lambda: 1001)
    restarted.daemon_request = Daemon()
    attach(restarted, "0xalice", port=43999, password="new-proxy")
    assert not restarted.daemon_target.shared_proxy_path.exists()

    replacement = restarted.handle(
        request("start", request_id="req-replacement", args={"proxy": "shared"}),
        owner="0xalice",
        transport="direct",
    )

    assert replacement["ok"] is True
    saved = json.loads((tmp_path / "sessions.json").read_text())
    assert saved["sessions"][started["result"]["session_id"]]["status"] == "stopped"
    assert saved["sessions"][replacement["result"]["session_id"]]["status"] == "active"


def test_stop_is_idempotent_and_keeps_a_tombstone(tmp_path):
    remote, daemon = service(tmp_path)
    started = remote.handle(request("start"), owner="0xalice", transport="direct")
    session_id = started["result"]["session_id"]

    first = remote.handle(
        request("stop", request_id="req-stop-1", session_id=session_id),
        owner="0xalice",
        transport="direct",
    )
    retry = remote.handle(
        request("stop", request_id="req-stop-2", session_id=session_id),
        owner="0xalice",
        transport="direct",
    )
    assert first["state"]["session"] == retry["state"]["session"] == "stopped"
    assert len([call for call in daemon.calls if call[0].startswith("tab close")]) == 1


def test_relay_fails_before_daemon_or_registry_mutation(tmp_path):
    remote, daemon = service(tmp_path)
    result = remote.handle(request("start"), owner="0xalice", transport="relay")
    assert result["code"] == "SECURE_CHANNEL_UNAVAILABLE"
    assert result["state"]["fallback_applied"] is False
    assert daemon.calls == []
    assert not (tmp_path / "sessions.json").exists()


def test_non_direct_proxy_and_navigation_are_not_silently_enabled(tmp_path):
    remote, daemon = service(tmp_path)
    # `shared` is a real mode now, but it cannot be assumed: the caller's
    # computer has to be attached to this host (`co proxy share`) first. Asking
    # for shared egress without one must not quietly fall back to this host's
    # address — that would send traffic from the data centre while the caller
    # believed it left from home.
    shared = remote.handle(
        request("start", args={"proxy": "shared"}),
        owner="0xalice",
        transport="direct",
    )
    unknown = remote.handle(
        request("start", args={"proxy": "tor"}, request_id="req-tor"),
        owner="0xalice",
        transport="direct",
    )
    navigation = remote.handle(
        request("open", request_id="req-open"),
        owner="0xalice",
        transport="direct",
    )
    assert shared["code"] == "REMOTE_SESSION_PROXY_NOT_ATTACHED"
    assert shared["next_actions"][0]["command"] == "co proxy share"
    assert unknown["code"] == "REMOTE_SESSION_PROXY_LOCKED"
    assert navigation["code"] == "INVALID_ARGUMENT"
    assert daemon.calls == []


def test_shared_start_pins_the_laptop_proxy_without_persisting_its_secret(tmp_path):
    daemon = Daemon()
    remote = RemoteBrowserService(tmp_path / "sessions.json")
    remote.daemon_request = daemon
    attach(remote, "0xalice")
    attach(remote, "0xbob", port=43999, password="bobs")

    started = remote.handle(
        request("start", args={"proxy": "shared"}),
        owner="0xalice",
        transport="direct",
    )

    assert started["ok"] is True
    assert started["result"]["proxy_mode"] == "shared"
    assert "secret-value" not in repr(started)
    saved = json.loads((tmp_path / "sessions.json").read_text())
    session = next(iter(saved["sessions"].values()))
    assert session["proxy_mode"] == "shared"
    assert len(session["proxy_binding"]) == 64
    assert "secret-value" not in repr(saved)
    # The browser is pointed at the caller's own share, on this host's loopback.
    config = json.loads(remote.daemon_target.shared_proxy_path.read_text())
    assert config["host"] == "127.0.0.1"
    assert config["port"] == 43123
    assert config["password"] == "secret-value"

    stopped = remote.handle(
        request(
            "stop",
            request_id="req-stop-shared",
            session_id=started["result"]["session_id"],
        ),
        owner="0xalice",
        transport="direct",
    )
    assert stopped["ok"] is True
    assert not remote.daemon_target.shared_proxy_path.exists()
    assert daemon.calls[-1][0] == "close"


def test_failed_first_shared_start_leaves_no_stale_proxy_selection(tmp_path):
    remote = RemoteBrowserService(tmp_path / "sessions.json")

    def rejected(_line, **_identity):
        return 1, "browser rejected start"

    remote.daemon_request = rejected
    attach(remote, "0xalice")
    result = remote.handle(
        request("start", args={"proxy": "shared"}),
        owner="0xalice",
        transport="direct",
    )

    assert result["code"] == "REMOTE_BROWSER_UNAVAILABLE"
    assert not remote.daemon_target.shared_proxy_path.exists()
    assert not (tmp_path / "sessions.json").exists()


def test_one_wtf_runtime_cannot_mix_direct_and_shared_sessions(tmp_path):
    remote, daemon = service(tmp_path)
    first = remote.handle(request("start"), owner="0xalice", transport="direct")
    attach(remote, "0xbob")
    second = remote.handle(
        request("start", request_id="req-shared", args={"proxy": "shared"}),
        owner="0xbob",
        transport="direct",
    )

    assert first["ok"] is True
    assert second["code"] == "REMOTE_SESSION_PROXY_LOCKED"
    assert "WTF Browser" not in second["message"]
    assert "Remote Browser" in second["message"]
    assert len(daemon.calls) == 1


def test_explicit_non_object_args_are_rejected(tmp_path):
    remote, daemon = service(tmp_path)

    for index, args in enumerate((None, [], "", 0, False)):
        result = remote.handle(
            request("start", request_id=f"req-invalid-{index}", args=args),
            owner="0xalice",
            transport="direct",
        )
        assert result["code"] == "INVALID_ARGUMENT"
    assert daemon.calls == []


def test_different_owners_receive_distinct_daemon_tabs(tmp_path):
    remote, daemon = service(tmp_path)

    alice = remote.handle(
        request("start", request_id="req-alice"),
        owner="0xalice",
        transport="direct",
    )
    bob = remote.handle(
        request("start", request_id="req-bob"),
        owner="0xbob",
        transport="direct",
    )

    assert alice["result"]["session_id"] != bob["result"]["session_id"]
    opened = [line for line, _ in daemon.calls if line.startswith("tab open")]
    assert len(opened) == 2
    assert opened[0].split()[2] != opened[1].split()[2]

    remote.handle(
        request(
            "stop",
            request_id="req-stop-alice",
            session_id=alice["result"]["session_id"],
        ),
        owner="0xalice",
        transport="direct",
    )
    bob_status = remote.handle(
        request(
            "status",
            request_id="req-status-bob",
            session_id=bob["result"]["session_id"],
        ),
        owner="0xbob",
        transport="direct",
    )
    assert bob_status["state"]["session"] == "active"


def test_diagnose_states_the_incomplete_navigation_boundary(tmp_path):
    remote, _ = service(tmp_path)
    started = remote.handle(request("start"), owner="0xalice", transport="direct")
    result = remote.handle(
        request(
            "diagnose",
            request_id="req-diagnose",
            session_id=started["result"]["session_id"],
        ),
        owner="0xalice",
        transport="direct",
    )
    assert result["result"]["checks"]["navigation_policy"] == "not_enabled"
    assert result["warnings"]


def test_success_and_failure_envelopes_keep_stable_common_fields(tmp_path):
    remote, _ = service(tmp_path)
    success = remote.handle(
        request("sessions"), owner="0xalice", transport="direct"
    )
    failure = remote.handle(
        request("sessions", request_id="req-relay"),
        owner="0xalice",
        transport="relay",
    )

    common = {
        "schema_version",
        "ok",
        "command",
        "request_id",
        "state",
        "tips",
        "warnings",
        "next_actions",
    }
    assert common <= success.keys()
    assert common <= failure.keys()
