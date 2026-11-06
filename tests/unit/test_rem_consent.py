"""Consent stays readable while the structured summary keeps every setting."""

import copy
import json
import textwrap

import pytest

from connectonion.cli.commands.rem_output import render
from connectonion.rem.config import prepare, read_config
from connectonion.rem.service import consent_summary


def test_consent_with_four_sources_fits_one_screen(tmp_path, monkeypatch):
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    for number in range(6):
        (sessions / f'rollout-{number}.jsonl').write_text('')
    sources = {
        'codex': {'kind': 'codex', 'enabled': True, 'root': str(sessions)},
        'claude-code': {'kind': 'claude-code', 'enabled': True, 'root': str(tmp_path / 'missing')},
        'gmail': {'kind': 'gmail', 'enabled': False, 'adapter': 'waiting for co auth google'},
        'whatsapp': {'kind': 'whatsapp', 'enabled': False, 'root': '/fictional/inbox/whatsapp',
                     'since': '2026-09-05T12:00:00+00:00', 'chats': []},
    }
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: sources)
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    monkeypatch.setattr('connectonion.rem.config.first_runner', lambda value: value)
    prepare(tmp_path / 'rem')
    summary = consent_summary(tmp_path / 'rem')
    original = copy.deepcopy(summary)
    text = render(summary, 'start — source access and schedule')
    assert len(text.splitlines()) <= 25
    assert sum(max(1, len(textwrap.wrap(line, 80))) for line in text.splitlines()) < 30
    assert text.splitlines()[2:7] == [
        'Sources:', '  codex sessions: 6 found, will be read',
        '  claude-code sessions: directory missing',
        '  gmail: waiting for co auth google', '  whatsapp: not subscribed',
    ]
    assert 'Input chars per batch' not in text
    assert '/fictional/inbox/whatsapp' not in text and str(sessions) not in text
    assert '2026-09-05' not in text and 'Since:' not in text
    assert 'Model: codex · ' + summary['model'] in text
    assert 'through your own Codex login (no API key)' in text
    assert 'Permissions: ' in text and 'danger-full-access' in text
    assert 'Schedule: ' + ', '.join(summary['schedule']['times']) in text
    assert summary['schedule']['timezone'] in text
    assert 'Daily cap: 50 runner calls/day; stop at 90% weekly quota used' in text
    assert 'Background: ' in text and 'co rem stop' in text
    assert text.endswith('Details: co rem config')
    assert summary == original
    assert set(summary) == {'root', 'sources', 'runner', 'model', 'model_receives',
                            'model_permissions', 'schedule', 'limits', 'background'}
    assert json.loads(json.dumps(summary)) == original
    assert summary['limits'] == read_config(tmp_path / 'rem')['limits']
    assert summary['sources']['whatsapp'] == {
        'state': 'unsubscribed', 'root': '/fictional/inbox/whatsapp', 'project': None,
        'since': '2026-09-05T12:00:00+00:00', 'chats': [],
    }


def test_consent_keeps_connected_mail_and_chat_scope_on_one_line():
    from connectonion.cli.commands.rem_output import _consent_source
    mail = {'state': 'connected; read from now on if you approve (automated senders skipped). '
                     'Keep it out with co rem sources remove gmail'}
    chat = {'state': "will read 2 chat(s), both sides, the agent's own replies left out",
            'root': '/fictional/inbox/whatsapp', 'chats': ['fictional-chat-a', 'fictional-chat-b']}
    assert _consent_source('gmail', mail) == (
        '  gmail: connected; will be read if approved (automated senders skipped)')
    assert _consent_source('whatsapp', chat) == (
        "  whatsapp: will read 2 chat(s), both sides, the agent's own replies left out")


def test_default_mail_summary_and_recorded_approval_stay_unchanged(tmp_path, monkeypatch):
    from connectonion.rem import service
    from connectonion.rem.files import read_json, state_path
    monkeypatch.setattr(service, 'mail_available', lambda kind: True)
    prepare(tmp_path)
    service.subscribe_read_mail(tmp_path, ['gmail'])
    summary = service.consent_summary(tmp_path)
    assert summary['sources']['gmail']['state'] == 'will be read (automated senders skipped)'
    assert summary['sources']['outlook']['state'] == (
        'connected; read from now on if you approve (automated senders skipped). '
        'Keep it out with co rem sources remove outlook')
    assert service.ensure_consent(tmp_path, confirm=lambda summary: True)
    fingerprint = service.summary_fingerprint(tmp_path)
    assert read_json(state_path(tmp_path, 'consent.json'), {})['summary'] == fingerprint
    assert service.ensure_consent(tmp_path, confirm=lambda summary: pytest.fail('repeat approval'))
    assert service.summary_fingerprint(tmp_path) == fingerprint


def test_scoped_consent_does_not_approve_an_existing_waiting_mailbox(tmp_path, monkeypatch):
    from connectonion.rem import service
    monkeypatch.setattr(service, 'mail_available', lambda kind: True)
    prepare(tmp_path)
    service.subscribe_read_mail(tmp_path, ['gmail', 'outlook'])
    assert service.ensure_consent(tmp_path, mail=['gmail'], confirm=lambda summary: True)
    sources = service.subscriptions(tmp_path)
    assert sources['gmail']['consented']
    assert not sources['outlook']['consented']
    assert service.ensure_consent(tmp_path, mail=['gmail'],
                                  confirm=lambda summary: pytest.fail('repeat approval'))
