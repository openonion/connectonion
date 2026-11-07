"""Owner-only reader actions create unsent provider drafts and save translation priority."""
import json

from tests.unit.test_rem_live_reader import call, host  # noqa: F401
from connectonion.rem import drafts
from connectonion.rem.files import read_json, state_path


def test_rem_draft_endpoint_creates_only_after_authenticated_owner_click(host, monkeypatch):
    calls = []
    monkeypatch.setattr(drafts, 'open_provider', lambda root, key: calls.append(key) or {'url': 'https://mail.google.com/mail/u/0/#drafts'})
    payload = json.dumps({'id': 'a' * 32, 'action': 'open'}).encode()
    status, _, _ = call(host.routes, 'POST', '/rem/draft', body=payload)
    assert status == 401 and calls == []
    status, _, body = call(host.routes, 'POST', '/rem/draft', cookie=f'co_rem={host.token}', body=payload)
    assert status == 200 and calls == ['a' * 32]
    assert json.loads(body)['url'].endswith('#drafts')


def test_rem_draft_endpoint_sends_only_for_the_authenticated_owner_and_carries_edits(host, monkeypatch):
    sent = []
    monkeypatch.setattr(drafts, 'send', lambda root, key, body=None: sent.append((key, body)) or {'status': 'sent'})
    payload = json.dumps({'id': 'a' * 32, 'action': 'send', 'body': 'Edited by hand.'}).encode()
    status, _, _ = call(host.routes, 'POST', '/rem/draft', body=payload)
    assert status == 401 and sent == []
    status, _, body = call(host.routes, 'POST', '/rem/draft', cookie=f'co_rem={host.token}', body=payload)
    assert status == 200 and sent == [('a' * 32, 'Edited by hand.')]
    assert json.loads(body) == {'status': 'sent'}


def test_rem_draft_endpoint_rejects_unknown_actions_and_form_posts(host, monkeypatch):
    monkeypatch.setattr(drafts, 'open_provider', lambda *args: (_ for _ in ()).throw(AssertionError('unexpected call')))
    for action, content_type, expected in [('forward', 'application/json', 400), ('open', 'application/x-www-form-urlencoded', 415)]:
        status, _, _ = call(host.routes, 'POST', '/rem/draft', cookie=f'co_rem={host.token}',
                           body=json.dumps({'id': 'a' * 32, 'action': action}).encode(), content_type=content_type)
        assert status == expected


def test_rem_reader_request_queues_translation_instead_of_starting_model(host):
    status, _, _ = call(host.routes, 'POST', '/rem/translation-request', cookie=f'co_rem={host.token}',
                       body=json.dumps({'page': 'people/alice-chen.md', 'language': 'zh'}).encode())
    assert status == 200
    assert read_json(state_path(host.root, 'translation-requests.json'), {}) == {'zh': ['people/alice-chen.md']}


def test_rem_actions_reject_malformed_or_non_object_json(host):
    for endpoint in ('/rem/draft', '/rem/translation-request'):
        for payload in (b'{', b'[]', b'null', b'"draft"'):
            status, _, body = call(host.routes, 'POST', endpoint, cookie=f'co_rem={host.token}', body=payload)
            assert status == 400
            assert json.loads(body)['error']


def test_rem_draft_endpoint_prepares_a_thread_now_for_the_owner(host, monkeypatch):
    calls = []
    monkeypatch.setattr(drafts, 'prepare_now', lambda root, provider, thread: calls.append((provider, thread)) or {'id': 'b' * 32, 'status': 'prepared'})
    payload = json.dumps({'action': 'prepare', 'provider': 'outlook', 'thread': 'mail:outlook:abc'}).encode()
    status, _, _ = call(host.routes, 'POST', '/rem/draft', body=payload)
    assert status == 401 and calls == []
    status, _, body = call(host.routes, 'POST', '/rem/draft', cookie=f'co_rem={host.token}', body=payload)
    assert status == 200 and calls == [('outlook', 'mail:outlook:abc')] and json.loads(body)['status'] == 'prepared'
    status, _, _ = call(host.routes, 'POST', '/rem/draft', cookie=f'co_rem={host.token}', body=json.dumps({'action': 'prepare', 'provider': 'outlook'}).encode())
    assert status == 400
