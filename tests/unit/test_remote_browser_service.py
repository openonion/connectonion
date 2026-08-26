import json

from connectonion.network.host.remote_browser import RemoteBrowserService


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
        raise AssertionError(line)


def service(tmp_path, daemon=None):
    daemon = daemon or Daemon()
    return (
        RemoteBrowserService(
            tmp_path / "sessions.json", daemon_request=daemon, clock=lambda: 1000
        ),
        daemon,
    )


def request(command, request_id="req-1", session_id=None, args=None):
    value = {"request_id": request_id, "command": command}
    if session_id is not None:
        value["session_id"] = session_id
    if args is not None:
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
    shared = remote.handle(
        request("start", args={"proxy": "shared"}),
        owner="0xalice",
        transport="direct",
    )
    navigation = remote.handle(
        request("open", request_id="req-open"),
        owner="0xalice",
        transport="direct",
    )
    assert shared["code"] == "REMOTE_SESSION_PROXY_LOCKED"
    assert navigation["code"] == "INVALID_ARGUMENT"
    assert daemon.calls == []


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
