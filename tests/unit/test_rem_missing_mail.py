"""Deleted mailbox evidence cannot monopolise scheduled preparation (#3073)."""

import json
from datetime import datetime, timedelta, timezone
from subprocess import CompletedProcess
from types import SimpleNamespace

import httpx
import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import codex_exec, codex_schedule, drafts, fetch_stalls, investigate as inv, native, native_round, night_mail, service
from connectonion.rem.config import read_config
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from connectonion.rem.mail import MissingMail, read_mail
from connectonion.useful_tools.gmail_mailbox import MailboxError
from tests.unit.test_rem_fetch_stalls import Mailbox, notebook, round_of


def gone(status=404):
    return MailboxError('not_found' if status == 404 else 'provider_error', f'Gmail read failed (HTTP {status}).')


@pytest.mark.parametrize('status', [404, 410])
def test_scheduled_next_parks_gmail_attachment_metadata_and_serves_other_work(notebook, monkeypatch, status):
    round_of(notebook, monkeypatch, ['orgs/lantern.md'])
    book = Notebook(notebook)
    book.write('orgs/lantern.md', '# Lantern\n\n- Domain: lantern.example\n')
    mailbox = Mailbox(attachment_errors={'mail-1': lambda: gone(status)})
    monkeypatch.setattr(native_round, '_prepare_investigation', lambda *a: inv.gather(
        'Lantern', ['lantern.example'], days=5, clients={'gmail': mailbox}, subscriptions={},
        archive_root=notebook, record='orgs/lantern.md', attachments_dir=notebook / 'attachments', lock_held=True))
    task = native.next_task(notebook, scheduled=True)
    assert task['outcome'] == 'task' and task['record'] == 'projects/heron.md'
    parked = read_json(state_path(notebook, fetch_stalls.LEDGER), {})['items']['orgs/lantern.md']
    assert parked['missing_id'] == 'mail-1'
    assert 'no longer exists' in parked['error']
    assert any('mail-1' in notice for notice in task['notices'])


@pytest.mark.parametrize('status', [404, 410])
@pytest.mark.parametrize('provider', ['gmail', 'outlook'])
@pytest.mark.parametrize('record', ['people/ivy.md', 'orgs/lantern.md', 'projects/pilot.md'])
def test_investigate_body_parks_gone_evidence(notebook, provider, status, record):
    mailbox = Mailbox(body_errors={'mail-1': lambda: gone(status)})
    with pytest.raises(MissingMail, match='mail-1.*no longer exists'):
        inv.gather('Ivy', ['ivy@lantern.example', 'lantern.example'], days=5, clients={provider: mailbox}, subscriptions={},
                   archive_root=notebook, record=record, lock_held=True)


@pytest.mark.parametrize('site', ['body', 'attachments', 'night-metadata', 'night-body'])
@pytest.mark.parametrize('status', [401, 403, 429, 500, 'network'])
def test_other_mailbox_read_errors_stay_failures(notebook, monkeypatch, site, status):
    monkeypatch.setattr('time.sleep', lambda seconds: None)
    error = httpx.ConnectError('Mailbox network unavailable') if status == 'network' else gone(status)
    mailbox = Mailbox(**{('body_errors' if site == 'body' else 'attachment_errors'): {'mail-1': lambda: error}})
    if site.startswith('night'):
        write_json(state_path(notebook, 'subscriptions.json'), {'gmail': {'enabled': True, 'consented': True}})
        monkeypatch.setattr(night_mail, '_client', lambda provider: mailbox)
        monkeypatch.setattr(night_mail, '_metadata', lambda *a: (_ for _ in ()).throw(error) if site == 'night-metadata' else {'id': 'mail-1'})
        mailbox.get_email_body = lambda key: (_ for _ in ()).throw(error)
        call = lambda: night_mail._fetch(notebook, 'gmail:mail-1', {})
    else:
        call = lambda: inv.gather('Ivy', ['ivy@lantern.example'], days=5, clients={'gmail': mailbox},
                                  subscriptions={}, archive_root=notebook, record='people/ivy.md',
                                  attachments_dir=notebook / 'attachments', lock_held=True)
    with pytest.raises(type(error)) as caught:
        call()
    assert caught.value is error


@pytest.mark.parametrize('site', ['metadata', 'body'])
@pytest.mark.parametrize('status', [404, 410])
def test_night_cited_original_is_parked_once(notebook, monkeypatch, site, status):
    write_json(state_path(notebook, 'subscriptions.json'), {'gmail': {'enabled': True, 'consented': True}})
    calls = []
    def missing(*args):
        calls.append(site)
        raise gone(status)
    mailbox = Mailbox()
    monkeypatch.setattr(night_mail, '_client', lambda provider: mailbox)
    monkeypatch.setattr(night_mail, '_metadata', missing if site == 'metadata' else lambda *a: {'id': 'mail-1'})
    if site == 'body':
        mailbox.get_email_body = missing
    rows = [{'reply': {'state': 'unarchived', 'source': 'gmail:mail-1'}}]
    first = night_mail.fetch_missing(notebook, rows)
    assert 'mail-1' in first['gmail:mail-1'] and 'no longer exists' in first['gmail:mail-1']
    assert night_mail.fetch_missing(notebook, rows) == first
    assert calls == [site]


def test_second_turn_leaves_missing_page_parked_until_page_changes(notebook, monkeypatch):
    book = Notebook(notebook)
    book.stub_person('people/ivy.md', 'Ivy')
    def missing(key):
        raise gone()
    with pytest.raises(MissingMail) as caught:
        read_mail(missing, 'mail-1', provider='gmail')
    job = {'record': 'people/ivy.md', 'kind': 'person'}
    fetch_stalls.park(notebook, job, caught.value)
    moment = service.now()
    monkeypatch.setenv('CO_REM_TURN_ID', 'second-turn')
    monkeypatch.setattr(service, 'now', lambda: moment + timedelta(days=2))
    assert native_round._with_parked(notebook, [job]) == []
    assert fetch_stalls.due(notebook) == {}
    book.write(job['record'], book.read(job['record']) + '\nNew mail arrived.\n')
    assert native_round._with_parked(notebook, [job]) == [job]


def test_every_candidate_parked_is_a_failed_turn_with_reason(notebook, monkeypatch):
    round_of(notebook, monkeypatch, ['people/ivy.md'])
    cursor = read_json(state_path(notebook, 'round.json'), {})
    cursor['jobs'] = cursor['jobs'][:1]
    write_json(state_path(notebook, 'round.json'), cursor)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_schedule.CodexNative, 'recent_desktop_fire', lambda *a: False)
    def run(command, **kwargs):
        monkeypatch.setenv('CO_REM_TURN_ID', kwargs['env']['CO_REM_TURN_ID'])
        result = CliRunner().invoke(app, ['rem', '--root', str(notebook), 'next', '--scheduled', '--json'])
        assert result.exit_code == 1
        assert 'parked' in result.output.lower()
        return CompletedProcess(command, 0)
    assert codex_exec.run_turn(notebook, run=run) == 'failed'
    receipt = read_json(state_path(notebook, 'last-turn.json'), {})
    assert 'parked' in receipt['reason'].lower()


def test_draft_preparation_uses_saved_mail_without_a_mailbox_read(notebook, monkeypatch):
    from tests.unit.test_rem_proactive import night_item
    night_item(notebook, 0)
    monkeypatch.setattr(drafts, 'mail_client', lambda *a: pytest.fail('draft preparation is offline'))
    row = drafts.queue(notebook)[0]
    task = drafts.prepare(notebook, row, read_config(notebook), directory=notebook)
    assert task['row']['version'] == 'gmail:ask-0'


def test_offered_pending_task_counts_as_served_in_its_new_turn(notebook, monkeypatch):
    round_of(notebook, monkeypatch, [])
    offered = native.next_task(notebook)
    monkeypatch.setenv('CO_REM_TURN_ID', 'new-turn')
    again = native.next_task(notebook, scheduled=True)
    assert again['id'] == offered['id']
    assert read_json(state_path(notebook, 'round.json'), {})['served_turn'] == 'new-turn'


@pytest.mark.parametrize('status', [404, 410])
@pytest.mark.parametrize('error_type', ['gmail-sdk', 'gmail-mailbox', 'outlook'])
def test_mail_queue_drops_missing_native_id_and_keeps_next_message(status, error_type):
    from googleapiclient.errors import HttpError
    from connectonion.provider_credentials import ProviderCredentialError
    from connectonion.rem.mail import collect_mail
    from tests.unit.test_rem_mail import FakeMail, NOW, mail, references, subscription
    error = (HttpError(SimpleNamespace(status=status, reason='Gone'), b'{}') if error_type == 'gmail-sdk'
             else ProviderCredentialError('provider_unavailable', f'Graph HTTP {status}', 'co outlook inbox', status=status)
             if error_type == 'outlook' else gone(status))
    class Deleted(FakeMail):
        def get_email_body(self, identity):
            if identity == 'm1':
                raise error
            return super().get_email_body(identity)
    client = Deleted([mail(1, '2026-09-02T09:00:00+00:00'), mail(2, '2026-09-03T09:00:00+00:00')])
    batch = collect_mail(subscription(), {}, 10, 100000, client, now=NOW)
    assert references(batch) == ['outlook:m2']
    assert batch.dropped_missing == 1 and batch.progress['dropped_missing'] == ['m1']
    again = collect_mail(subscription(), batch.progress, 10, 100000, client, now=NOW)
    assert not again.items and not again.dropped_missing
    assert again.progress['dropped_missing'] == ['m1']


@pytest.mark.parametrize('status', [404, 410])
def test_mail_search_moves_past_missing_message(notebook, status):
    mailbox = Mailbox(body_errors={'mail-1': lambda: gone(status)})
    mailbox.list_search = lambda query, limit: mailbox.rows
    found = inv.mail_search({'gmail': mailbox}, notebook)(['pilot'])
    assert len(found) == 1 and found[0]['subject'] == 'Pilot note 2'


@pytest.mark.parametrize('status', [404, 410])
def test_archive_preparation_records_gone_id_and_keeps_other_mail(notebook, status):
    from connectonion.rem.mail_archive import archive_init
    moment = datetime.now(timezone.utc)
    mailbox = Mailbox(body_errors={'mail-1': lambda: gone(status)})
    state_path(notebook, 'source-inventory.jsonl').write_text(''.join(
        json.dumps({'type': 'mail', 'source': 'gmail', **row}) + '\n' for row in mailbox.rows))
    result = archive_init(notebook, {'started': moment.isoformat(), 'days': 5}, {'gmail': mailbox})
    assert result['phase'] == 'complete' and result['failed'] == 0 and result['saved'] == 1
    assert result['dropped_missing'][0]['id'] == 'mail-1'


def test_night_lists_missing_original_as_could_not_prepare(notebook, monkeypatch):
    from connectonion.rem import night
    from tests.unit.test_rem_proactive import night_item
    night_item(notebook, 0, archived=False)
    write_json(state_path(notebook, 'subscriptions.json'), {'gmail': {'enabled': True, 'consented': True}})
    mailbox = Mailbox()
    mailbox.get_email_body = lambda identity: (_ for _ in ()).throw(gone())
    monkeypatch.setattr(night_mail, '_client', lambda provider: mailbox)
    assert night.prepare(notebook, read_config(notebook)) == []
    outcome = night.listing(notebook)[0]
    assert outcome['kind'] == 'could_not_prepare'
    assert outcome['source'] in outcome['reason'] or outcome['source'].partition(':')[2] in outcome['reason']
    assert 'no longer exists' in outcome['reason']


def test_every_next_raising_mailbox_error_keeps_error_in_failed_receipt(notebook, monkeypatch):
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_schedule.CodexNative, 'recent_desktop_fire', lambda *a: False)
    error = gone(403)
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(native, 'next_task', fail)
    def run(command, **kwargs):
        monkeypatch.setenv('CO_REM_TURN_ID', kwargs['env']['CO_REM_TURN_ID'])
        for _ in range(2):
            result = CliRunner().invoke(app, ['rem', '--root', str(notebook), 'next', '--scheduled', '--json'])
            assert result.exit_code == 1 and result.exception is error
        return CompletedProcess(command, 0)
    assert codex_exec.run_turn(notebook, run=run) == 'failed'
    receipt = read_json(state_path(notebook, 'last-turn.json'), {})
    assert receipt['reason'] == str(error)
    assert read_json(state_path(notebook, f"turns/{receipt['turn_id']}.json"), {}) == receipt
