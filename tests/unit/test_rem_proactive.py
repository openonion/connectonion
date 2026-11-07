"""Scheduled REM does reversible work before asking the owner to act."""
import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from connectonion.rem import daily, native, native_round, service, translate
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, read_json, state_path, write_json


@pytest.fixture
def notebook(tmp_path, monkeypatch, rem_clock):
    prepare(tmp_path)
    monkeypatch.setattr(daily, '_clients', lambda sources: {})
    return tmp_path


def test_rem_later_round_queues_unwritten_people_projects_and_owner(notebook, monkeypatch):
    book = Notebook(notebook)
    book.stub_person('people/fern.md', 'Fern Vale', ['fern@example.test'], email='fern@example.test')
    monkeypatch.setattr(daily, '_owner_due', lambda root: [{'record': 'people/me.md', 'kind': 'owner'}])
    monkeypatch.setattr('connectonion.rem.people_pages.correspondents_since', lambda *a, **k: {'records': []})
    monkeypatch.setattr('connectonion.rem.project_pages.queue', lambda root, **kw: [{'record': 'projects/pilot.md'}] if kw.get('include_backlog') else [])
    rows = native_round._jobs(notebook, False, [], {})
    assert {r['record'] for r in rows} >= {'people/fern.md', 'projects/pilot.md', 'people/me.md'}


def test_rem_status_reports_queued_work_without_commands(notebook):
    from connectonion.cli.commands.rem_status import _notebook, notebook as counts
    Notebook(notebook).stub_person('people/fern.md', 'Fern Vale', ['fern@example.test'], email='fern@example.test')
    text = '\n'.join(_notebook(notebook, {'root': str(notebook), 'configured': True}, counts(notebook), lambda args: 'co rem ' + ' '.join(args)))
    assert 'people page queued for tonight' in text
    assert 'co rem investigate' not in text


def test_rem_translation_backlog_orders_changed_owner_people_and_sessions(notebook):
    book = Notebook(notebook)
    for record in ['sessions/old.md', 'projects/pilot.md', 'people/fern.md', 'people/me.md']:
        book.write(record, '# Fictional page\n\n## Sources\n')
    write_json(state_path(notebook, 'map.json'), {'owner': {'record': 'people/me.md'}})
    rows = translate.backlog(notebook, 'zh', changed=['projects/pilot.md'])
    assert rows == ['projects/pilot.md', 'people/me.md', 'people/fern.md', 'sessions/old.md']
    assert read_config(notebook)['limits']['translations_per_day'] == 100


def test_rem_translation_has_budget_independent_of_investigation(notebook, monkeypatch):
    from connectonion.rem import quota
    monkeypatch.setattr(quota, 'read', lambda config: {'unknown': 'fixture'})
    write_json(state_path(notebook, 'runs/run_full.json'), {'id': 'full', 'started_at': service.now().isoformat(), 'phase': 'daily-investigation', 'runner_attempts': 200})
    assert native._stop(notebook, read_config(notebook), phase='daily-translation')[0] is None


def mail_thread(root, provider='gmail', latest='one'):
    from connectonion.rem.mail_archive import retain_message
    from connectonion.rem.store import refresh
    book = Notebook(root)
    book.write('people/fern.md', '# Fern Vale\n\n## Open threads\n- You owe Fern a pilot review. [1]\n\n## Sources\n- [1] ' + provider + ':one\n\nInvestigation: 2026-11-01\n')
    write_json(state_path(root, 'map.json'), {'owner': {'record': 'people/me.md', 'addresses': ['owner@example.test']}})
    retain_message(root, provider, {'id': latest, 'from': 'fern@example.test', 'to': ['owner@example.test'], 'cc': ['team@example.test'], 'subject': 'Pilot review', 'date': '2026-11-07T01:00:00+00:00' if latest == 'one' else '2026-11-07T02:00:00+00:00', 'thread': 'pilot'}, 'Please review the pilot.', fetched_at=service.now().isoformat())
    refresh(root)


def test_rem_drafts_one_per_owner_thread_and_regenerates_for_new_mail(notebook):
    from connectonion.rem import drafts
    mail_thread(notebook)
    rows = drafts.queue(notebook)
    assert len(rows) == 1
    row = rows[0]
    directory = notebook / 'task'
    directory.mkdir()
    task = drafts.prepare(notebook, row, read_config(notebook), directory=directory)
    assert 'never send' in task['prompt'].lower()
    assert 'owner' in task['prompt'].lower() and 'language' in task['prompt'].lower()
    result = drafts.check(task, {'result': json.dumps({'body': 'I will review the pilot today.', 'sources': ['gmail:one']})})
    drafts.promote(notebook, result)
    saved = read_json(drafts.path(notebook, row['id']), {})
    assert saved['to'] == 'fern@example.test' and saved['cc'] == 'team@example.test'
    assert saved['in_reply_to'] == 'one' and saved['from'] == 'owner@example.test'
    assert not drafts.queue(notebook)
    mail_thread(notebook, latest='two')
    assert drafts.queue(notebook)[0]['in_reply_to'] == 'two'
    assert not drafts.listing(notebook), 'stale drafts must never be actionable'
    assert read_config(notebook)['limits']['drafts_per_night'] == 10


@pytest.mark.parametrize('provider', ['gmail', 'outlook'])
def test_rem_open_provider_draft_is_idempotent_and_never_sends(notebook, monkeypatch, provider):
    from connectonion.rem import drafts
    mail_thread(notebook, provider)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'I will review it.', 'sources': [provider + ':one']})
    client = Mock()
    client.create_draft.return_value = {'id': 'draft-1'}
    client.reply.return_value = {'id': 'draft-1', 'web_link': 'https://outlook.live.com/mail/drafts/id/draft-1'}
    monkeypatch.setattr(drafts, 'mail_client', lambda kind: client)
    first = drafts.open_provider(notebook, row['id'])
    assert first == drafts.open_provider(notebook, row['id'])
    assert first['url'].startswith('https://')
    client.send.assert_not_called()
    client.send_draft.assert_not_called()
    assert client.create_draft.call_count + client.reply.call_count == 1
    drafts.discard(notebook, row['id'])
    assert not drafts.queue(notebook) and not drafts.listing(notebook)


def test_rem_switch_accepts_paused_definition_when_desktop_index_lags(notebook, tmp_path, monkeypatch):
    from connectonion.rem.codex_schedule import CodexNative
    monkeypatch.setattr('connectonion.rem.codex_schedule.desktop_timezone', lambda: 'UTC')
    scheduler = CodexNative(tmp_path / 'codex', launcher=Mock(), wait_seconds=0)
    definition = scheduler.render(notebook, read_config(notebook))
    definition['status'] = 'ACTIVE'
    scheduler._write(notebook, definition)
    monkeypatch.setattr(scheduler, '_indexed', lambda root: {**definition, 'cwds': json.dumps(definition['cwds'])})
    assert scheduler.pause_for_exec(notebook)
    assert scheduler.definition(notebook)['status'] == 'PAUSED'


def test_rem_exec_skips_recent_desktop_fire_only_for_this_notebook(notebook, tmp_path):
    from connectonion.rem.codex_schedule import CodexNative, automation_id
    scheduler = CodexNative(tmp_path / 'codex', launcher=Mock(), wait_seconds=0)
    database = scheduler.home / 'sqlite/codex.db'
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE automation_runs (automation_id TEXT, created_at INTEGER)')
        db.execute('INSERT INTO automation_runs VALUES (?, ?)', (automation_id(notebook), int((service.now() - timedelta(minutes=9)).timestamp() * 1000)))
    assert scheduler.recent_desktop_fire(notebook)
    assert not scheduler.recent_desktop_fire(notebook / 'other')
    with sqlite3.connect(database) as db:
        db.execute('UPDATE automation_runs SET created_at = ?', (int((service.now() - timedelta(minutes=11)).timestamp() * 1000),))
    assert not scheduler.recent_desktop_fire(notebook)


def test_rem_native_round_prepares_and_accepts_reply_without_sending(notebook, monkeypatch):
    from connectonion.rem import drafts, quota
    mail_thread(notebook)
    write_json(state_path(notebook, 'consent.json'), {'authorized_at': service.now().isoformat()})
    write_json(state_path(notebook, 'subscriptions.json'), {})
    monkeypatch.setattr(quota, 'read', lambda config: {'unknown': 'fixture'})
    monkeypatch.setattr('connectonion.rem.project_material.extract', lambda *a, **kw: {})
    task = native.next_task(notebook)
    assert task['stage'] == 'reply-draft'
    Path(task['candidate']).write_text(json.dumps({'body': 'I can review the pilot today.', 'sources': ['gmail:one']}))
    assert native.submit(notebook, task['id'])['outcome'] == 'accepted'
    assert len(drafts.listing(notebook)) == 1


def test_rem_native_round_caps_reply_drafts_across_rounds(notebook, monkeypatch):
    from connectonion.rem import drafts
    mail_thread(notebook)
    write_json(state_path(notebook, 'runs/run_drafts.json'), {'phase': 'reply-draft', 'runner_attempts': 10, 'started_at': service.now().isoformat()})
    monkeypatch.setattr(drafts, 'prepare', lambda *a, **k: pytest.fail('Draft budget was exceeded'))
    cursor = {'phase': 'daily-update', 'batch': {'done': True}, 'current': None,
              'jobs': [], 'job_index': 0, 'summaries': [], 'same_new_left': 0,
              'same_left': 0, 'slot': None, 'changed': [], 'translations': []}
    monkeypatch.setattr(native_round, 'finish', lambda *a: None)
    directory = notebook / 'task'
    directory.mkdir()
    assert native_round.prepare_task(notebook, cursor, read_config(notebook), directory) is None


def test_rem_reader_drafts_are_local_only(notebook):
    from connectonion.rem import drafts
    from connectonion.rem.reader_model import reply_drafts
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'I will review it.', 'sources': ['gmail:one']})
    assert reply_drafts(notebook, local=True)[0]['body'] == 'I will review it.'
    assert reply_drafts(notebook) == []


@pytest.mark.parametrize("scheduled", [False, True])
def test_rem_translation_runs_after_general_budget_is_spent(notebook, monkeypatch, scheduled):
    from connectonion.rem import quota
    set_config(notebook, ['languages', 'zh,en'])
    Notebook(notebook).write('people/fern.md', '# Fern Vale\n\n## Sources\n')
    write_json(state_path(notebook, 'consent.json'), {'authorized_at': service.now().isoformat()})
    write_json(state_path(notebook, 'runs/run_full.json'), {'phase': 'daily-investigation', 'runner_attempts': 200, 'started_at': service.now().isoformat()})
    monkeypatch.setattr(quota, 'read', lambda config: {'unknown': 'fixture'})
    write_json(state_path(notebook, 'worker.json'), {'enabled': True})
    task = native.next_task(notebook, scheduled=scheduled)
    assert task['stage'] == 'translate'
    Path(task['candidate']).write_text('# Fern Vale\n')
    assert native.submit(notebook, task['id'])['outcome'] == 'accepted'
    assert translate.cached(notebook, 'people/fern.md', 'zh')
    assert native.next_task(notebook, scheduled=scheduled)['outcome'] == 'done'
    finished = read_json(state_path(notebook, 'round.json'), {})
    assert finished['done']
    assert service.run_logs(notebook, finished['run']['id'])[0]['outcome'] == 'completed'
    if scheduled:
        worker = service.worker_state(notebook)
        assert worker['last_scheduled_slot'] == finished['slot']
        assert worker['last_scheduled_outcome'] == 'completed'


def test_rem_requested_translation_leads_next_backlog(notebook):
    book = Notebook(notebook)
    book.write('sessions/old.md', '# Old\n')
    book.write('people/fern.md', '# Fern\n')
    translate.request(notebook, 'sessions/old.md', 'zh')
    assert translate.backlog(notebook, 'zh')[0] == 'sessions/old.md'


def test_rem_exec_job_installs_after_lagging_pause(notebook, tmp_path, monkeypatch):
    from connectonion.rem.schedule import CodexExec
    from connectonion.rem.codex_schedule import CodexNative
    import plistlib
    binary = tmp_path / 'fictional-codex'
    binary.write_text('#!/bin/sh\nexit 0\n')
    binary.chmod(0o700)
    monkeypatch.setenv('CODEX_CMD', str(binary))
    monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('', ''))
    monkeypatch.setattr('connectonion.rem.codex_schedule.desktop_timezone', lambda: 'UTC')
    monkeypatch.setattr(CodexNative, 'pause_for_exec', lambda self, root: True)
    scheduler = CodexExec(agents_dir=tmp_path / 'agents', command=['/python', '-m', 'connectonion.cli.main'])
    monkeypatch.setattr(scheduler, '_load', lambda path: None)
    result = scheduler.install(notebook, read_config(notebook))
    assert result['scheduler'] == 'codex-exec'
    assert 'paused in its definition' in result['note']
    job = plistlib.loads(scheduler.plist_path(notebook).read_bytes())
    assert 'connectonion.rem.codex_exec' in job['ProgramArguments']


def test_rem_exec_checks_recent_desktop_fire_before_touching_round(notebook, monkeypatch):
    from connectonion.rem.schedule import exec_round
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda *a: True)
    monkeypatch.setattr(native, 'next_task', lambda *a, **kw: pytest.fail('Must skip the turn'))
    assert exec_round(notebook)['outcome'] == 'skipped'


def test_rem_translation_pass_preserves_active_investigation_checkpoint(notebook, monkeypatch):
    from connectonion.rem import quota
    set_config(notebook, ['languages', 'zh,en'])
    Notebook(notebook).write('people/fern.md', '# Fern\n')
    monkeypatch.setattr(quota, 'read', lambda config: {'unknown': 'fixture'})
    cursor = native_round.prepare_translation_round(notebook, read_config(notebook), scheduled=False)
    cursor.update(phase='daily-investigation', investigation_left=0,
                  current={'record': 'people/pilot.md'}, jobs=[{'record': 'people/pilot.md'}])
    write_json(state_path(notebook, 'round.json'), cursor)
    task = native.next_task(notebook)
    assert task['stage'] == 'translate'
    assert read_json(state_path(notebook, 'round.json'), {})['current'] == cursor['current']


def test_rem_ui_language_request_is_translated_without_owner_language_setting(notebook, monkeypatch):
    Notebook(notebook).write('people/fern.md', '# Fern\n')
    translate.request(notebook, 'people/fern.md', 'zh')
    cursor = native_round.prepare_translation_round(notebook, read_config(notebook), scheduled=False)
    directory = notebook / 'translation-task'
    directory.mkdir()
    task = native_round.prepare_translation(notebook, cursor, read_config(notebook), directory)
    assert task and task['task']['language'] == 'zh'


def test_rem_discarded_state_survives_reader_reload_and_new_mail_resets_it(notebook):
    from connectonion.rem import drafts
    from connectonion.rem.reader_model import reply_drafts
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'I will review it.', 'sources': ['gmail:one']})
    drafts.discard(notebook, row['id'])
    state = reply_drafts(notebook, local=True)[0]
    assert state['status'] == 'discarded' and 'body' not in state
    assert not drafts.queue(notebook)
    mail_thread(notebook, latest='two')
    assert reply_drafts(notebook, local=True)[0]['status'] == 'pending'


def test_rem_private_mail_keeps_generated_draft_behind_reader_privacy(notebook):
    from connectonion.rem import drafts
    mail_thread(notebook)
    book = Notebook(notebook)
    book.write('people/fern.md', book.read('people/fern.md').replace('pilot review.', 'pilot review. [sensitive]'))
    row = drafts.queue(notebook)[0]
    assert row['private'] is True
    task_dir = notebook / 'task-private'
    task_dir.mkdir()
    task = drafts.prepare(notebook, row, read_config(notebook), directory=task_dir)
    draft = drafts.check(task, {'result': json.dumps({'body': 'Private reply.', 'sources': ['gmail:one']})})
    assert draft['private'] is True


def test_rem_draft_model_cannot_change_recipient_or_reply_target(notebook):
    from connectonion.rem import drafts
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    task = {'row': row}
    value = drafts.check(task, {'result': json.dumps({'to': 'wrong@example.test', 'in_reply_to': 'wrong', 'body': 'Review.', 'sources': ['gmail:one']})})
    assert value['to'] == 'fern@example.test' and value['in_reply_to'] == 'one'


def test_rem_new_privacy_label_hides_an_existing_draft(notebook):
    from connectonion.rem import drafts
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'Review.', 'sources': ['gmail:one']})
    book = Notebook(notebook)
    book.write('people/fern.md', book.read('people/fern.md').replace('pilot review.', 'pilot review. [sensitive]'))
    assert drafts.listing(notebook)[0]['private'] is True


def test_rem_reply_to_survives_archive_and_drives_the_draft_recipient(notebook):
    from connectonion.rem import drafts
    from connectonion.rem.mail_archive import retain_message
    mail_thread(notebook)
    retain_message(notebook, 'gmail', {'id': 'reply-to', 'from': 'notices@example.test',
                   'reply_to': 'fern@example.test', 'to': ['owner@example.test'], 'subject': 'Pilot review',
                   'thread': 'pilot', 'date': '2026-11-07T03:00:00+00:00'}, 'Reply to Fern.', fetched_at=service.now().isoformat())
    row = drafts.queue(notebook)[0]
    assert row['to'] == 'fern@example.test' and row['in_reply_to'] == 'reply-to'


def test_rem_gmail_reply_draft_keeps_thread_and_never_calls_send(monkeypatch):
    from unittest.mock import MagicMock
    from connectonion.useful_tools.gmail import Gmail
    gmail = Gmail.__new__(Gmail)
    api = MagicMock()
    monkeypatch.setattr(gmail, '_get_service', lambda: api)
    monkeypatch.setattr(gmail, '_require_draft_write_scope', lambda: None)
    api.users().messages().get().execute.return_value = {
        'threadId': 'provider-thread', 'payload': {'headers': [
            {'name': 'Message-ID', 'value': '<one@example.test>'},
            {'name': 'References', 'value': '<earlier@example.test>'}]}}
    api.users().drafts().create().execute.return_value = {'id': 'draft-one'}
    result = gmail.create_draft('fern@example.test', 'Re: Pilot', 'Review.', in_reply_to='one')
    assert result['id'] == 'draft-one'
    message = api.users().drafts().create.call_args.kwargs['body']['message']
    assert message['threadId'] == 'provider-thread'
    decoded = gmail._decode_message(message['raw'])
    assert decoded['In-Reply-To'] == '<one@example.test>'
    assert decoded['References'] == '<earlier@example.test> <one@example.test>'
    api.users().messages().send.assert_not_called()
    api.users().drafts().send.assert_not_called()


def test_rem_native_round_resumes_stalled_mail_archive_automatically(notebook, monkeypatch):
    write_json(state_path(notebook, 'consent.json'), {'authorized_at': service.now().isoformat()})
    calls = []
    monkeypatch.setattr(service, '_resume_archive', lambda root: calls.append(root))
    monkeypatch.setattr(native_round, '_jobs', lambda *a: [])
    native_round.prepare(notebook, read_config(notebook), scheduled=False)
    assert calls == [notebook]


def test_rem_queues_project_backlog_without_rewriting_recent_tiny_updates(notebook, monkeypatch):
    from connectonion.rem import project_pages
    book = Notebook(notebook)
    book.stub_project('projects/old.md', 'Old pilot', [])
    book.write('projects/recent.md', '# Recent pilot\n\nInvestigation: written 2026-09-07\n')
    old = (service.now() - timedelta(days=90)).isoformat()
    fresh = service.now().isoformat()
    monkeypatch.setattr('connectonion.rem.people_pages.correspondents_since', lambda *a, **kw: {'records': []})
    monkeypatch.setattr(project_pages, 'pending', lambda root, record: ([{'timestamp': fresh if 'recent' in record else old, 'text': 'Please review.', 'tool': 'codex', 'source': 'codex:fixture:1', 'cwd': '/fictional/pilot'}], 'update' if 'recent' in record else 'first'))
    monkeypatch.setattr(project_pages, 'page_state', lambda root, record: {'written_at': fresh, 'last_activity': fresh if 'recent' in record else old})
    records = {row['record'] for row in native_round._jobs(notebook, False, [], {})}
    assert 'projects/old.md' in records
    assert 'projects/recent.md' not in records


def test_rem_new_mail_during_drafting_requeues_instead_of_requesting_manual_discard(notebook):
    from connectonion.rem import drafts
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    directory = notebook / 'draft-in-flight'
    directory.mkdir()
    prepared = drafts.prepare(notebook, row, read_config(notebook), directory=directory)
    mail_thread(notebook, latest='two')
    result = native_round.check_task(notebook, {'handler': 'draft', 'task': prepared},
                                     {'result': json.dumps({'body': 'Review.', 'sources': ['gmail:one']})})
    assert result['discarded']
    assert drafts.queue(notebook)[0]['in_reply_to'] == 'two'


def test_rem_translation_attempts_reset_each_notebook_day(notebook):
    set_config(notebook, ['languages', 'zh'])
    Notebook(notebook).write('people/fern.md', '# Fern\n')
    cursor = native_round.prepare_translation_round(notebook, read_config(notebook), scheduled=False)
    cursor.update(task_day='2026-09-06', translation_attempts=[['zh', 'people/fern.md']])
    directory = notebook / 'next-day-translation'
    directory.mkdir()
    assert native_round.prepare_translation(notebook, cursor, read_config(notebook), directory)


def test_rem_native_later_round_does_not_requeue_stale_written_person(notebook, monkeypatch):
    record = 'people/fern.md'
    book = Notebook(notebook)
    book.stub_person(record, 'Fern', ['fern@example.test'], email='fern@example.test')
    previous = service.now().isoformat()
    row = {'record': record, 'mode': 'update', 'last_activity': (service.now() - timedelta(days=2)).isoformat()}
    monkeypatch.setattr('connectonion.rem.people_pages.correspondents_since', lambda *a, **kw: {'records': []})
    monkeypatch.setattr('connectonion.rem.people_pages.queue', lambda *a, **kw: [row])
    monkeypatch.setattr(daily, 'unfinished_by_recency', lambda root: [{'path': record, 'mode': 'update'}])
    jobs = native_round._jobs(notebook, False, [{'phase': 'daily-update', 'started_at': previous}], {})
    assert record not in {job['record'] for job in jobs}


@pytest.mark.parametrize('state', ['missing-mailbox', 'written', 'skipped'])
def test_rem_owner_setup_does_not_hand_work_back_as_a_command(notebook, state):
    from types import SimpleNamespace
    from connectonion.cli.commands.rem_commands import _first_page_skipped
    ctx = SimpleNamespace(obj={'root': notebook, 'default_root': False, 'json': False})
    result = {}
    if state != 'missing-mailbox':
        Notebook(notebook).write('people/owner.md', '# Owner\nInvestigation: investigated 2026-11-07\n')
        result['owner'] = {'record': 'people/owner.md', 'addresses': ['owner@example.test']}
    line = _first_page_skipped(ctx, notebook, result, want=state != 'skipped',
                               problem='', fix='', retry=['investigate', 'me'], init=['init'])
    assert 'co rem' not in line
    if state == 'missing-mailbox':
        assert 'co auth google' in line
        from connectonion.cli.commands.rem_commands import _investigate_me
        from connectonion.rem.files import RemError
        write_json(state_path(notebook, 'map.json'), {'owner': {'record': 'people/owner.md'}})
        with pytest.raises(RemError) as error:
            _investigate_me(notebook, days=None, quick=False)
        assert 'co auth google' in str(error.value)
        assert 'co rem' not in str(error.value)
