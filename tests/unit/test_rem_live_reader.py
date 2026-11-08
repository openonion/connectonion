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


def test_live_reader_reuses_its_page_until_notebook_or_template_changes(host, cache, clock, monkeypatch, tmp_path):
    # Since 2026-11-09 a change is served as the last page at once and rebuilt
    # behind it (reader.refresh is what the detached build runs), at most once
    # per REBUILD_INTERVAL. An edit REM did not make, in place, is found by the
    # background full check after FULL_CHECK_SECONDS; the open itself never walks.
    from connectonion.rem.files import Notebook, state_path
    builds, original = [], reader.snapshot

    def counted(root, **options):
        builds.append(options)
        return original(root, **options)
    monkeypatch.setattr(reader, 'snapshot', counted)
    template = tmp_path / 'reader-template.html'
    template.write_text('Example template /*__REM_DATA__*/null')
    monkeypatch.setattr(reader, 'TEMPLATE', template)
    get = lambda: call(host.routes, 'GET', '/rem', cookie=f'co_rem={host.token}')[2]
    page = get()
    assert get() == page and builds == [{'local': True, 'today': True}]
    reader.refresh(host.root)                       # the details the first request left behind it
    assert builds[1:] == [{'local': True}]
    changes = [
        ('Alice Chen-Vale', lambda: (host.root / 'people/alice-chen.md').write_text(PAGE.replace('Alice Chen', 'Alice Chen-Vale'))),
        ('Alice Chen-Vale', lambda: state_path(host.root, 'map.json').write_text('{"owner": {}}')),
        ('Nora', lambda: (host.root / 'people/nora.md').write_text('# Nora')),          # added by hand
        ('Alice Chen-Vale', lambda: (host.root / 'people/nora.md').unlink()),           # removed by hand
        ('Alice Chen-Vale', lambda: Notebook(host.root).write('people/fern-holt.md', '# Fern Holt\n')),
        ('Updated template', lambda: template.write_text('Updated template /*__REM_DATA__*/null')),
    ]
    for shown, change in changes:
        change()
        clock[0] += reader.REBUILD_INTERVAL + 1
        cache.clear()
        builds.clear()
        assert get() == page and cache == [host.root] and builds == []   # the last page, a rebuild behind
        reader.refresh(host.root)
        assert builds == [{'local': True, 'today': True}, {'local': True}]
        page = get()
        assert shown in page and get() == page
    assert 'Nora' not in page
    # Authentication still runs for every request, including a cache hit.
    assert call(host.routes, 'GET', '/rem')[0] == 401


def test_live_reader_second_request_reuses_the_actual_snapshot(host, cache, monkeypatch):
    from connectonion.rem.store import refresh
    refresh(host.root)
    builds, original = [], reader.snapshot

    def counted(root, **options):
        builds.append(root)
        return original(root, **options)

    monkeypatch.setattr(reader, 'snapshot', counted)
    get = lambda: call(host.routes, 'GET', '/rem', cookie=f'co_rem={host.token}')[2]
    assert get() == get()
    assert builds == [host.root]


def test_lazy_notebook_data_is_authenticated_cached_and_invalidated(host, cache, clock, monkeypatch):
    calls, original = [], reader.snapshot

    def detail(root, **options):
        calls.append((root, options))
        data = original(root, **options)
        if 'today' not in options:
            data['conversations'] = {'example': {}}
        return data
    monkeypatch.setattr(reader, 'snapshot', detail)
    assert call(host.routes, 'GET', '/rem/data.json')[0] == 401
    assert call(host.routes, 'GET', '/rem/data.json', cookie=f'co_rem={host.token}',
                client='192.168.1.20')[0] == 404
    get = lambda: call(host.routes, 'GET', '/rem/data.json', cookie=f'co_rem={host.token}')
    status, headers, body = get()
    assert status == 200 and headers['content-type'].startswith('application/json')
    data = json.loads(body)
    assert data['conversations'] == {'example': {}} and 'Alice Chen' in json.dumps(data['records'])
    assert get()[2] == body and len(calls) == 1
    (host.root / 'people/alice-chen.md').write_text(PAGE + '\nChanged.')   # in place, not by REM
    cache.clear()
    assert get()[2] == body and cache == []          # the open never walks the notebook to see it
    clock[0] += reader.FULL_CHECK_SECONDS + 1
    assert get()[2] == body and cache == [host.root]  # the background full check is due
    reader.refresh(host.root, ['full'])
    assert len(calls) == 2 and 'Changed.' in get()[2]
    assert all(options == {'local': True} for _, options in calls)


def test_task_refresh_is_owner_only_and_reads_the_receipt(host):
    from connectonion.rem import tasks
    from connectonion.rem.files import write_json
    from pathlib import Path
    receipt = tasks.reserve(host.root, {'key': 'people/fern.md\nReview the pilot.',
        'keys': ['people/fern.md\nReview the pilot.'], 'record': 'people/fern.md',
        'title': 'Fern Vale', 'text': 'Review the pilot.', 'task': {'prompt': 'Review it.'}})
    write_json(Path(receipt['receipt']), {**receipt, 'result': 'failed', 'exit_code': 1})
    body = json.dumps({'id': receipt['id']}).encode()
    assert call(host.routes, 'POST', '/rem/task', body=body)[0] == 401
    status, _, text = call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=body)
    assert status == 200 and json.loads(text)['result'] == 'failed'
    assert call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=b'{}')[0] == 400


def test_task_stop_and_undo_go_through_the_owner_endpoint(host, monkeypatch):
    from connectonion.rem import tasks
    calls = []
    monkeypatch.setattr(tasks, 'stop', lambda root, task_id: calls.append(('stop', task_id)) or {'result': 'stopped'})
    monkeypatch.setattr(tasks, 'undo', lambda root, task_id: calls.append(('undo', task_id)) or {'status': 'cancelled'})
    task_id = 'a' * 32
    for action, expected in (('stop', {'result': 'stopped'}), ('undo', {'status': 'cancelled'})):
        body = json.dumps({'id': task_id, 'action': action}).encode()
        assert call(host.routes, 'POST', '/rem/task', body=body)[0] == 401
        status, _, text = call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=body)
        assert status == 200 and json.loads(text) == expected
    assert calls == [('stop', task_id), ('undo', task_id)]
    body = json.dumps({'id': task_id, 'action': 'push'}).encode()
    assert call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=body)[0] == 400


@pytest.fixture
def clock(monkeypatch):
    """The reader's own clock, moved by the test: [seconds since the epoch]."""
    now = [1_794_000_000.0]
    monkeypatch.setattr(reader, "_now", lambda: now[0], raising=False)
    return now


@pytest.fixture
def cache(tmp_path, monkeypatch, clock):
    """The reader's saved pages land in this test's own temporary folder."""
    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path / "tmp"))
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    spawned = []
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: spawned.append(root), raising=False)
    return spawned


def test_live_reader_serves_the_last_page_while_a_newer_one_builds(host, cache, clock):
    from connectonion.rem.files import Notebook
    cookie = f"co_rem={host.token}"
    get = lambda: call(host.routes, "GET", "/rem", cookie=cookie)[2]
    first = get()
    assert "Alice Chen" in first
    version = call(host.routes, "GET", "/rem/version", cookie=cookie)
    assert version[0] == 200 and json.loads(version[2])["as_of"] in first
    clock[0] += reader.REBUILD_INTERVAL
    Notebook(host.root).write("people/bruno-vale.md", "# Bruno Vale\n")
    cache.clear()
    assert get() == first and cache == [host.root]   # instantly the last page, a rebuild behind it
    reader.refresh(host.root)
    Notebook(host.root).write("people/bruno-vale.md", "# Bruno Vale, again\n")
    cache.clear()
    assert get() != first and cache == []            # rebuilt a moment ago: the next waits
    reader.refresh(host.root)
    fresh = get()
    assert "Bruno Vale" in fresh
    # The open page learns a newer render has landed from this tiny, owner-only answer.
    assert json.loads(call(host.routes, "GET", "/rem/version", cookie=cookie)[2])["as_of"] in fresh
    assert call(host.routes, "GET", "/rem/version")[0] == 401


def test_a_dead_saved_host_does_not_hold_back_the_saved_page(host, cache, monkeypatch):
    import time
    identity = host.routes["identity_dir"]
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: identity)
    reader.open_snapshot(host.root, launch=False)                  # a page was saved before
    live_host.write_json(identity / "rem-live-host.json", {
        "address": "owner", "pid": 2 ** 22 + 7, "port": 9125, "command": "-m connectonion.cli.main ai"})
    monkeypatch.setattr(live_host, "answers", lambda port, address: False)
    monkeypatch.setattr(live_host, "ensure_online", lambda *a, **k: pytest.fail("waited for co ai to start"))
    started_hosts = []

    def spawn(directory):
        started_hosts.append(directory)
        return SimpleNamespace(pid=4242, args=["python", "-m", "connectonion.cli.main", "ai", "--port", "9126"])
    monkeypatch.setattr(live_host, "_spawn", spawn)
    started = time.monotonic()
    result = reader.local_or_snapshot(host.root, "owner", launch=False)
    assert time.monotonic() - started < 1.0
    assert result["link"].startswith("file://") and "Alice Chen" in open(result["page"], encoding="utf-8").read()
    assert started_hosts == [identity] and "co ai is starting" in result["live"]
    assert live_host.read_json(identity / "rem-live-host.json", {})["pid"] == 4242


def test_a_second_live_request_on_a_large_notebook_lists_no_directory(host, cache, monkeypatch):
    import glob
    import os
    import time
    for folder in range(200):
        directory = host.root / ".state" / "mail" / f"{folder:03}"
        directory.mkdir(parents=True)
        for item in range(100):
            (directory / f"{item}.json").write_text("{}")
    get = lambda: call(host.routes, "GET", "/rem", cookie=f"co_rem={host.token}")
    first = get()[2]
    reader.refresh(host.root)                      # the details it left to the background

    def listed(*args, **kwargs):
        raise AssertionError("an unchanged notebook was listed again")
    for name in ("walk", "scandir", "listdir"):
        monkeypatch.setattr(os, name, listed)
    monkeypatch.setattr(glob._StringGlobber, "scandir", staticmethod(listed))
    cache.clear()
    started = time.monotonic()
    status, _, second = get()
    assert time.monotonic() - started < 1.0
    assert status == 200 and second == first and cache == []


def test_rebuilds_wait_out_the_interval_unless_the_owner_acted_in_the_reader(host, cache, clock):
    """A night run keeps writing and a rebuild costs ~100 s of CPU on a real notebook."""
    from connectonion.rem.files import Notebook
    cookie = f"co_rem={host.token}"
    get = lambda: call(host.routes, "GET", "/rem", cookie=cookie)[2]
    get()
    reader.refresh(host.root)
    cache.clear()
    for minute in range(1, reader.REBUILD_INTERVAL // 60):          # the night run, writing
        clock[0] += 60
        Notebook(host.root).write("people/nora-pike.md", f"# Nora Pike\n\nPass {minute}.\n")
        get()
        assert call(host.routes, "GET", "/rem/version", cookie=cookie)[0] == 200
    assert cache == []                                              # nothing rebuilt yet
    clock[0] += 61
    get()
    assert cache == [host.root]                                     # the interval is over
    reader.refresh(host.root)
    cache.clear()
    clock[0] += 60
    payload = json.dumps({"key": "people/alice-chen.md\nA promise", "state": "done"}).encode()
    assert call(host.routes, "POST", "/rem/thread", cookie=cookie, body=payload)[0] == 200
    assert cache == [host.root]                                     # the owner's own action: now
