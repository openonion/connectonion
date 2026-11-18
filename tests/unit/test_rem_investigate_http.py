"""POST /rem/investigate: the reader's Investigate button through the live Host (#3105)."""
import json

from tests.unit.test_rem_live_reader import call, host  # noqa: F401
from connectonion.rem import page_runs


def post(host, body, cookie=True):
    return call(host.routes, 'POST', '/rem/investigate', body=json.dumps(body).encode(),
                **({'cookie': f'co_rem={host.token}'} if cookie else {}))


def test_the_owner_starts_a_run_at_the_level_chosen_and_follows_it(host, monkeypatch):
    calls = []
    monkeypatch.setattr(page_runs, 'start', lambda root, page, mode: calls.append(('start', page, mode)) or {'result': 'running'})
    monkeypatch.setattr(page_runs, 'status', lambda root, page: calls.append(('status', page)) or {'result': 'running'})
    status, _, _ = post(host, {'action': 'run', 'page': 'people/avery.md'}, cookie=False)
    assert status == 401 and calls == []
    status, _, body = post(host, {'action': 'run', 'page': 'people/avery.md'})
    assert status == 200 and calls == [('start', 'people/avery.md', 'full')]
    assert post(host, {'action': 'run', 'page': 'people/avery.md', 'mode': 'rewrite'})[0] == 200
    assert calls[-1] == ('start', 'people/avery.md', 'rewrite')
    assert post(host, {'page': 'people/avery.md'})[0] == 200 and calls[-1] == ('status', 'people/avery.md')


def test_undo_accept_and_discard_reach_their_functions_and_bad_bodies_are_refused(host, monkeypatch):
    done = []
    for name in ('undo', 'accept', 'discard'):
        monkeypatch.setattr(page_runs, name, lambda root, page, name=name: done.append(name) or {'record': page})
    for name in ('undo', 'accept', 'discard'):
        assert post(host, {'action': name, 'page': 'people/avery.md'})[0] == 200
    assert done == ['undo', 'accept', 'discard']
    for body in ({'action': 'run'}, {'action': 'run', 'page': 'people/avery.md', 'mode': 'deep'},
                 {'action': 'explode', 'page': 'people/avery.md'}, {'action': 'run', 'page': 7}):
        assert post(host, body)[0] == 400, body
