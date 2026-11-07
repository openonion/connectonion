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


def test_rem_thread_endpoint_owner_json_gating_and_undo(host):
    payload = json.dumps({'key': 'people/alice-chen.md\nA promise', 'state': 'done'}).encode()
    assert call(host.routes, 'POST', '/rem/thread', body=payload)[0] == 401
    cookie = f'co_rem={host.token}'
    assert call(host.routes, 'POST', '/rem/thread', cookie=cookie, body=payload, content_type='text/plain')[0] == 415
    for kwargs in ({'client': '192.168.1.2'}, {'host_header': 'evil.test'}):
        assert call(host.routes, 'POST', '/rem/thread', cookie=cookie, body=payload, **kwargs)[0] == 404
    assert call(host.routes, 'POST', '/rem/thread', cookie=cookie, body=payload)[0] == 200
    status, _, body = call(host.routes, 'GET', '/rem/thread', cookie=cookie)
    assert status == 200 and json.loads(body)['people/alice-chen.md\nA promise']['state'] == 'done'
    assert read_json(state_path(host.root, 'threads.json'), {})
    payload = json.dumps({'key': 'people/alice-chen.md\nA promise', 'state': 'open'}).encode()
    assert call(host.routes, 'POST', '/rem/thread', cookie=cookie, body=payload)[0] == 200
    assert read_json(state_path(host.root, 'threads.json'), {}) == {}


def test_rem_thread_endpoint_rejects_invalid_actions(host):
    for value in ({'key': '../x', 'state': 'done'}, {'key': 'x', 'state': 'sent'}, {}, [], None):
        assert call(host.routes, 'POST', '/rem/thread', cookie=f'co_rem={host.token}', body=json.dumps(value).encode())[0] == 400


def test_interface_language_persists_owner_consent_once_without_replacing_settings(host):
    from connectonion.rem.config import read_config, set_config
    set_config(host.root, ['languages', 'ja', 'limits.translations_per_day', '7'])
    endpoint, payload = '/rem/language', b'{"language":"zh"}'
    assert call(host.routes, 'POST', endpoint, body=payload)[0] == 401
    assert read_config(host.root)['languages'] == ['ja']
    cookie = f'co_rem={host.token}'
    assert call(host.routes, 'POST', endpoint, cookie=cookie, body=payload)[0] == 200
    saved = (host.root / 'config.yaml').read_bytes()
    assert call(host.routes, 'POST', endpoint, cookie=cookie, body=payload)[0] == 200
    assert (host.root / 'config.yaml').read_bytes() == saved
    config = read_config(host.root)
    assert config['languages'] == ['ja', 'zh'] and config['language'] == 'en'
    assert config['limits']['translations_per_day'] == 7
    assert 'languages' in read_json(state_path(host.root, 'config-explicit.json'), [])


def test_interface_language_validates_and_uses_owner_json_gates(host):
    from connectonion.rem.config import read_config
    endpoint, cookie = '/rem/language', f'co_rem={host.token}'
    for payload in (b'{', b'[]', b'null'):
        assert call(host.routes, 'POST', endpoint, cookie=cookie, body=payload)[0] == 400
    for language in (None, [], '../zh', 'zh,en', ''):
        status, _, body = call(host.routes, 'POST', endpoint, cookie=cookie,
                               body=json.dumps({'language': language}).encode())
        assert status == 409 and 'language' in json.loads(body)['error']
    payload = b'{"language":"zh"}'
    assert call(host.routes, 'POST', endpoint, cookie=cookie, body=payload, content_type='text/plain')[0] == 415
    for kwargs in ({'client': '192.168.1.2'}, {'host_header': 'evil.test'}):
        assert call(host.routes, 'POST', endpoint, cookie=cookie, body=payload, **kwargs)[0] == 404
    assert read_config(host.root)['languages'] == []


def test_interface_switch_posts_once_only_in_live_reader():
    import re
    from connectonion.rem.reader import TEMPLATE
    from tests.unit.test_rem_reader import _run_reader_js
    function = re.search(r'function setInterfaceLanguage\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + '''
      const REM = {live: true, records: []}, location = {protocol: "http:"};
      const calls = [], fetch = (url, options) => {calls.push({url, ...options}); return Promise.resolve({ok: true});};
      const readerStorage = () => {}, closeEvidence = () => {}, render = () => {};
      setInterfaceLanguage("zh");
      const live = calls.splice(0);
      REM.live = false; setInterfaceLanguage("en");
      REM.live = true; location.protocol = "file:"; setInterfaceLanguage("zh");
      console.log(JSON.stringify({live, offline: calls}));
    ''')
    assert result['offline'] == []
    assert len(result['live']) == 1
    request = result['live'][0]
    assert request['url'] == '/rem/language' and request['method'] == 'POST'
    assert request['headers']['Content-Type'] == 'application/json'
    assert json.loads(request['body']) == {'language': 'zh'}


def test_interface_language_waits_for_an_in_progress_notebook_write(host):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    import pytest
    from connectonion.rem.config import read_config
    from connectonion.rem.files import maintenance_lock
    with ThreadPoolExecutor(max_workers=1) as pool:
        with maintenance_lock(host.root):
            pending = pool.submit(call, host.routes, 'POST', '/rem/language',
                                  cookie=f'co_rem={host.token}', body=b'{"language":"zh"}')
            with pytest.raises(TimeoutError):
                pending.result(timeout=0.2)
        assert pending.result(timeout=5)[0] == 200
    assert read_config(host.root)['languages'] == ['zh']
