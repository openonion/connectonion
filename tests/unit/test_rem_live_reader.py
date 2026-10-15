"""The live reader on this computer: owner-only by the token beside the Host's key,
loopback-only, and able to ask co ai for a translation it then polls."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from connectonion.network.host import rem_http
from connectonion.network.host.http_router import handle_http
from connectonion.rem import live_host, reader
from connectonion.rem.config import prepare

PAGE = "# Alice Chen\n\n## Facts\n- Role: founder [1]\n\n## Sources\n- [1] gmail:abc — intro\n"


@pytest.fixture
def host(tmp_path):
    root, identity = tmp_path / "rem", tmp_path / "co"
    prepare(root)
    identity.mkdir()
    (root / "people" / "alice-chen.md").write_text(PAGE)
    rem_http.TASKS.clear()
    return SimpleNamespace(root=root, routes={"rem_root": root, "identity_dir": identity},
                           token=live_host.reader_token(identity))


def call(routes, method, path, *, query=b"", cookie="", body=b"", client="127.0.0.1",
         host_header="127.0.0.1:8123", content_type="application/json"):
    headers = [[b"host", host_header.encode()], [b"content-type", content_type.encode()]]
    if cookie:
        headers.append([b"cookie", cookie.encode()])
    scope = {"type": "http", "method": method, "path": path, "query_string": query,
             "headers": headers, "client": (client, 50000)}
    sent = []

    async def receive():
        return {"body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    async def run():
        await handle_http(scope, receive, send, route_handlers=routes, storage=Mock(), trust="careful", start_time=0)
    asyncio.run(run())
    head = dict((k.decode(), v.decode()) for k, v in sent[0]["headers"])
    return sent[0]["status"], head, sent[1]["body"].decode()


def test_the_token_is_traded_for_a_strict_cookie_and_leaves_the_address_bar(host):
    status, head, _ = call(host.routes, "GET", "/rem", query=b"token=" + host.token.encode())
    assert status == 303 and head["location"] == "/rem"
    assert "HttpOnly" in head["set-cookie"] and "SameSite=Strict" in head["set-cookie"]
    status, head, page = call(host.routes, "GET", "/rem", cookie=f"co_rem={host.token}")
    assert status == 200 and head["x-frame-options"] == "DENY"
    assert '"live": true' in page and "Alice Chen" in page


@pytest.mark.parametrize("kwargs", [
    {},                                                   # no token at all
    {"query": b"token=wrong"},
    {"cookie": "co_rem=wrong"},
])
def test_without_the_owner_token_nothing_is_read(host, kwargs):
    status, _, body = call(host.routes, "GET", "/rem", **kwargs)
    assert status == 401 and "Alice" not in body and "co rem open" in body


@pytest.mark.parametrize("kwargs", [
    {"client": "192.168.1.20"},                           # another machine on the LAN
    {"host_header": "evil.example:8123"},                 # a rebound DNS name
])
def test_only_loopback_is_answered_even_with_the_token(host, kwargs):
    status, _, body = call(host.routes, "GET", "/rem", cookie=f"co_rem={host.token}", **kwargs)
    assert status == 404 and "Alice" not in body


def test_a_host_without_a_notebook_says_so(host):
    host.routes["rem_root"] = host.root / "missing"
    status, _, body = call(host.routes, "GET", "/rem", cookie=f"co_rem={host.token}")
    assert status == 404 and "co rem init" in body


def test_translate_validates_before_any_model_call(host, monkeypatch):
    monkeypatch.setattr("connectonion.rem.translate.translate", lambda *a: pytest.fail("model called"))
    cookie = f"co_rem={host.token}"
    ask = lambda payload, **kw: call(host.routes, "POST", "/rem/translate", cookie=cookie,
                                     body=json.dumps(payload).encode(), **kw)
    assert ask({"page": "people/alice-chen.md", "language": "zh"}, content_type="text/plain")[0] == 415
    assert ask({"page": "people/alice-chen.md", "language": "../x"})[0] == 400
    assert ask({"page": "config.yaml", "language": "zh"})[0] == 400
    assert ask({"page": "../secret.md", "language": "zh"})[0] == 400
    status, _, _ = call(host.routes, "POST", "/rem/translate", body=b'{"page":"people/alice-chen.md","language":"zh"}')
    assert status == 401


def test_translate_runs_once_and_is_polled_until_ready(host, monkeypatch):
    calls = []

    def fake(root, page, language):
        calls.append((page, language))
        return "# Alice Chen\n\n中文\n"
    monkeypatch.setattr("connectonion.rem.translate.translate", fake)
    body = json.dumps({"page": "people/alice-chen.md", "language": "zh"}).encode()
    cookie = f"co_rem={host.token}"

    async def poll():
        loop_calls = []
        for _ in range(50):
            scope = {"type": "http", "method": "POST", "path": "/rem/translate", "query_string": b"",
                     "client": ("127.0.0.1", 1), "headers": [[b"host", b"localhost:8123"],
                                                             [b"content-type", b"application/json"],
                                                             [b"cookie", cookie.encode()]]}
            sent = []

            async def receive():
                return {"body": body, "more_body": False}

            async def send(message):
                sent.append(message)
            await rem_http.handle_rem_http(scope, receive, send, host.routes)
            answer = json.loads(sent[1]["body"])
            loop_calls.append(answer["state"])
            if answer["state"] != "running":
                return loop_calls, answer
            await asyncio.sleep(0.01)
    states, answer = asyncio.run(poll())
    assert states[0] == "running" and answer == {"state": "ready", "text": "# Alice Chen\n\n中文\n"}
    assert calls == [("people/alice-chen.md", "zh")] and rem_http.TASKS == {}


def test_a_failed_translation_is_reported_then_can_be_asked_again(host, monkeypatch):
    from connectonion.rem.files import RemError

    def fail(root, page, language):
        raise RemError("Codex is not signed in; run `codex login` and translate again")
    monkeypatch.setattr("connectonion.rem.translate.translate", fail)

    async def twice():
        first = rem_http._progress(host.root, "people/alice-chen.md", "zh")
        while (answer := rem_http._progress(host.root, "people/alice-chen.md", "zh"))["state"] == "running":
            await asyncio.sleep(0.01)
        return first, answer, rem_http._progress(host.root, "people/alice-chen.md", "zh")
    first, failed, again = asyncio.run(twice())
    assert first["state"] == "running" and "codex login" in failed["error"] and again["state"] == "running"


def test_the_reader_token_is_private_and_stable(tmp_path):
    token = live_host.reader_token(tmp_path)
    assert len(token) >= 32 and live_host.reader_token(tmp_path) == token
    if live_host.os.name != "nt":
        assert (tmp_path / "rem-reader-token").stat().st_mode & 0o777 == 0o600


def test_bare_open_starts_the_local_reader(tmp_path, monkeypatch):
    monkeypatch.setattr(live_host, "ensure_local", lambda address: ("http://127.0.0.1:9/rem?token=t", None))
    opened = []
    monkeypatch.setattr(reader.webbrowser, "open", opened.append)
    result = reader.local_or_snapshot(tmp_path, "owner", launch=True)
    assert opened == ["http://127.0.0.1:9/rem?token=t"] and result["page"] == "http://127.0.0.1:9/rem"


def test_bare_open_falls_back_to_the_snapshot_and_says_why(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr(live_host, "ensure_local", lambda address: (None, "co ai exited during startup"))
    result = reader.local_or_snapshot(tmp_path, "owner", launch=False)
    # The snapshot the owner asked to see still opens: a fallback, not a failure.
    assert result["link"].startswith("file://") and "live_startup_failed" not in result
    assert "co ai exited during startup" in result["live"]
    unowned = reader.local_or_snapshot(tmp_path, None, launch=False)
    assert unowned["link"].startswith("file://") and "default notebook" in unowned["live"]


def test_ensure_local_uses_a_running_host_and_never_starts_a_second(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: tmp_path)
    live_host.write_json(tmp_path / "rem-live-host.json", {"address": "owner", "pid": 1, "port": 9123})
    monkeypatch.setattr(live_host, "answers", lambda port, address: port == 9123)
    monkeypatch.setattr(live_host, "ensure_online", lambda address: pytest.fail("started a Host"))
    url, failure = live_host.ensure_local("owner")
    assert failure is None and url == f"http://127.0.0.1:9123/rem?token={live_host.reader_token(tmp_path)}"


def test_ensure_local_starts_co_ai_when_nothing_answers(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: tmp_path)
    started = []

    def online(address):
        started.append(address)
        live_host.write_json(tmp_path / "rem-live-host.json", {"address": address, "pid": 1, "port": 9124})
    monkeypatch.setattr(live_host, "ensure_online", online)
    monkeypatch.setattr(live_host, "answers", lambda port, address: bool(started) and port == 9124)
    url, failure = live_host.ensure_local("owner")
    assert started == ["owner"] and url.startswith("http://127.0.0.1:9124/rem?token=")


def test_a_host_on_an_unknown_port_is_named_not_duplicated(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: tmp_path)
    monkeypatch.setattr(live_host, "ensure_online", lambda address: None)
    monkeypatch.setattr(live_host, "answers", lambda port, address: False)
    url, failure = live_host.ensure_local("owner")
    assert url is None and "co rem open --live" in failure


def test_the_rem_path_is_reserved_from_publisher_routes():
    from connectonion.network.host.http_routes import _RESERVED_PREFIXES
    assert "/rem" in _RESERVED_PREFIXES
