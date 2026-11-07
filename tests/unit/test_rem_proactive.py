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


@pytest.mark.parametrize('scheduled, enabled', [(False, False), (False, True), (True, False), (True, True)])
def test_rem_status_reports_queued_work_and_the_next_command(notebook, scheduled, enabled):
    from connectonion.cli.commands.rem_status import _notebook, notebook as counts
    Notebook(notebook).stub_person('people/fern.md', 'Fern Vale', ['fern@example.test'], email='fern@example.test')
    value = {'root': str(notebook), 'configured': True, 'next_run': 'tonight' if scheduled else None,
             'worker': {'enabled': enabled}}
    text = '\n'.join(_notebook(notebook, value, counts(notebook), lambda args: 'co rem ' + ' '.join(args)))
    assert ('1 people page queued for tonight' if scheduled and enabled else '1 people page not written') in text
    assert ('co rem investigate people' in text) == (not (scheduled and enabled))
    assert ('Work queued for the next scheduled run.' in text) == (scheduled and enabled)


@pytest.mark.parametrize('scheduled, enabled', [(False, False), (False, True), (True, False), (True, True)])
@pytest.mark.parametrize('arguments', [[], ['investigate'], ['show', 'people/fern.md'],
                                        ['show', 'projects/private.md'], ['show', 'people/held.md']])
def test_rem_next_leaves_scheduled_writing_to_rem(notebook, monkeypatch, scheduled, enabled, arguments):
    import shlex
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    book = Notebook(notebook)
    book.stub_person('people/fern.md', 'Fern Vale', ['fern@example.test'], email='fern@example.test')
    book.stub_person('people/held.md', 'Held contact', ['held@example.test'], email='held@example.test')
    book.stub_project('projects/private.md', 'Private', ['/repo/private'])
    write_json(state_path(notebook, 'map.json'), {'people': [{'record': 'people/held.md', 'needs_review': True}]})
    write_json(state_path(notebook, 'worker.json'), {'enabled': enabled})
    monkeypatch.setattr('connectonion.rem.schedule.default_scheduler', lambda *a, **kw: Mock(installed=lambda root: scheduled))
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), '--json', *arguments])
    assert result.exit_code == 0, result.output
    next_step = shlex.split(json.loads(result.stdout)['next'])[4:]
    if scheduled and enabled and arguments not in (['show', 'projects/private.md'], ['show', 'people/held.md']):
        assert next_step == ['status']
    else:
        assert next_step[:1] == ['investigate']


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
    assert state['status'] == 'skipped' and state['body'] == 'I will review it.'
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


def test_rem_reply_draft_keeps_the_owner_language_gist_and_background():
    from connectonion.rem import drafts
    task = {'row': {'id': 'x', 'material': [{'source': 'gmail:one'}], 'obligations': [], 'to': 'mia@example.com'}}
    result = drafts.check(task, {'result': json.dumps({'body': 'Hi Mia,\n\nThanks.', 'sources': ['gmail:one'],
                                                       'gist': '感谢并确认下周见。', 'why': 'Mia 是 Aurora 试点的负责人。'})})
    assert result['gist'] == '感谢并确认下周见。' and result['why'] == 'Mia 是 Aurora 试点的负责人。'
    assert 'material' not in result and 'obligations' not in result
    bare = drafts.check(task, {'result': json.dumps({'body': 'Hi', 'sources': ['gmail:one'], 'gist': '   '})})
    assert 'gist' not in bare and 'why' not in bare


def test_rem_reply_draft_prompt_runs_on_the_fixed_skill_and_the_owners_voice(tmp_path, monkeypatch):
    from connectonion.rem import drafts
    from connectonion.rem.config import default_config
    home = tmp_path / 'home'
    (home / '.claude/skills/email-writing').mkdir(parents=True)
    (home / '.claude/skills/email-writing/SKILL.md').write_text('# voice\n')
    monkeypatch.setattr(drafts.Path, 'home', classmethod(lambda cls: home))
    task = drafts.prepare(tmp_path, {'id': 'x', 'material': []}, default_config(), directory=tmp_path)
    assert 'rem-reply-draft/SKILL.md' in task['prompt']
    assert str(home / '.claude/skills/email-writing/SKILL.md') in task['prompt']
    assert 'Never send' not in task['prompt'] or 'follow it' in task['prompt']
    (home / '.claude/skills/email-writing/SKILL.md').unlink()
    assert 'email-writing' not in drafts.prepare(tmp_path, {'id': 'x', 'material': []}, default_config(), directory=tmp_path)['prompt']


@pytest.mark.parametrize('provider', ['gmail', 'outlook'])
def test_rem_send_replies_in_thread_with_the_edited_body_and_records_it(notebook, monkeypatch, provider):
    from connectonion.rem import drafts
    from connectonion.rem.files import read_json
    mail_thread(notebook, provider)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'I will review it.', 'sources': [provider + ':one']})
    client = Mock()
    client.reply.return_value = {'id': 'sent-1'}
    monkeypatch.setattr(drafts, 'mail_client', lambda kind: client)
    assert drafts.send(notebook, row['id'], 'I will review it on Tuesday.') == {'status': 'sent'}
    args, kwargs = client.reply.call_args
    assert args == (row['in_reply_to'], 'I will review it on Tuesday.')
    assert kwargs == ({'cc': row['cc'] or None} if provider == 'outlook' else {})
    saved = read_json(drafts.path(notebook, row['id']), {})
    assert saved['status'] == 'sent' and saved['body'] == 'I will review it on Tuesday.' and saved['sent_receipt'] == {'id': 'sent-1'}
    client.create_draft.assert_not_called()
    with pytest.raises(Exception, match='empty'):
        drafts.send(notebook, row['id'], '   ')


def test_rem_redraft_rewrites_for_a_chat_channel_and_send_goes_through_that_tool(notebook, monkeypatch):
    from connectonion.rem import drafts, runner
    from connectonion.rem.files import read_json
    mail_thread(notebook, 'gmail')
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'Dear Mia, I will review it.', 'sources': ['gmail:one']})

    def fake_turn(workspace, prompt, config, stage, session=''):
        material = json.loads((workspace / 'reply-material.json').read_text())
        assert material['channel'] == 'lark' and 'owner' in material and 'person' in material
        (workspace / 'candidate.json').write_text(json.dumps({'body': '看过了，周二前给你反馈。', 'gist': '简短确认', 'why': '她是试点负责人', 'sources': ['gmail:one']}))
        return {'outcome': 'natural'}
    monkeypatch.setattr(runner, 'run_task', fake_turn)
    saved = drafts.redraft(notebook, row['id'], 'lark')
    assert saved['channel'] == 'lark' and saved['body'] == '看过了，周二前给你反馈。' and saved['status'] == 'prepared'
    with pytest.raises(Exception, match='Unknown channel'):
        drafts.redraft(notebook, row['id'], 'pigeon')

    commands = []

    def fake_run(command, capture_output, text):
        commands.append(command)
        payload = {'items': [{'name': 'Mia', 'open_id': 'ou_mia'}]} if command[1] == 'contact' else {'message_id': 'om_1'}
        return type('Done', (), {'returncode': 0, 'stdout': json.dumps(payload), 'stderr': ''})()
    monkeypatch.setattr(drafts.subprocess, 'run', fake_run)
    client = Mock()
    monkeypatch.setattr(drafts, 'mail_client', lambda kind: client)
    assert drafts.send(notebook, row['id']) == {'status': 'sent'}
    assert commands[0][:3] == ['lark-cli', 'contact', '+search-user'] and row['to'] in commands[0]
    assert commands[1][:3] == ['lark-cli', 'im', '+messages-send'] and 'ou_mia' in commands[1] and '看过了，周二前给你反馈。' in commands[1]
    client.reply.assert_not_called()
    assert read_json(drafts.path(notebook, row['id']), {})['sent_receipt'] == {'message_id': 'om_1'}


def test_rem_prepare_now_drafts_one_waiting_thread_on_the_owners_click(notebook, monkeypatch):
    from connectonion.rem import drafts, runner
    mail_thread(notebook, 'gmail')
    row = drafts.queue(notebook)[0]

    def fake_turn(workspace, prompt, config, stage, session=''):
        (workspace / 'candidate.json').write_text(json.dumps({'body': 'Hi Mia, Tuesday works.', 'gist': '周二可以', 'why': '她在等回复', 'sources': ['gmail:one']}))
        return {'outcome': 'natural'}
    monkeypatch.setattr(runner, 'run_task', fake_turn)
    saved = drafts.prepare_now(notebook, row['provider'], row['thread'])
    assert saved['status'] == 'prepared' and saved['body'] == 'Hi Mia, Tuesday works.' and saved['id'] == row['id']
    assert drafts.queue(notebook) == []
    with pytest.raises(Exception, match='cannot be drafted yet'):
        drafts.prepare_now(notebook, 'gmail', 'mail:gmail:no-such-thread')


def test_rem_send_refuses_a_second_send_of_the_same_draft(notebook, monkeypatch):
    from connectonion.rem import drafts
    mail_thread(notebook, 'outlook')
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'Sent once.', 'sources': ['outlook:one']})
    client = Mock()
    client.reply.return_value = {'id': 'sent-1'}
    monkeypatch.setattr(drafts, 'mail_client', lambda kind: client)
    assert drafts.send(notebook, row['id']) == {'status': 'sent'}
    with pytest.raises(Exception, match='already sent'):
        drafts.send(notebook, row['id'])
    assert client.reply.call_count == 1


def draft_check_task(root, *, direct_send='partner', send='now', kind='reply'):
    from connectonion.rem import drafts
    mail_thread(root)
    book = Notebook(root)
    book.write('people/fern.md', book.read('people/fern.md') + '\n## Facts\n- Email: fern@example.test\n- Direct send: ' + direct_send + '\n')
    directory = root / 'check-draft'
    directory.mkdir()
    write_json(directory / 'verdict.json', {'kind': kind, 'send': send})
    task = drafts.prepare(root, drafts.queue(root)[0], read_config(root), directory=directory)
    return task


@pytest.mark.parametrize('change, direct_send, problem', [
    ({'body': '可以。 【需要你：成本假设怎么看 — 11月10日】'}, 'partner', 'slot'),
    ({'needs_owner': ['【需要你：成本假设怎么看 — 11月10日】']}, 'close', 'needs_owner'),
    ({}, 'none', 'direct_send'),
])
def test_rem_reply_draft_check_enforces_each_direct_send_gate(notebook, change, direct_send, problem):
    from connectonion.rem import drafts
    from connectonion.rem.files import RemError
    task = draft_check_task(notebook, direct_send=direct_send)
    candidate = {'body': '周二可以。', 'sources': ['gmail:one'], 'verdict': 'reply', 'send': 'now', 'needs_owner': [], **change}
    with pytest.raises(RemError, match=problem) as error:
        drafts.check(task, {'result': json.dumps(candidate)})
    assert 'Fix ' + task['candidate'] in str(error.value)


@pytest.mark.parametrize('direct_send', ['partner', 'close'])
@pytest.mark.parametrize('decision, writer', [('now', 'now'), ('now', 'owner'), ('owner', 'owner')])
def test_rem_reply_draft_check_preserves_or_lowers_send(notebook, direct_send, decision, writer):
    from connectonion.rem import drafts
    task = draft_check_task(notebook, direct_send=direct_send, send=decision)
    needs = ['【需要你：成本假设怎么看 — 11月10日】'] if writer == 'owner' else []
    value = {'body': '周二可以。' + ''.join(needs), 'sources': ['gmail:one'],
             'verdict': 'reply', 'send': writer, 'needs_owner': needs, 'why': '合伙人；11月7日约定；已等3天'}
    result = drafts.check(task, {'result': json.dumps(value)})
    assert {key: result[key] for key in ('verdict', 'send', 'needs_owner')} == {
        'verdict': 'reply', 'send': writer, 'needs_owner': needs}


@pytest.mark.parametrize('decision', ['owner', None])
def test_rem_reply_draft_writer_cannot_raise_send(notebook, decision):
    from connectonion.rem import drafts
    from connectonion.rem.files import RemError
    task = draft_check_task(notebook, send=decision)
    if decision is None:
        (Path(task['candidate']).parent / 'verdict.json').unlink()
    with pytest.raises(RemError, match='raise'):
        drafts.check(task, {'result': json.dumps({'body': 'Confirmed.', 'sources': ['gmail:one'],
                     'verdict': 'reply', 'send': 'now', 'needs_owner': [], 'person': {'direct_send': 'partner'}})})


def test_rem_writer_cannot_raise_send_by_rewriting_the_verdict_file(notebook):
    from connectonion.rem import drafts
    from connectonion.rem.files import RemError
    task = draft_check_task(notebook, send='owner')
    write_json(Path(task['candidate']).parent / 'verdict.json', {'kind': 'reply', 'send': 'now'})
    with pytest.raises(RemError, match='raise'):
        drafts.check(task, {'result': json.dumps({'body': 'Confirmed.', 'sources': ['gmail:one'],
                     'verdict': 'reply', 'send': 'now', 'needs_owner': []})})


def test_rem_direct_send_permission_must_belong_to_the_recipient(notebook):
    from connectonion.rem import drafts
    from connectonion.rem.files import RemError
    task = draft_check_task(notebook)
    book = Notebook(notebook)
    book.write('people/fern.md', book.read('people/fern.md').replace('Email: fern@example.test', 'Email: other@example.test'))
    task = drafts.prepare(notebook, task['row'], read_config(notebook), directory=Path(task['candidate']).parent)
    assert read_json(Path(task['input_paths'][0]), {})['person']['direct_send'] == 'none'
    with pytest.raises(RemError, match='direct_send'):
        drafts.check(task, {'result': json.dumps({'body': 'Confirmed.', 'sources': ['gmail:one'],
                     'verdict': 'reply', 'send': 'now', 'needs_owner': []})})


@pytest.mark.parametrize('body', [None, ''])
def test_rem_no_reply_needs_no_body_and_is_promoted_as_no_reply(notebook, body):
    from connectonion.rem import drafts
    task = draft_check_task(notebook, send='owner', kind='no_reply')
    value = {'verdict': 'no_reply', 'send': 'owner', 'needs_owner': [], 'sources': ['gmail:one'],
             'gist': '需要你到场，已等3天。', 'why': '合伙人；11月7日约定；到场已等3天'}
    if body is not None:
        value['body'] = body
    result = drafts.check(task, {'result': json.dumps(value)})
    drafts.promote(notebook, result)
    saved = drafts.listing(notebook)[0]
    assert saved['status'] == 'no_reply' and saved['verdict'] == 'no_reply'
    assert saved['gist'] == value['gist'] and not saved.get('body')
    assert drafts.queue(notebook) == []


def test_rem_no_reply_still_requires_thread_evidence(notebook):
    from connectonion.rem import drafts
    from connectonion.rem.files import RemError
    task = draft_check_task(notebook, send='owner', kind='no_reply')
    with pytest.raises(RemError, match='sources'):
        drafts.check(task, {'result': json.dumps({'verdict': 'no_reply', 'sources': ['gmail:invented']})})


@pytest.mark.parametrize('action', ['send', 'open_provider'])
def test_rem_no_reply_cannot_create_or_send_an_empty_reply(notebook, monkeypatch, action):
    from connectonion.rem import drafts
    from connectonion.rem.files import RemError
    task = draft_check_task(notebook, send='owner', kind='no_reply')
    result = drafts.check(task, {'result': json.dumps({'verdict': 'no_reply', 'sources': ['gmail:one'],
                         'gist': '需要你到场。'})})
    drafts.promote(notebook, result)
    client = Mock()
    monkeypatch.setattr(drafts, 'mail_client', lambda kind: client)
    with pytest.raises(RemError, match='no reply'):
        getattr(drafts, action)(notebook, result['id'])
    client.reply.assert_not_called()
    client.create_draft.assert_not_called()


@pytest.mark.parametrize('level', ['partner', 'close', 'none'])
def test_rem_draft_identities_include_owner_voice_open_threads_and_permission(notebook, level):
    from connectonion.rem import drafts
    mail_thread(notebook)
    book = Notebook(notebook)
    book.write('people/fern.md', book.read('people/fern.md') + '\n## How the user writes to them\n名字加逗号，一行，不用谢谢。\n\n## Facts\n- Email: fern@example.test\n- Direct send: ' + level + '\n')
    task = drafts.prepare(notebook, drafts.queue(notebook)[0], read_config(notebook), directory=notebook)
    material = read_json(Path(task['input_paths'][0]), {})
    assert material['person']['how_the_user_writes_to_them'] == '名字加逗号，一行，不用谢谢。'
    assert 'You owe Fern a pilot review.' in material['person']['open_threads']
    assert material['person']['direct_send'] == level
    assert material['owner_samples'] == []


def test_rem_draft_permission_is_not_inferred_from_relationship(notebook):
    from connectonion.rem import drafts
    mail_thread(notebook)
    book = Notebook(notebook)
    book.write('people/fern.md', book.read('people/fern.md') + '\n## Our relationship\nClose partner. Direct send: partner\n')
    assert drafts._identities(notebook, drafts.queue(notebook)[0])['person']['direct_send'] == 'none'


def test_rem_draft_direct_send_recognizes_the_pages_mapped_alias(notebook):
    from connectonion.rem import drafts
    task = draft_check_task(notebook)
    book = Notebook(notebook)
    book.write('people/fern.md', book.read('people/fern.md').replace('Email: fern@example.test', 'Email: primary@example.test'))
    mapped = read_json(state_path(notebook, 'map.json'), {})
    mapped['people'] = [{'record': 'people/fern.md', 'address': 'primary@example.test', 'addresses': ['FERN@example.test']}]
    write_json(state_path(notebook, 'map.json'), mapped)
    assert drafts._identities(notebook, task['row'])['person']['direct_send'] == 'partner'


def test_rem_owner_samples_are_verbatim_to_this_address_recent_and_thread_language_first(notebook):
    from connectonion.rem import drafts
    from connectonion.rem.mail_archive import retain_message
    from connectonion.rem.store import refresh
    mail_thread(notebook)
    for number, (sender, recipient, body) in enumerate([
        ('owner@example.test', 'fern@example.test', 'Fern, confirmed for Tuesday.\nOwner'),
        ('OWNER@example.test', 'FERN@example.test', 'Fern, the pilot works.\nOwner'),
        ('owner@example.test', 'fern@example.test', 'Fern, use the second file.\nOwner'),
        ('owner@example.test', 'fern@example.test', 'Fern, the review is attached.\nOwner'),
        ('owner@example.test', 'fern@example.test', '小芬，周二见，带上那份合同。'),
        ('owner@example.test', 'other@example.test', 'Wrong recipient, never include this.'),
        ('fern@example.test', 'owner@example.test', 'Other person, never include this.'),
    ]):
        retain_message(notebook, 'outlook', {'id': f'sample-{number}', 'from': sender, 'to': [recipient],
                       'subject': 'Earlier', 'thread': 'earlier', 'date': f'2026-11-06T0{number}:00:00Z'}, body,
                       fetched_at=service.now().isoformat())
    refresh(notebook)
    task = drafts.prepare(notebook, drafts.queue(notebook)[0], read_config(notebook), directory=notebook)
    samples = read_json(Path(task['input_paths'][0]), {})['owner_samples']
    assert [sample['source'] for sample in samples] == ['outlook:sample-3', 'outlook:sample-2', 'outlook:sample-1']
    assert samples[0]['message']['body'] == 'Fern, the review is attached.\nOwner'


def test_native_no_reply_commit_and_recovery_preserve_verdict(notebook, monkeypatch):
    from connectonion.rem import drafts, quota
    mail_thread(notebook)
    write_json(state_path(notebook, 'consent.json'), {'authorized_at': service.now().isoformat()})
    write_json(state_path(notebook, 'subscriptions.json'), {})
    monkeypatch.setattr(quota, 'read', lambda config: {'unknown': 'fixture'})
    monkeypatch.setattr('connectonion.rem.project_material.extract', lambda *a, **kw: {})
    task = native.next_task(notebook)
    Path(task['candidate']).write_text(json.dumps({'verdict': 'no_reply', 'sources': ['gmail:one']}))
    assert native.submit(notebook, task['id'])['outcome'] == 'accepted'
    saved = drafts.listing(notebook)[0]
    assert saved['status'] == 'no_reply'
    receipt_task = {'directory': str(Path(task['candidate']).parent)}
    drafts.path(notebook, saved['id']).unlink()
    native_round.recover_commit(notebook, receipt_task)
    assert read_json(drafts.path(notebook, saved['id']), {})['status'] == 'no_reply'


@pytest.mark.parametrize('action, body', [('send', None), ('send', ''), ('send', 'Edited reply'), ('open_provider', None)])
@pytest.mark.parametrize('status, verdict, saved_body', [
    ('no_reply', 'no_reply', 'Unexpected body'),
    ('prepared', 'no_reply', 'Unexpected body'),
    ('prepared', 'reply', '   '),
])
def test_reply_boundaries_refuse_no_reply_and_empty_final_body(notebook, monkeypatch, action, body, status, verdict, saved_body):
    from connectonion.rem import drafts
    from connectonion.rem.files import RemError
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    write_json(drafts.path(notebook, row['id']), {**row, 'status': status, 'verdict': verdict, 'body': saved_body,
                                               'provider_draft': {'url': 'https://example.test/draft'}})
    client = Mock()
    client.reply.return_value = {'id': 'sent'}
    monkeypatch.setattr(drafts, 'mail_client', lambda provider: client)
    if verdict == 'reply' and body and body.strip():
        assert drafts.send(notebook, row['id'], body) == {'status': 'sent'}
        client.reply.assert_called_once_with(row['in_reply_to'], body)
    else:
        with pytest.raises(RemError):
            if action == 'send':
                drafts.send(notebook, row['id'], body)
            else:
                drafts.open_provider(notebook, row['id'])
        assert not client.mock_calls


def test_nights_three_drafts_cover_the_first_three_today_cards(notebook, monkeypatch):
    from connectonion.rem import drafts
    from connectonion.rem.mail_archive import retain_message
    from connectonion.rem.reader import snapshot
    from connectonion.rem.store import refresh
    monkeypatch.setattr(service, 'mail_available', lambda kind: False)
    from datetime import datetime, timezone
    monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc))
    set_config(notebook, ['limits.drafts_per_night', '3'])
    book = Notebook(notebook)
    write_json(state_path(notebook, 'map.json'), {'owner': {'record': 'people/me.md', 'addresses': ['owner@example.test']}})
    for index in range(12):
        book.write(f'people/fern-{index}.md', f'# Fern {index}\n\n## Open threads\n'
                   f'- You owe Fern {index} a review; due 2026-11-{index + 1:02}. [1]\n\n'
                   f'## Sources\n- [1] gmail:review-{index}\n')
        retain_message(notebook, 'gmail', {'id': f'review-{index}', 'from': f'fern-{index}@example.test',
                       'to': ['owner@example.test'], 'subject': 'Review', 'thread': f'review-{index}',
                       'date': f'2026-11-{index + 1:02}T01:00:00+00:00'}, 'Please review.', fetched_at=service.now().isoformat())
    refresh(notebook)
    cap = read_config(notebook)['limits']['drafts_per_night']
    rows = drafts.queue(notebook)[:cap]
    assert [row['thread'] for row in rows] == [f'mail:gmail:review-{i}' for i in range(3)]
    for row in rows:
        drafts.promote(notebook, {**row, 'body': 'The review is attached.', 'sources': [row['version']]})
    data = snapshot(notebook, local=True)
    first = [row for row in data['today_queue'] if row['section'] == 'today'][:cap]
    assert [row['reply']['thread'] for row in first] == [row['thread'] for row in rows]
    assert {row['thread'] for row in data['drafts'] if row['status'] == 'prepared'} == {row['reply']['thread'] for row in first}


@pytest.mark.parametrize('body', ['My feedback: [Add your feedback on Demo A here.]',
                                 'My feedback: 【Please add feedback】', 'My feedback: ［填写意见］',
                                 'My feedback: 【需要你：意见】', 'My feedback: 【需要你： — 】', 'My feedback: 【需要你：意见 — date not agreed',
                                 'My feedback: [Add feedback'])
def test_reply_check_rejects_noncanonical_bracketed_slots(notebook, body):
    from connectonion.rem import drafts
    from connectonion.rem.files import RemError
    task = draft_check_task(notebook, send='owner')
    with pytest.raises(RemError, match='slot'):
        drafts.check(task, {'result': json.dumps({'body': body, 'sources': ['gmail:one'], 'send': 'owner'})})


@pytest.mark.parametrize('body', ['Feedback: 【需要你：演示意见 — date not agreed】',
                                 'Feedback: [Add feedback here.]', 'Feedback: [Add feedback',
                                 'Feedback: 【需要你：意见 — date not agreed'])
@pytest.mark.parametrize('edited', [False, True])
def test_reply_send_refuses_marked_parts_before_contacting_any_provider(notebook, monkeypatch, body, edited):
    from connectonion.rem import drafts
    from connectonion.rem.files import RemError
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'Complete.' if edited else body, 'sources': ['gmail:one']})
    client = Mock()
    client.reply.return_value = {'id': 'sent'}
    monkeypatch.setattr(drafts, 'mail_client', lambda kind: client)
    with pytest.raises(RemError, match='Fill the marked part first'):
        drafts.send(notebook, row['id'], body if edited else None)
    client.reply.assert_not_called()
    assert read_json(drafts.path(notebook, row['id']), {})['status'] == 'prepared'


@pytest.mark.parametrize('provider', ['gmail', 'outlook'])
def test_today_reply_state_uses_latest_archived_sender_and_missing_original(notebook, provider):
    from connectonion.rem.mail_archive import retain_message, observed_message_path
    from connectonion.rem.store import refresh
    from connectonion.rem.today import queue
    mail_thread(notebook, provider)
    assert queue(notebook)[0]['reply']['state'] == 'queued'
    observed_message_path(notebook, provider, 'one').unlink()
    reply = queue(notebook)[0]['reply']
    assert reply['state'] == 'unarchived' and reply['provider'] == provider
    retain_message(notebook, provider, {'id': 'own-promise', 'from': 'owner@example.test',
                   'to': ['fern@example.test'], 'subject': 'Pilot review', 'thread': 'pilot',
                   'date': '2026-11-07T03:00:00+00:00'}, "I'll watch the demo and send feedback.", fetched_at=service.now().isoformat())
    refresh(notebook)
    reply = queue(notebook)[0]['reply']
    assert reply['state'] == 'task' and reply['last_word_yours']
    assert reply['since'] == '2026-11-07'
    assert reply['source'] == provider + ':own-promise'
    assert reply['promise'] == "I'll watch the demo and send feedback."


def test_today_morning_selects_the_named_counterparts_request_once_per_page(notebook):
    from datetime import date
    from connectonion.rem.today import queue
    records = []
    for name, lines in [('Mara', ['You owe Fern a talk abstract.', 'You owe Mara the signed draft.', 'You owe Mara a second answer.']),
                        ('Fern', ['You owe Fern the signed draft.']), ('Avery', ['You owe Avery the receipts.'])]:
        path = f'people/{name.lower()}.md'
        text = '# ' + name + '\n\n## Open threads\n' + '\n'.join('- ' + line for line in lines)
        Notebook(notebook).write(path, text)
        records.append({'path': path, 'text': text, 'title': name})
    morning = [row for row in queue(notebook, records=records, contexts={}, as_of=date(2026, 11, 8)) if row['section'] == 'morning']
    assert [row['text'] for row in morning] == ['You owe Mara the signed draft.', 'You owe Fern the signed draft.', 'You owe Avery the receipts.']


def test_today_order_does_not_depend_on_reader_excerpt_budget(notebook):
    from datetime import date
    from connectonion.rem.today import queue
    mail_thread(notebook)
    Notebook(notebook).write('people/avery.md', '# Avery\n\n## Open threads\n- You owe Avery a receipt.\n')
    full = queue(notebook, as_of=date(2026, 11, 8))
    without_excerpts = queue(notebook, contexts={}, as_of=date(2026, 11, 8))
    assert [(row['key'], row['since']) for row in without_excerpts] == [(row['key'], row['since']) for row in full]


@pytest.mark.parametrize('day', ['31 November', 'November 00', '2026-13-12', '2026-11-31'])
def test_today_ignores_invalid_notebook_dates_instead_of_breaking_the_reader(notebook, day):
    from datetime import date
    from connectonion.rem.today import queue
    Notebook(notebook).write('people/fern.md', f'# Fern\n\n## Open threads\n- You owe Fern a review; since {day}.\n')
    rows = queue(notebook, contexts={}, as_of=date(2026, 11, 8))
    assert rows[0]['since'] == '' and rows[0]['section'] == 'morning'


def test_waiting_on_someone_else_is_not_advertised_as_draftable(notebook):
    from connectonion.rem import drafts
    from connectonion.rem.today import queue
    mail_thread(notebook)
    book = Notebook(notebook)
    book.write('people/fern.md', book.read('people/fern.md').replace('You owe Fern a pilot review.', 'You asked Fern for a pilot review.'))
    assert drafts.queue(notebook) == []
    assert queue(notebook)[0]['reply']['state'] == 'waiting'
