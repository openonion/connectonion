"""GitHub polling preserves work across replay, crashes and quiet PR reviews."""
import json
import subprocess

import pytest
from typer.testing import CliRunner

from connectonion.inbox.github import GitHub, configure, read_config
from connectonion.inbox.store import Inbox

START = '2026-10-02T10:00:00Z'
LATER = '2026-10-02T10:01:00Z'


def issue(number=1, **changes):
    return dict(id=number, number=number, title='Fix login', body='Original **markdown**',
                user={'login': 'alice'}, created_at=LATER, updated_at=LATER,
                html_url=f'https://github.com/acme/app/issues/{number}', state='open',
                labels=[], **changes)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('CO_INBOX_HOME', str(tmp_path))
    configure('acme/app')
    box = Inbox('github')
    bot = GitHub()
    calls = []
    data = {'issues': [issue()], 'issues/comments': [], 'pulls/comments': [], 'pulls': []}

    def api(path, **query):
        calls.append((path, query))
        suffix = path.removeprefix('repos/acme/app/')
        return data.get(suffix, [])

    monkeypatch.setattr(bot, 'pages', api)
    return bot, box, data, calls


def test_issue_pr_comments_and_review_keep_routing_data(setup):
    bot, box, data, _ = setup
    data['issues'].append(issue(2, pull_request={}))
    data['pulls/2'] = {'merged_at': None}
    data['issues/comments'] = [dict(id=7, body='Please investigate', user={'login': 'bob'},
        created_at=LATER, updated_at=LATER, issue_url='https://api.github.com/repos/acme/app/issues/1',
        html_url='https://github.com/acme/app/issues/1#issuecomment-7')]
    data['pulls/comments'] = [dict(data['issues/comments'][0], id=8,
        pull_request_url='https://api.github.com/repos/acme/app/pulls/2')]
    data['pulls'] = [issue(2)]
    data['pulls/2/reviews'] = [dict(id=9, body='Looks good', user={'login': 'bob'},
        submitted_at=LATER, state='APPROVED', html_url='https://github.com/acme/app/pull/2#review-9')]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(bot, 'api', lambda path, **_: data[path.removeprefix('repos/acme/app/')])
    bot.scan(box, since=START, now='2026-10-02T10:02:00Z')
    rows = box.history()
    assert len(rows) == 5
    assert {r['event']['kind'] for r in rows} == {'issue', 'pull_request', 'issue_comment', 'review_comment', 'review'}
    assert rows[0]['text'] == 'Fix login\n\nOriginal **markdown**'
    assert all(r['event']['repo'] == 'acme/app' and r['event']['url'] for r in rows)
    monkeypatch.undo()


def test_restart_and_equal_timestamps_do_not_duplicate(setup):
    bot, box, data, _ = setup
    data['issues'].append(issue(2))
    bot.scan(box, since=START, now=LATER)
    bot.scan(box, now=LATER)
    assert len(box.history()) == 2
    restored = GitHub()
    restored.pages = bot.pages
    restored.scan(box, now=LATER)
    assert len(box.history()) == 2


def test_failed_delivery_never_advances_checkpoint(setup, monkeypatch):
    bot, box, _, _ = setup
    monkeypatch.setattr(box, 'deliver', lambda *_a, **_kw: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError, match='disk full'):
        bot.scan(box, since=START, now=LATER)
    assert not (box.root / 'checkpoint.json').exists()


def test_default_baseline_skips_old_content_but_not_new_activity(setup):
    bot, box, data, _ = setup
    data['issues'] = [dict(issue(), created_at='2020-01-01T00:00:00Z', updated_at='2020-01-01T00:00:00Z'), issue(2)]
    bot.scan(box, now=START)
    assert [r['event']['number'] for r in box.history()] == [2]


def test_review_on_old_closed_pr_does_not_depend_on_issue_timestamp(setup):
    bot, box, data, _ = setup
    data['issues'] = []
    data['pulls'] = [dict(issue(2), updated_at='2020-01-01T00:00:00Z', state='closed')]
    data['pulls/2/reviews'] = [dict(id=9, body='Late review', user={'login': 'bob'},
        submitted_at=LATER, state='COMMENTED', html_url='https://github.com/acme/app/pull/2#review-9')]
    bot.scan(box, since=START, now=LATER)
    assert box.history()[0]['event']['kind'] == 'review'


def test_watch_is_explicit_and_invalid_names_never_become_arguments(tmp_path, monkeypatch):
    monkeypatch.setenv('CO_INBOX_HOME', str(tmp_path))
    configure('acme/app', interval=90)
    configure('acme/other')
    assert read_config()['repos'] == ['acme/app', 'acme/other']
    assert read_config()['interval'] == 90
    for name in ['--help', 'a/b/c', 'https://github.com/a/b', 'a/../b']:
        with pytest.raises(ValueError):
            configure(name)


def test_paginated_gh_api_reuses_auth_without_reading_token(monkeypatch):
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        rows = [{'id': i} for i in range(100)] if len(calls) == 1 else [{'id': 101}]
        return subprocess.CompletedProcess(argv, 0, 'HTTP/2.0 200 OK\nContent-Type: application/json\n\n' + json.dumps(rows), '')
    monkeypatch.setattr(subprocess, 'run', run)
    assert len(GitHub().pages('repos/acme/app/issues', state='all')) == 101
    assert len(calls) == 2 and 'page=2' in calls[1]
    assert '--method' in calls[0] and 'GET' in calls[0]
    assert 'auth' not in calls[0] and 'token' not in calls[0]


def test_github_cli_only_advertises_supported_verbs():
    from connectonion.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ['github', '--help'])
    assert result.exit_code == 0, result.output
    for verb in ['watch', 'unwatch', 'listen', 'receive', 'consume', 'done']:
        assert verb in result.output
    assert ' send ' not in result.output and ' reply ' not in result.output


def test_event_survives_queue_claim_without_raw_flag(setup):
    bot, box, _, _ = setup
    bot.scan(box, since=START, now=LATER)
    taken = box.receive(0)
    assert taken.event['number'] == 1 and taken.raw is None
    assert taken.event['host'] == 'github.com'


def test_baseline_is_not_advanced_on_partial_page_fetch(setup, monkeypatch):
    bot, box, _, _ = setup
    def failed(path, **_):
        if path.endswith('/pulls'):
            raise RuntimeError('rate limited')
        return [issue()] if path.endswith('/issues') else []
    monkeypatch.setattr(bot, 'pages', failed)
    with pytest.raises(RuntimeError, match='rate limited'):
        bot.scan(box, since=START, now=LATER)
    assert not (box.root / 'checkpoint.json').exists()


def test_rate_limit_waits_for_retry_after_then_reads(monkeypatch):
    responses = [subprocess.CompletedProcess([], 1, 'HTTP/2.0 429 Too Many Requests\nRetry-After: 2\n\n{}', 'rate limited'),
                 subprocess.CompletedProcess([], 0, 'HTTP/2.0 200 OK\n\n{"login":"alice"}', '')]
    waits = []
    monkeypatch.setattr(subprocess, 'run', lambda *_a, **_kw: responses.pop(0))
    monkeypatch.setattr('connectonion.inbox.github.time.sleep', waits.append)
    assert GitHub().api('user') == {'login': 'alice'}
    assert max(waits) > 1


def test_auth_failure_never_copies_environment_token(monkeypatch):
    monkeypatch.setenv('GH_TOKEN', 'secret-for-test-only')
    monkeypatch.setattr(subprocess, 'run', lambda *_a, **_kw:
                        subprocess.CompletedProcess([], 1, '', 'gh: Bad credentials (HTTP 401)'))
    with pytest.raises(RuntimeError, match='Bad credentials') as failure:
        GitHub().api('user')
    assert 'secret-for-test-only' not in str(failure.value)


def test_initial_crash_keeps_start_time_for_undelivered_activity(setup, monkeypatch):
    bot, box, data, _ = setup
    original = box.deliver
    monkeypatch.setattr(box, 'deliver', lambda *_a, **_kw: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        bot.scan(box, now=START)
    monkeypatch.setattr(box, 'deliver', original)
    restored = GitHub()
    restored.pages = bot.pages
    restored.scan(box, now='2026-10-03T00:00:00Z')
    assert box.history()[0]['event']['number'] == 1


def test_merged_pr_is_distinguished_from_closed_pr(setup, monkeypatch):
    bot, box, data, _ = setup
    data['issues'] = [dict(issue(2, pull_request={}), state='closed')]
    monkeypatch.setattr(bot, 'api', lambda *_a, **_kw: {'merged_at': LATER})
    bot.scan(box, since=START, now=LATER)
    assert box.history()[0]['event']['action'] == 'merged'
