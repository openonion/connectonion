"""The live reader on this computer: owner-only by the token beside the Host's key,
loopback-only, and able to ask co ai for a translation it then polls."""

import asyncio
import json
import re
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import connectonion
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
    # D-60: the Host's own 401 page names no command either; it has no language, so English.
    assert status == 401 and "Alice" not in body and body == "This page's session has ended. Open REM again from your computer."


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
    monkeypatch.setattr(live_host, "ensure_local", lambda address, **k: ("http://127.0.0.1:9/rem?token=t", None))
    opened = []
    monkeypatch.setattr(reader.webbrowser, "open", opened.append)
    result = reader.local_or_snapshot(tmp_path, "owner", launch=True)
    assert opened == ["http://127.0.0.1:9/rem?token=t"] and result["page"] == "http://127.0.0.1:9/rem"


def test_bare_open_falls_back_to_the_snapshot_and_says_why(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr(live_host, "ensure_local", lambda address, **k: (None, "co ai exited during startup"))
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
    monkeypatch.setattr(live_host, "ensure_online", lambda address, **k: pytest.fail("started a Host"))
    url, failure = live_host.ensure_local("owner")
    assert failure is None and url == f"http://127.0.0.1:9123/rem?token={live_host.reader_token(tmp_path)}"


def test_ensure_local_starts_co_ai_when_nothing_answers(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: tmp_path)
    started = []

    def online(address, **k):
        started.append(address)
        live_host.write_json(tmp_path / "rem-live-host.json", {"address": address, "pid": 1, "port": 9124})
    monkeypatch.setattr(live_host, "ensure_online", online)
    monkeypatch.setattr(live_host, "answers", lambda port, address: bool(started) and port == 9124)
    url, failure = live_host.ensure_local("owner")
    assert started == ["owner"] and url.startswith("http://127.0.0.1:9124/rem?token=")


def test_a_host_on_an_unknown_port_is_named_not_duplicated(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: tmp_path)
    monkeypatch.setattr(live_host, "ensure_online", lambda address, **k: None)
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
    reader.refresh(host.root)                       # the details the first request left behind it,
    assert builds[1:] == [{'local': True, 'today': True}, {'local': True}]   # with the page: one render
    page = get()
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
        # The last page, a rebuild behind it; marked when the key shows it behind (a hand edit only the walk finds is not).
        assert get().replace(reader.UPDATING, "") == page and cache == [host.root] and builds == []
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
    clock[0] += reader.REBUILD_INTERVAL + 1
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


def test_a_hand_to_codex_or_claude_button_dispatches_any_pending_item(host, monkeypatch):
    from connectonion.rem import tasks
    calls = []
    monkeypatch.setattr(tasks, 'dispatch', lambda root, key, agent='codex': calls.append((key, agent)) or {'agent': agent, 'result': 'starting'})
    key = 'people/fern.md\nReview the pilot.'
    for agent in ('codex', 'claude'):
        body = json.dumps({'key': key, 'action': 'run', 'agent': agent}).encode()
        assert call(host.routes, 'POST', '/rem/task', body=body)[0] == 401
        status, _, text = call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=body)
        assert status == 200 and json.loads(text) == {'agent': agent, 'result': 'starting'}
    assert calls == [(key, 'codex'), (key, 'claude')]
    for bad in ({'key': key, 'action': 'run', 'agent': 'gemini'}, {'action': 'run', 'agent': 'claude'}):
        assert call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=json.dumps(bad).encode())[0] == 400


def test_a_key_no_unfinished_row_has_is_a_400_in_plain_words(host):
    body = json.dumps({'key': 'people/nobody.md\nNothing.', 'action': 'run', 'agent': 'codex'}).encode()
    status, _, text = call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=body)
    assert status == 400 and 'no longer open' in json.loads(text)['error']


def test_see_result_reads_what_the_agent_wrote(host):
    from connectonion.rem import tasks
    from connectonion.rem.files import write_json
    from pathlib import Path
    receipt = tasks.reserve(host.root, {'key': 'people/fern.md\nReview the pilot.',
        'keys': ['people/fern.md\nReview the pilot.'], 'record': 'people/fern.md',
        'title': 'Fern Vale', 'text': 'Review the pilot.', 'task': {'prompt': 'Review it.'}})
    body = json.dumps({'id': receipt['id'], 'action': 'result'}).encode()
    assert call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=body)[0] == 409  # still queued
    Path(receipt['deliverable']).write_text('# Pilot review\nFern can sign on Friday.\n')
    write_json(Path(receipt['receipt']), {**receipt, 'result': 'completed', 'exit_code': 0})
    status, _, text = call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=body)
    assert status == 200 and 'Fern can sign on Friday.' in json.loads(text)['text']


def test_talk_routes_are_owner_only_and_reach_the_conversation(host, monkeypatch):
    from connectonion.rem import conversations
    calls = []
    monkeypatch.setattr(conversations, 'begin', lambda root, agent, key=None, session=None:
                        calls.append(('begin', agent, key, session)) or {'id': 'a' * 32, 'state': 'working'})
    monkeypatch.setattr(conversations, 'say', lambda root, talk_id, text: calls.append(('say', talk_id, text)) or {'state': 'working'})
    monkeypatch.setattr(conversations, 'read', lambda root, talk_id: calls.append(('read', talk_id)) or {'state': 'idle'})
    for body in ({'action': 'begin', 'agent': 'claude', 'key': 'people/fern.md\nReview the pilot.'},
                 {'action': 'begin', 'session': 'sessions/fern.md'},
                 {'action': 'say', 'id': 'a' * 32, 'text': 'Draft it.'}, {'action': 'read', 'id': 'a' * 32}):
        raw = json.dumps(body).encode()
        assert call(host.routes, 'POST', '/rem/talk', body=raw)[0] == 401
        assert call(host.routes, 'POST', '/rem/talk', cookie=f'co_rem={host.token}', body=raw)[0] == 200
    assert calls == [('begin', 'claude', 'people/fern.md\nReview the pilot.', None), ('begin', 'codex', None, 'sessions/fern.md'),
                     ('say', 'a' * 32, 'Draft it.'), ('read', 'a' * 32)]
    for bad in ({'action': 'begin', 'agent': 'gemini', 'key': 'k'}, {'action': 'say', 'id': 'a' * 32}, {'action': 'push'}):
        assert call(host.routes, 'POST', '/rem/talk', cookie=f'co_rem={host.token}', body=json.dumps(bad).encode())[0] == 400


def test_a_snapshot_links_to_this_computers_live_reader_only_with_an_identity(host, monkeypatch):
    from connectonion import address
    identity = host.routes["identity_dir"]
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: identity)
    assert live_host.live_link() == ""                        # no key here: no live reader to link to
    address.save(address.generate(), identity)
    assert live_host.live_link() == f"http://127.0.0.1:8000/rem?token={host.token}"
    live_host.write_json(identity / "rem-live-host.json", {"port": 9125})
    assert live_host.live_link() == f"http://127.0.0.1:9125/rem?token={host.token}"


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
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: spawned.append(root) or True, raising=False)
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
    assert get() == reader._updating(first) and cache == [host.root]   # instantly the last page, a rebuild behind it
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

    def spawn(directory, port=None):
        started_hosts.append(directory)
        return SimpleNamespace(pid=4242, args=["python", "-m", "connectonion.cli.main", "ai", "--port", "9126"])
    monkeypatch.setattr(live_host, "_spawn", spawn)
    started = time.monotonic()
    result = reader.local_or_snapshot(host.root, "owner", launch=False)
    assert time.monotonic() - started < 1.0
    assert result["link"].startswith("file://") and "Alice Chen" in open(result["page"], encoding="utf-8").read()
    assert started_hosts == [identity] and result["live"] == live_host.STARTING
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
    get()
    reader.refresh(host.root)                      # the details it left to the background
    first = get()[2]

    def listed(*args, **kwargs):
        raise AssertionError("an unchanged notebook was listed again")
    for name in ("walk", "scandir", "listdir"):
        monkeypatch.setattr(os, name, listed)
    if hasattr(glob, "_StringGlobber"):  # 3.13+: pathlib's rglob bound os.scandir at import;
        monkeypatch.setattr(glob._StringGlobber, "scandir", staticmethod(listed))  # earlier calls os.scandir
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



def _review(root, kind="link"):
    from connectonion.rem import reviews
    (root / "people" / "noor-alvi.md").write_text("# Noor Alvi\n")
    subjects = ["people/alice-chen.md", "people/noor-alvi.md"] if kind == "link" else ["people/alice-chen.md"]
    return reviews.propose(root, kind, subjects, "Is Alice Chen the same person as Noor Alvi?", "Same phone in two signatures.")


def test_a_review_is_decided_from_the_page_by_the_owner_only(host, cache, clock):
    """问题与关联 decides in place: no terminal, no copied command (D-60)."""
    from connectonion.rem import reviews
    row = _review(host.root)
    body = json.dumps({"id": row["id"], "verdict": "yes", "response": "Same phone."}).encode()
    assert call(host.routes, "POST", "/rem/review", body=body)[0] == 401
    assert reviews.listing(host.root)[0]["status"] == "pending"
    call(host.routes, "GET", "/rem", cookie=f"co_rem={host.token}")
    reader.refresh(host.root)
    cache.clear()
    status, _, text = call(host.routes, "POST", "/rem/review", cookie=f"co_rem={host.token}", body=body)
    assert status == 200
    decided = json.loads(text)
    assert decided["id"] == row["id"] and decided["status"] == "accepted" and decided["author"] == "owner"
    saved = reviews.listing(host.root)[0]
    assert saved["status"] == "accepted" and saved["response"] == "Same phone." and saved["author"] == "owner"
    assert cache == [host.root]                                     # the page rebuilds now


def test_a_question_is_answered_with_the_owners_words(host):
    from connectonion.rem import reviews
    row = _review(host.root, kind="question")
    body = json.dumps({"id": row["id"], "verdict": "answer", "response": "Yes, she changed her name."}).encode()
    status, _, text = call(host.routes, "POST", "/rem/review", cookie=f"co_rem={host.token}", body=body)
    assert status == 200 and json.loads(text)["status"] == "answered"
    assert reviews.listing(host.root)[0]["response"] == "Yes, she changed her name."


@pytest.mark.parametrize("bad", [{"verdict": "yes"}, {"id": "", "verdict": "yes"}, {"id": 7, "verdict": "no"},
                                 {"id": "ID", "verdict": "maybe"}, {"id": "ID", "verdict": "unsure"},
                                 {"id": "ID", "verdict": None}, {"id": "ID"},
                                 {"id": "ID", "verdict": "yes", "response": ["Same phone."]}])
def test_a_review_without_an_id_or_with_a_verdict_decide_refuses_is_a_400(host, bad):
    from connectonion.rem import reviews
    row = _review(host.root)
    body = json.dumps({key: row["id"] if value == "ID" else value for key, value in bad.items()}).encode()
    status, _, text = call(host.routes, "POST", "/rem/review", cookie=f"co_rem={host.token}", body=body)
    assert status == 400 and json.loads(text)["error"]
    assert reviews.listing(host.root)[0]["status"] == "pending"


def test_an_unknown_review_is_a_404_not_already_decided(host):
    _review(host.root)
    body = json.dumps({"id": "f" * 32, "verdict": "yes"}).encode()
    status, _, text = call(host.routes, "POST", "/rem/review", cookie=f"co_rem={host.token}", body=body)
    assert status == 404 and "already been decided" not in json.loads(text)["error"]


def test_a_long_answer_is_recorded_whole(host):
    from connectonion.rem import reviews
    row = _review(host.root, kind="question")
    answer = "她在两个团队都做过产品负责人。" * 120                     # ~5 KB of UTF-8, past the 4 KB action limit
    body = json.dumps({"id": row["id"], "verdict": "answer", "response": answer}, ensure_ascii=False).encode()
    assert call(host.routes, "POST", "/rem/review", cookie=f"co_rem={host.token}", body=body)[0] == 200
    assert reviews.listing(host.root)[0]["response"] == answer


def test_a_review_already_decided_says_so_instead_of_deciding_twice(host):
    row = _review(host.root)
    cookie = f"co_rem={host.token}"
    body = json.dumps({"id": row["id"], "verdict": "no"}).encode()
    assert call(host.routes, "POST", "/rem/review", cookie=cookie, body=body)[0] == 200
    status, _, text = call(host.routes, "POST", "/rem/review", cookie=cookie,
                           body=json.dumps({"id": row["id"], "verdict": "yes"}).encode())
    assert status == 409 and "already been decided" in json.loads(text)["error"]


def test_a_status_read_is_not_an_owner_change(host, cache, clock):
    from connectonion.rem import tasks
    receipt = tasks.reserve(host.root, {'key': 'people/fern.md\nReview the pilot.',
        'keys': ['people/fern.md\nReview the pilot.'], 'record': 'people/fern.md',
        'title': 'Fern Vale', 'text': 'Review the pilot.', 'task': {'prompt': 'Review it.'}})
    call(host.routes, "GET", "/rem", cookie=f"co_rem={host.token}")
    reader.refresh(host.root)
    cache.clear()
    body = json.dumps({'id': receipt['id']}).encode()
    assert call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=body)[0] == 200
    assert cache == []


def test_version_names_a_failed_rebuild(host, cache, clock):
    cookie = f"co_rem={host.token}"
    call(host.routes, "GET", "/rem", cookie=cookie)
    assert json.loads(call(host.routes, "GET", "/rem/version", cookie=cookie)[2]).get("failed") is None
    reader._keep_failure(host.root)
    failed = json.loads(call(host.routes, "GET", "/rem/version", cookie=cookie)[2])["failed"]
    assert failed["log"].endswith("build.log") and failed["at"]


def test_a_host_that_died_soon_after_open_started_it_names_its_log(host, cache, monkeypatch):
    identity = host.routes["identity_dir"]
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: identity)
    reader.open_snapshot(host.root, launch=False)
    live_host.write_json(identity / "rem-live-host.json", {                 # a Host ran here before
        "address": "owner", "pid": 2 ** 22 + 7, "port": 9125, "command": "-m connectonion.cli.main ai"})
    monkeypatch.setattr(live_host, "answers", lambda port, address: False)
    monkeypatch.setattr(live_host, "_spawn", lambda directory, port=None: SimpleNamespace(
        pid=2 ** 22 + 9, args=["python", "-m", "connectonion.cli.main", "ai", "--port", "9127"]))
    first = reader.local_or_snapshot(host.root, "owner", launch=False)
    assert first["live"] == live_host.STARTING
    again = reader.local_or_snapshot(host.root, "owner", launch=False)  # that pid never ran
    assert "rem-live-host.log" in again["live"] and again["live"] != live_host.STARTING



def test_the_hosts_minute_tick_does_not_make_a_quiet_hour_rebuild(host, cache, clock, monkeypatch):
    """approvals.release takes the lock each minute and rewrites its owner file."""
    from connectonion.rem import approvals
    cookie = f"co_rem={host.token}"
    renders, original = [], reader.snapshot
    monkeypatch.setattr(reader, "snapshot", lambda root, **o: renders.append(1) or original(root, **o))
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: reader.refresh(root, builds) or True)
    call(host.routes, "GET", "/rem", cookie=cookie)
    reader.refresh(host.root)
    clock[0] += reader.REBUILD_INTERVAL + 1
    call(host.routes, "GET", "/rem/version", cookie=cookie)   # the first walk records the tree
    renders.clear()
    for minute in range(11, 60):                             # the rest of the hour since the build
        clock[0] += 60
        approvals.release(host.root)                         # the Host's minute clock
        call(host.routes, "GET", "/rem/version", cookie=cookie)
    assert renders == []


def test_the_hand_to_claude_button_reaches_dispatch_with_claude(host, monkeypatch):
    """The real button builds the request; the real Host route and tasks.dispatch take it."""
    from connectonion.rem import night, tasks
    from connectonion.rem.config import read_config
    from connectonion.rem.files import Notebook, read_json
    from tests.unit.test_rem_reader import HAND, TEMPLATE, _run_reader_js
    book = Notebook(host.root)
    book.stub_project('projects/pilot.md', 'Mara pilot', [])
    book.write('projects/pilot.md', book.read('projects/pilot.md').replace(
        '## Open threads\n', '## Open threads\n- You owe Mara a pilot review.\n'))
    night.prepare(host.root, read_config(host.root))
    row = night.listing(host.root)[0]
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in HAND)
    sent = _run_reader_js('const AGENT_NAMES = { codex: "Codex", claude: "Claude" }, ACTIVE_TASK = ["queued", "starting", "running"], OPEN_TALKS = new Map();\n' + functions + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: children.filter(Boolean),
        append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; }});
      const doneKey = entry => entry.key, location = {protocol: 'http:'}, setTimeout = () => {}, requests = [];
      const REM = {live: true, today_queue: [''' + json.dumps({'key': row['keys'][0], 'keys': row['keys']}) + r''']};
      globalThis.fetch = async (url, options) => { requests.push({url, ...options});
        return {ok: true, status: 200, json: async () => ({result: 'starting', agent: 'claude'})}; };
      const line = handOff({key: REM.today_queue[0].key}).children[0];
      line.children.find(child => child['data-agent'] === 'claude').onclick().then(() =>
        console.log(JSON.stringify({request: requests[0], shown: line.children.map(child => child.text).filter(text => text && text !== '·')})));
    ''')
    assert sent['request']['url'] == '/rem/task' and sent['shown'] == ['Claude is working', 'Stop', 'Take back from Claude']
    started = []
    monkeypatch.setattr(tasks, 'start', lambda root, task_id, agent=None: started.append(agent) or
                        {'id': task_id, 'agent': agent, 'result': 'starting'})
    status, _, text = call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}',
                           body=sent['request']['body'].encode())
    assert status == 200 and json.loads(text)['agent'] == 'claude' and started == ['claude']
    receipt = read_json(tasks.directory(host.root, json.loads(text)['id']) / 'receipt.json', {})
    assert receipt['agent'] == 'claude' and receipt['result'] == 'queued'


def test_a_host_this_open_just_started_is_called_starting_not_someone_elses(tmp_path, monkeypatch):
    """Seen on a real laptop: the relay saw the new Host before its port answered, and
    the open blamed "a co ai not on a port co rem knows" for REM's own Host."""
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: tmp_path)

    def online(address, **k):  # starts ours, then the relay sees it
        live_host.write_json(tmp_path / "rem-live-host.json",
                             {"address": address, "pid": 4242, "port": 9128, "command": "-m connectonion.cli.main ai"})
    monkeypatch.setattr(live_host, "ensure_online", online)
    monkeypatch.setattr(live_host, "answers", lambda port, address: False)   # its port is not up yet
    monkeypatch.setattr(live_host, "_alive", lambda saved: saved.get("pid") == 4242)
    monkeypatch.setattr(live_host, "LOCAL_WAIT", 0.05, raising=False)
    url, failure = live_host.ensure_local("owner")
    assert url is None and failure == live_host.STARTING
    assert "port co rem knows" not in failure and "`" not in failure and "co rem open" not in failure
    prepare(tmp_path / "rem")
    monkeypatch.setattr(live_host, "ensure_local", lambda address, **k: (None, live_host.STARTING))
    note = reader.local_or_snapshot(tmp_path / "rem", "owner", launch=False)["live"]
    assert note == live_host.STARTING                               # said plainly, not as "unavailable"


def test_ask_codex_to_look_starts_a_private_project_investigation_through_the_task_route(host, monkeypatch):
    """让 Codex 查 (#2909): the private project's page is the key of the same /rem/task run; nothing else is."""
    from connectonion.rem import tasks
    from connectonion.rem.files import Notebook
    book = Notebook(host.root)
    book.stub_project('projects/private-notes-ab12.md', 'Private notes', [])
    book.stub_project('projects/harbour-ab12.md', 'Harbour Studio', [])
    started = []
    monkeypatch.setattr(tasks, 'start', lambda root, task_id, agent=None: started.append(agent) or
                        {'id': task_id, 'agent': agent, 'result': 'starting'})
    body = json.dumps({'action': 'run', 'key': 'projects/private-notes-ab12.md', 'agent': 'codex'}).encode()
    assert call(host.routes, 'POST', '/rem/task', body=body)[0] == 401
    status, _, text = call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=body)
    assert status == 200 and started == ['codex']
    receipt = tasks.receipt_for(host.root, 'projects/private-notes-ab12.md')
    assert receipt['record'] == 'projects/private-notes-ab12.md' and receipt['by'] == 'owner'
    assert 'projects/private-notes-ab12.md' in receipt['prompt'] and 'Private notes' in receipt['text']
    # Only a private project page this notebook holds: anything else is the same plain 400.
    for key in ('projects/harbour-ab12.md', 'projects/private-gone-ab12.md', 'people/alice-chen.md', '../projects/private-notes-ab12.md'):
        raw = json.dumps({'action': 'run', 'key': key, 'agent': 'claude'}).encode()
        status, _, text = call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=raw)
        assert status == 400 and json.loads(text)['error'], key
    assert started == ['codex']


def test_a_private_projects_investigation_rides_on_its_page_in_the_live_reader(host, monkeypatch):
    from connectonion.rem import tasks
    from connectonion.rem.files import Notebook
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    Notebook(host.root).stub_project('projects/private-notes-ab12.md', 'Private notes', [])
    receipt = tasks.reserve(host.root, tasks.investigation(host.root, 'projects/private-notes-ab12.md'))
    live = {r['path']: r for r in reader.snapshot(host.root, local=True)['records']}
    shared = {r['path']: r for r in reader.snapshot(host.root)['records']}
    assert live['projects/private-notes-ab12.md']['task']['id'] == receipt['id']
    assert 'task' not in shared['projects/private-notes-ab12.md']


def test_details_stay_json_while_a_newer_render_builds(host, cache, clock):
    """The "Updating…" banner is HTML: put after the details JSON it broke every
    deferred page (Org, Projects, All records) with "Unexpected non-whitespace
    character after JSON" (1.9.6rc2)."""
    from connectonion.rem.files import Notebook
    cookie = f"co_rem={host.token}"
    call(host.routes, "GET", "/rem", cookie=cookie)
    reader.refresh(host.root)
    Notebook(host.root).write("people/bruno-vale.md", "# Bruno Vale\n")   # the key moves; a build runs
    clock[0] += reader.REBUILD_INTERVAL + 1                             # and one is due
    status, head, body = call(host.routes, "GET", "/rem/data.json", cookie=cookie)
    assert status == 200 and head["content-type"].startswith("application/json")
    assert json.loads(body)["records"]                                  # parses, banner or not
    assert 'id="rem-updating"' in call(host.routes, "GET", "/rem", cookie=cookie)[2]


def test_a_host_older_than_the_installed_package_does_not_say_updating_for_ever(host, cache, monkeypatch):
    """The reader's Host was started under 1.9.5 and the package was upgraded
    under it. Its page key carried the version in its memory; the build (a new
    Python) saved pages under the installed one. The two never met, so every
    page said "Updating…" and every request started a build with nothing to do."""
    import connectonion
    cookie = f"co_rem={host.token}"
    call(host.routes, "GET", "/rem", cookie=cookie)
    reader.refresh(host.root)                                    # what the detached build saves
    monkeypatch.setattr(connectonion, "__version__", "0.0.1")    # this process is the old Host
    cache.clear()
    for _ in range(2):
        assert 'id="rem-updating"' not in call(host.routes, "GET", "/rem", cookie=cookie)[2]
    assert cache == []


@pytest.fixture
def old_host_here(host, monkeypatch):
    """The Host co rem started before an upgrade, recorded in this identity folder:
    a stub answering /info as 0.0.1, with the reader's Host command."""
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: host.routes["identity_dir"])
    stub = Path(__file__).resolve().parents[1] / "rem_host_stub.py"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    args = [sys.executable, str(stub), "owner", "0.0.1", "ai", "--port", str(port), "--no-listen", "--no-launch"]
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL)
    deadline = time.monotonic() + 20
    while not live_host._info(port):
        assert process.poll() is None and time.monotonic() < deadline, "the stub Host did not answer"
    live_host.write_json(host.routes["identity_dir"] / "rem-live-host.json", {
        "address": "owner", "pid": process.pid, "port": port, "command": " ".join(args[1:])})
    yield process, port
    process.kill()
    process.wait()


def test_the_page_build_replaces_the_old_host_once_its_pages_are_saved(host, cache, old_host_here, monkeypatch):
    from tests.rem_host_stub import serving
    process, port = old_host_here
    started = []

    def spawn(directory, port_wanted=None):   # the installed version comes up on the port asked for
        started.append(bool(reader.saved(host.root, "live")))
        running.enter_context(serving("owner", connectonion.__version__, port=port_wanted))
        return SimpleNamespace(pid=4242, poll=lambda: None, args=["python", "-m", "connectonion.cli.main",
                                                                  "ai", "--port", str(port_wanted)])
    monkeypatch.setattr(live_host, "_spawn", spawn)
    with ExitStack() as running:
        reader.main([str(host.root), "live"])
        assert live_host.answers(port, "owner")             # the tab's address, now the installed version
    assert process.wait(timeout=10) is not None and started == [True]


def test_a_host_that_cannot_be_replaced_does_not_fail_the_saved_build(host, cache, old_host_here, monkeypatch, capsys):
    def refuse(saved):
        raise OSError("the co ai started before the upgrade (pid 7) did not stop")
    monkeypatch.setattr(live_host, "_retire", refuse)
    reader.main([str(host.root), "live"])                  # returns: the build itself succeeded
    assert reader.saved(host.root, "live") and reader.failure(host.root) is None
    assert capsys.readouterr().out.strip().splitlines()[-1] == (
        "The pages are saved; the server from before the upgrade was not replaced: "
        "the co ai started before the upgrade (pid 7) did not stop")


def test_a_half_written_upgrade_under_the_build_is_one_line_not_a_failed_build(host, cache, monkeypatch, capsys):
    def half_written():
        raise SyntaxError("unexpected EOF while parsing (_version.py, line 11)")
    monkeypatch.setattr(live_host, "renew_idle", half_written)
    reader.main([str(host.root), "live"])
    assert reader.saved(host.root, "live") and reader.failure(host.root) is None
    assert "was not replaced" in capsys.readouterr().out.strip().splitlines()[-1]
