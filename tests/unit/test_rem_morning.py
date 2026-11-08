"""Fictional overnight work; no real transport or model is used."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from connectonion.rem import morning as _morning, service
from connectonion.rem.config import prepare, set_config, read_config
from connectonion.rem.files import read_json, state_path, write_json

REAL_ACTIONABLE = _morning.actionable  # captured before any fixture replaces it

# Decision rows as approvals.outcomes() shapes them; titles are notebook page titles,
# written in the notebook's own language.
ROWS = {'zh': [{'id': 'reply:mara', 'kind': 'reply', 'title': 'Mara Quill', 'text': 'Fernhill 试点何时开始'},
               {'id': 'task:plan', 'kind': 'task', 'title': 'Fernhill 计划', 'text': '把试点计划写出来'}],
        'en': [{'id': 'reply:mara', 'kind': 'reply', 'title': 'Mara Quill', 'text': 'when the Fernhill pilot starts'},
               {'id': 'task:plan', 'kind': 'task', 'title': 'Fernhill plan', 'text': 'write up the pilot plan'}]}

FULL = {'zh': '昨夜：替你发出 1 封回复，另拟好 1 封待你看；跑完 1 项任务，查清 1 个问题。\n'
              '2 件要你拍板：\n'
              '· 以你的名义回 Mara Quill（Fernhill 试点何时开始）——用我拟的稿？\n'
              '· Fernhill 计划——花一次 Codex 运行去做，还是先放着？\n'
              '打开 Today：co rem open',
        'en': 'Overnight: 1 reply sent for you, 1 more drafted for you to check; 1 task finished, 1 problem explained.\n'
              '2 decisions:\n'
              '· Reply to Mara Quill as you (when the Fernhill pilot starts) — send my draft?\n'
              '· Fernhill plan — spend one Codex run on it, or leave it?\n'
              'Open Today: co rem open'}


def at(monkeypatch, *args):
    """Pin the clock; arguments are UTC (Sydney is UTC+11 in November)."""
    monkeypatch.setattr(service, 'now', lambda: datetime(*args, tzinfo=timezone.utc))


def investigations(*rows):
    """The index exactly as rem/problems.py writes it (night-investigations 35b0a770b):
    `update()` stores each receipt under its problem key; `reserve()` builds the receipt
    from the detector's problem plus id/state/result/...; every `save()` sets `state`
    and bumps `updated_at`. There is no `items` list and no `explained_at`."""
    entries = {}
    for key, state, updated_at in rows:
        id = hashlib.sha256(key.encode()).hexdigest()[:16]
        entries[key] = {
            'key': key, 'detector': 'workflow_red', 'repo': 'fernhill/pilot', 'project': 'projects/pilot.md',
            'symptom': 'CI is red on main', 'facts': [], 'evidence_revision': 'fictional-revision',
            'priority': 50, 'waiting': [], 'aliases': [], 'workflow': 'ci', 'detected_at': '2026-11-07T20:00:00+11:00',
            'oldest_at': '2026-11-07T19:00:00+11:00', 'default_branch': 'main', 'head_sha': '',
            'local_checkout': None, 'clone_url': None,
            'id': id, 'state': state, 'result': 'completed', 'attempts': 1, 'reason': '',
            'opened_at': '2026-11-07T22:30:00+11:00', 'updated_at': updated_at,
            'last_checked': '2026-11-07T22:30:00+11:00', 'resolved_by': None,
            'receipt': f'/fictional/.state/investigations/{id}/receipt.json',
            'started_at': '2026-11-07T23:00:00+11:00', 'finished_at': updated_at, 'exit_code': 0}
    return entries


@pytest.fixture(autouse=True)
def _own_cwd(tmp_path, monkeypatch):
    # project_root() falls back to the working directory, and the suite-wide stray-project
    # guard rejects /private/tmp: these tests must not depend on where pytest started.
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def morning_book(tmp_path, monkeypatch):
    from connectonion.rem import morning
    prepare(tmp_path)
    set_config(tmp_path, ['schedule.timezone', 'Australia/Sydney', 'notify.channel', 'telegram',
                          'notify.target', 'fictional-owner', 'languages', 'zh'])
    at(monkeypatch, 2026, 11, 7, 19)  # 06:00 Sydney, 8 November
    monkeypatch.setattr(morning, 'today_link', lambda root: 'co rem open')
    monkeypatch.setattr(morning, 'actionable', lambda root: ROWS['zh' if morning._zh(root, read_config(root)) else 'en'])
    write_json(state_path(tmp_path, 'night.json'), {'date': '2026-11-07', 'items': {
        'one': {'outcome': {'kind': 'prepared', 'draft_id': 'draft-one', 'prepared_at': '2026-11-07T23:30:00+11:00'}},
        'two': {'outcome': {'kind': 'prepared', 'draft_id': 'draft-one', 'prepared_at': '2026-11-07T23:30:00+11:00'}},
        'sent': {'outcome': {'kind': 'prepared', 'draft_id': 'draft-sent', 'prepared_at': '2026-11-07T23:00:00+11:00'}},
        'old': {'outcome': {'kind': 'prepared', 'draft_id': 'old', 'prepared_at': '2026-11-06T23:30:00+11:00'}}}})
    write_json(state_path(tmp_path, 'drafts/draft-sent.json'), {
        'id': 'draft-sent', 'status': 'sent', 'prepared_at': '2026-11-07T23:00:00+11:00'})
    write_json(state_path(tmp_path, 'approvals.json'), {
        'one': {'kind': 'reply', 'by': 'rem', 'status': 'sent', 'release_at': '2026-11-08T02:00:00+11:00'},
        'two': {'kind': 'reply', 'by': 'owner', 'status': 'sent', 'release_at': '2026-11-08T02:00:00+11:00'},
        'hold': {'kind': 'reply', 'by': 'rem', 'status': 'held', 'release_at': '2026-11-08T06:05:00+11:00'}})
    write_json(state_path(tmp_path, 'tasks/do-fern/receipt.json'), {
        'started_at': '2026-11-08T01:00:00+11:00', 'finished_at': '2026-11-08T03:00:00+11:00', 'result': 'completed'})
    write_json(state_path(tmp_path, 'investigations/index.json'), investigations(
        ('workflow_red:fernhill/pilot:ci', 'explained', '2026-11-08T04:00:00+11:00')))
    return tmp_path


@pytest.mark.parametrize('language', ['zh', 'en'])
def test_full_night_message_is_the_pm_text(morning_book, language):
    from connectonion.rem import morning
    set_config(morning_book, ['languages', language])
    value = morning.preview(morning_book)
    assert value['message'] == FULL[language]
    assert value['counts'] == {'sent': 1, 'drafted': 1, 'finished': 1, 'explained': 1}
    assert 'draft-one' not in value['message']


def test_investigations_counted_from_the_writer_shape(morning_book):
    from connectonion.rem import morning
    write_json(state_path(morning_book, 'investigations/index.json'), investigations(
        ('a', 'explained', '2026-11-08T04:00:00+11:00'),
        ('b', 'needs_owner', '2026-11-08T01:00:00+11:00'),
        ('c', 'fix_proposed', '2026-11-07T23:00:00+11:00'),
        ('d', 'investigating', '2026-11-08T02:00:00+11:00'),
        ('e', 'inconclusive', '2026-11-08T02:00:00+11:00'),
        ('f', 'stale', '2026-11-08T02:00:00+11:00'),
        ('g', 'explained', '2026-11-07T12:00:00+11:00')))
    assert morning.preview(morning_book)['counts']['explained'] == 3


def test_outside_the_morning_window_is_missed_and_silent(morning_book, monkeypatch):
    from connectonion.rem import morning
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    at(monkeypatch, 2026, 11, 8, 6)  # 17:00 Sydney: schedule.times' own second slot
    assert morning.run(morning_book)['status'] == 'missed'
    assert morning.run(morning_book)['status'] == 'missed'
    assert read_json(state_path(morning_book, 'morning.json'), {})['2026-11-08']['status'] == 'missed'
    at(monkeypatch, 2026, 11, 8, 10)  # 21:00
    assert morning.run(morning_book)['status'] == 'missed'
    send.assert_not_called()


def test_window_runs_from_the_previous_check_to_now(morning_book, monkeypatch):
    from connectonion.rem import morning
    write_json(state_path(morning_book, 'morning.json'), {
        '2026-11-07': {'status': 'sent', 'channel': 'telegram', 'checked_at': '2026-11-07T06:30:00+11:00'}})
    write_json(state_path(morning_book, 'tasks/do-day/receipt.json'), {
        'finished_at': '2026-11-07T07:00:00+11:00', 'result': 'completed'})   # after yesterday's note
    write_json(state_path(morning_book, 'tasks/do-early/receipt.json'), {
        'finished_at': '2026-11-07T06:10:00+11:00', 'result': 'completed'})   # already reported
    write_json(state_path(morning_book, 'tasks/do-late/receipt.json'), {
        'finished_at': '2026-11-08T07:30:00+11:00', 'result': 'completed'})   # after 06:00, before this check
    at(monkeypatch, 2026, 11, 7, 21)  # 08:00 Sydney
    assert morning.preview(morning_book)['counts']['finished'] == 3


def test_a_missed_day_does_not_move_the_window(morning_book):
    from connectonion.rem import morning
    write_json(state_path(morning_book, 'morning.json'), {
        '2026-11-06': {'status': 'sent', 'channel': 'telegram', 'checked_at': '2026-11-06T06:30:00+11:00'},
        '2026-11-07': {'status': 'missed', 'channel': 'telegram', 'checked_at': '2026-11-07T17:00:00+11:00'}})
    write_json(state_path(morning_book, 'tasks/do-day/receipt.json'), {
        'finished_at': '2026-11-07T12:00:00+11:00', 'result': 'completed'})
    assert morning.preview(morning_book)['counts']['finished'] == 2


def test_a_preview_error_claims_nothing_and_the_next_tick_retries(morning_book, monkeypatch):
    from connectonion.rem import morning
    write_json(state_path(morning_book, 'investigations/index.json'), investigations(
        ('a', 'explained', 'not-a-date')))
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    assert morning.scheduled_check(morning_book)['status'] == 'unavailable'
    assert not state_path(morning_book, 'morning.json').exists()
    write_json(state_path(morning_book, 'investigations/index.json'), {})
    assert morning.scheduled_check(morning_book)['status'] == 'sent'
    send.assert_called_once()


def test_real_outcomes_lines_use_the_rows_words_never_an_address(morning_book, monkeypatch):
    from connectonion.rem import approvals, drafts, morning, today
    monkeypatch.setattr(morning, 'actionable', REAL_ACTIONABLE)
    set_config(morning_book, ['languages', 'en'])
    thread = {'thread': 'fictional-thread-1', 'provider': 'outlook'}
    monkeypatch.setattr(today, 'queue', lambda root: [
        {'key': 'k1', 'keys': ['k1'], 'title': 'Mara Quill', 'closed': False, 'quiet': False, 'dir': 'mine',
         'text': 'Mara asked', 'reply': {**thread, 'state': 'waiting'}}])
    monkeypatch.setattr(drafts, 'listing', lambda root: [
        {'id': 'a' * 32, 'version': 'v1', 'status': 'prepared', 'to': 'mara@fernhill.example', **thread,
         'subject': 'Re: Fernhill pilot', 'body': 'Hi Mara, it starts Monday.', 'gist': 'when the Fernhill pilot starts'},
        {'id': 'b' * 32, 'version': 'v1', 'status': 'prepared', 'to': 'ops@fernhill.example',
         'thread': 'fictional-thread-2', 'provider': 'outlook', 'subject': 'Re: Fernhill pilot',
         'body': 'Thanks, the dates are fixed.'}])
    assert [row['title'] for row in approvals.outcomes(morning_book)] == ['Mara Quill', 'ops@fernhill.example']
    lines = morning.preview(morning_book)['message'].splitlines()
    assert lines[2] == '· Reply to Mara Quill as you (when the Fernhill pilot starts) — send my draft?'
    assert lines[3] == '· Reply as you (Re: Fernhill pilot) — send my draft?'
    assert '@' not in '\n'.join(lines)


def test_zero_counts_and_empty_decisions_are_left_out(morning_book, monkeypatch):
    from connectonion.rem import morning
    for name in ('night.json', 'approvals.json', 'investigations/index.json', 'drafts/draft-sent.json'):
        state_path(morning_book, name).unlink()
    monkeypatch.setattr(morning, 'actionable', lambda root: [])
    assert morning.preview(morning_book)['message'] == '昨夜：跑完 1 项任务。\n打开 Today：co rem open'
    set_config(morning_book, ['languages', 'en'])
    assert morning.preview(morning_book)['message'] == 'Overnight: 1 task finished.\nOpen Today: co rem open'


def test_more_than_two_decisions_point_to_today(morning_book, monkeypatch):
    from connectonion.rem import morning
    extra = [{'id': f'task:{n}', 'kind': 'task', 'title': f'Fernhill {n}', 'text': ''} for n in range(3)]
    monkeypatch.setattr(morning, 'actionable', lambda root: ROWS['zh'] + extra)
    lines = morning.preview(morning_book)['message'].splitlines()
    assert lines[1] == '5 件要你拍板：' and lines[4] == '还有 3 件在 Today'
    assert len(lines) == 6


def test_dry_run_says_whether_it_would_really_send(morning_book, monkeypatch):
    from connectonion.rem import morning
    assert morning.run(morning_book, dry_run=True)['plan'] == 'would send now via telegram'
    at(monkeypatch, 2026, 11, 7, 18, 30)
    assert morning.run(morning_book, dry_run=True)['plan'] == 'not due until 06:00'
    at(monkeypatch, 2026, 11, 8, 1)
    assert morning.run(morning_book, dry_run=True)['plan'] == \
        'outside the morning window (06:00–11:00): nothing will be sent today'
    at(monkeypatch, 2026, 11, 7, 19, 2)
    monkeypatch.setattr(morning, 'send_message', Mock())
    morning.run(morning_book)
    assert morning.run(morning_book, dry_run=True)['plan'] == 'already sent 06:02'
    set_config(morning_book, ['notify.channel', 'none'])
    at(monkeypatch, 2026, 11, 8, 19)
    assert morning.run(morning_book, dry_run=True)['plan'] == 'channel none: nothing will be sent'


def test_dry_run_on_a_quiet_morning(tmp_path, monkeypatch):
    from connectonion.rem import morning
    prepare(tmp_path)
    set_config(tmp_path, ['schedule.timezone', 'UTC', 'notify.channel', 'telegram', 'notify.target', 'fictional-owner'])
    at(monkeypatch, 2026, 11, 8, 7)
    monkeypatch.setattr(morning, 'actionable', lambda root: [])
    monkeypatch.setattr(morning, 'today_link', lambda root: 'co rem open')
    value = morning.run(tmp_path, dry_run=True)
    assert (value['plan'], value['message']) == ('quiet: nothing to send', '')


def test_host_check_runs_before_the_write_lock(morning_book, monkeypatch):
    from connectonion.rem import morning
    held = []

    @contextmanager
    def lock(root, *args, **kwargs):
        held.append(True)
        yield
        held.pop()

    def link(root):
        assert not held, 'host_online must not run under the notebook write lock'
        return 'co rem open'
    monkeypatch.setattr(morning, 'maintenance_lock', lock)
    monkeypatch.setattr(morning, 'today_link', link)
    monkeypatch.setattr(morning, 'send_message', Mock())
    assert morning.run(morning_book)['status'] == 'sent'


def test_same_decisions_and_nothing_new_stays_quiet(morning_book, monkeypatch):
    from connectonion.rem import morning
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    morning.run(morning_book)
    at(monkeypatch, 2026, 11, 8, 19)  # next morning, no new receipts, same two decisions
    assert morning.preview(morning_book)['message'] == ''
    assert morning.run(morning_book)['status'] == 'quiet'
    monkeypatch.setattr(morning, 'actionable', lambda root: ROWS['zh'][:1])
    at(monkeypatch, 2026, 11, 9, 19)  # the set changed: one was settled
    assert morning.run(morning_book)['status'] == 'sent'
    assert send.call_count == 2


def test_doctor_reports_only_the_latest_and_the_file_is_pruned(morning_book, monkeypatch):
    from connectonion.rem import morning
    monkeypatch.setattr(morning, 'sender_status', lambda: [
        {'channel': 'telegram', 'configured': True, 'next': 'fictional'}])
    old = {f'2026-10-{day:02d}': {'status': 'failed', 'channel': 'telegram', 'checked_at': f'2026-10-{day:02d}T06:00:00+11:00'}
           for day in range(1, 31)}
    write_json(state_path(morning_book, 'morning.json'), old)
    delivery = [row for row in morning.doctor(morning_book) if row['check'] == 'morning delivery']
    assert [row['detail'] for row in delivery] == ['2026-10-30: failed; no automatic retry']
    monkeypatch.setattr(morning, 'send_message', Mock())
    morning.run(morning_book)
    saved = read_json(state_path(morning_book, 'morning.json'), {})
    assert min(saved) == '2026-10-25' and max(saved) == '2026-11-08'
    assert not [row for row in morning.doctor(morning_book) if row['check'] == 'morning delivery']


def test_help_is_the_same_on_every_machine(monkeypatch):
    from connectonion.rem import morning
    from connectonion.cli.commands.rem_help import page
    monkeypatch.setattr(morning, 'sender_status', Mock(side_effect=AssertionError('help read this machine')))
    text = page('co rem morning')
    assert 'on this machine' not in text and 'co rem doctor' in text


def test_send_once_and_dry_run_does_not_claim(morning_book, monkeypatch):
    from connectonion.rem import morning
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    expected = morning.preview(morning_book)
    assert morning.run(morning_book, dry_run=True)['message'] == expected['message']
    assert not state_path(morning_book, 'morning.json').exists()
    assert morning.run(morning_book)['status'] == 'sent'
    assert morning.run(morning_book)['status'] == 'sent'
    send.assert_called_once_with('telegram', 'fictional-owner', expected['message'], expected['html'], expected['subject'])


def test_failure_is_durable_and_never_retried(morning_book, monkeypatch):
    from connectonion.rem import morning
    send = Mock(side_effect=RuntimeError('fictional outage'))
    monkeypatch.setattr(morning, 'send_message', send)
    assert morning.run(morning_book)['status'] == 'failed'
    morning.run(morning_book)
    assert send.call_count == 1
    assert any(not row['ok'] and 'failed' in row['detail'] for row in morning.doctor(morning_book))


def test_empty_morning_checked_without_send(tmp_path, monkeypatch):
    from connectonion.rem import morning
    prepare(tmp_path)
    set_config(tmp_path, ['schedule.timezone', 'UTC'])
    at(monkeypatch, 2026, 11, 8, 7)
    monkeypatch.setattr(morning, 'actionable', lambda root: [])
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    assert morning.run(tmp_path)['status'] == 'quiet'
    assert read_json(state_path(tmp_path, 'morning.json'), {})
    send.assert_not_called()


def test_before_six_waits_and_missing_investigations_are_zero(morning_book, monkeypatch):
    from connectonion.rem import morning
    state_path(morning_book, 'investigations/index.json').unlink()
    assert morning.preview(morning_book)['counts']['explained'] == 0
    at(monkeypatch, 2026, 11, 7, 18, 59)
    assert morning.run(morning_book)['status'] == 'not_due'
    assert not state_path(morning_book, 'morning.json').exists()


def test_cli_preview_exact(morning_book):
    from connectonion.cli.main import app
    result = CliRunner().invoke(app, ['rem', '--root', str(morning_book), 'morning', '--dry-run'])
    assert result.exit_code == 0, result.output
    assert result.stdout == 'would send now via telegram\n' + FULL['zh'] + '\n'
    assert not state_path(morning_book, 'morning.json').exists()


def test_channel_validation(tmp_path):
    prepare(tmp_path)
    assert read_config(tmp_path)['notify']['channel'] == 'none'
    with pytest.raises(Exception, match='notify.channel'):
        set_config(tmp_path, ['notify.channel', 'carrier-pigeon'])


@pytest.mark.parametrize('channel', ['telegram', 'lark', 'whatsapp', 'email'])
def test_existing_transport_seams(channel, monkeypatch):
    from connectonion.rem import morning
    telegram = Mock(return_value={'success': True, 'message_id': 'fictional'})
    email = Mock(return_value={'success': True})
    chat = Mock()
    chat.send.return_value = "fictional-receipt"
    monkeypatch.setattr('connectonion.cli.commands.telegram_commands.send_telegram', telegram)
    import importlib
    monkeypatch.setattr(importlib.import_module('connectonion.useful_tools.send_email'), 'send_email', email)
    monkeypatch.setattr('connectonion.cli.commands.listen_commands._configured', lambda *a, **kw: chat)
    morning.send_message(channel, 'fictional-owner', 'Fernhill ready')
    if channel == 'telegram':
        telegram.assert_called_once_with('fictional-owner', 'Fernhill ready')
    elif channel == 'email':
        email.assert_called_once_with('fictional-owner', 'REM · Today', 'Fernhill ready')
    else:
        chat.send.assert_called_once()
        assert chat.send.call_args.args == ('fictional-owner', 'Fernhill ready')


def test_none_is_a_final_check(morning_book, monkeypatch):
    from connectonion.rem import morning
    set_config(morning_book, ['notify.channel', 'none'])
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    assert morning.run(morning_book)['status'] == 'disabled'
    set_config(morning_book, ['notify.channel', 'telegram'])
    assert morning.run(morning_book)['status'] == 'disabled'
    send.assert_not_called()


def test_new_local_date_gets_one_new_check(morning_book, monkeypatch):
    from connectonion.rem import morning
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    morning.run(morning_book)
    write_json(state_path(morning_book, 'tasks/do-next/receipt.json'), {
        'finished_at': '2026-11-09T03:00:00+11:00', 'result': 'completed'})
    at(monkeypatch, 2026, 11, 8, 19)
    morning.run(morning_book)
    assert send.call_count == 2
    assert len(read_json(state_path(morning_book, 'morning.json'), {})) == 2


def test_scheduled_next_checks_even_if_no_round_due(morning_book, monkeypatch):
    from connectonion.rem import morning, native
    call = Mock()
    monkeypatch.setattr(morning, 'scheduled_check', call)
    monkeypatch.setattr(native, 'pending', lambda root: [])
    monkeypatch.setattr(native, '_next_round', lambda *a, **kw: {'outcome': 'done', 'reason': 'not due'})
    assert native.next_task(morning_book, scheduled=True)['reason'] == 'not due'
    call.assert_called_once_with(morning_book)


def test_live_today_link_only_for_served_default_book(tmp_path, monkeypatch):
    from connectonion.rem import morning, reader
    monkeypatch.setattr('connectonion.project.project_identity', lambda: {'address': 'fictional-address'})
    monkeypatch.setattr(reader, 'host_online', lambda address: True)
    assert morning.today_link(tmp_path) == 'co rem open'
    from pathlib import Path
    root = Path.home() / '.co/rem'
    assert morning.today_link(root) == 'https://chat.openonion.ai/fictional-address/rem'
    monkeypatch.setattr(reader, 'host_online', lambda address: False)
    assert morning.today_link(root) == 'co rem open'


def test_busy_notification_does_not_block_round(morning_book, monkeypatch):
    from connectonion.rem import morning, native
    from connectonion.rem.files import RemError
    monkeypatch.setattr(morning, 'run', Mock(side_effect=RemError('Fictional busy notebook')))
    monkeypatch.setattr(native, 'pending', lambda root: [])
    monkeypatch.setattr(native, '_next_round', lambda *a, **kw: {'outcome': 'done', 'reason': 'round reached'})
    assert native.next_task(morning_book, scheduled=True)['reason'] == 'round reached'


def test_a_sent_draft_is_counted_once_as_sent(morning_book):
    from connectonion.rem import morning
    write_json(state_path(morning_book, 'night.json'), {'items': {}})
    write_json(state_path(morning_book, 'drafts/fern.json'), {
        'id': 'fern', 'status': 'prepared', 'prepared_at': '2026-11-07T23:00:00+11:00'})
    counts = morning.preview(morning_book)['counts']
    assert (counts['sent'], counts['drafted']) == (1, 1)


def test_english_plurals(morning_book):
    from connectonion.rem import morning
    set_config(morning_book, ['languages', 'en'])
    write_json(state_path(morning_book, 'tasks/do-two/receipt.json'), {
        'finished_at': '2026-11-08T04:00:00+11:00', 'result': 'completed'})
    message = morning.preview(morning_book)['message']
    assert '2 tasks finished' in message and '1 problem explained' in message


def test_doctor_flags_unconfigured_selected_sender(morning_book, monkeypatch):
    from connectonion.rem import morning
    monkeypatch.setattr(morning, 'sender_status', lambda: [
        {'channel': 'telegram', 'configured': False, 'next': 'co telegram check'}])
    rows = morning.doctor(morning_book)
    assert any(not row['ok'] and 'telegram' in row['detail'] for row in rows)


# ---------- the morning mail ----------
LIVE = 'https://chat.openonion.ai/fictional-address/rem'


def visible(html):
    import re
    return re.sub(r'\s+', ' ', re.sub(r'<style.*?</style>|<[^>]+>', ' ', html, flags=re.S))


def mail_book(book):
    """One fictional night of every kind REM reports, with the people's own names."""
    write_json(state_path(book, 'approvals.json'), {
        'avery': {'kind': 'reply', 'by': 'rem', 'status': 'sent', 'title': 'Avery Stone', 'subject': 'Re: Fernhill invoice',
                  'release_at': '2026-11-08T02:00:00+11:00', 'keys': ['people/avery-stone.md\nAvery asked']},
        'fern': {'kind': 'reply', 'by': 'rem', 'status': 'held', 'title': 'Fern Ivers', 'subject': 'Re: Lab keys',
                 'release_at': '2026-11-08T06:05:00+11:00', 'keys': ['people/fern-ivers.md\nFern asked']}})
    write_json(state_path(book, 'drafts/draft-mara.json'), {
        'id': 'draft-mara', 'version': 'outlook:mara-1', 'status': 'prepared', 'to': 'mara@fernhill.example',
        'subject': 'Re: Fernhill pilot dates', 'gist': 'Tell Mara the pilot starts Monday',
        'prepared_at': '2026-11-07T23:10:00+11:00'})
    write_json(state_path(book, 'night.json'), {'items': {'mara': {'outcome': {
        'kind': 'prepared', 'title': 'Mara Quill', 'draft_id': 'draft-mara', 'source': 'outlook:mara-1', 'prepared_at': '2026-11-07T23:10:00+11:00'}}}})
    write_json(state_path(book, 'tasks/do-fern/receipt.json'), {
        'finished_at': '2026-11-08T03:00:00+11:00', 'result': 'completed', 'title': 'Fernhill Labs',
        'text': 'Write up the pilot plan', 'record': 'orgs/fernhill-labs.md',
        'deliverable': '/fictional/.state/tasks/do-fern/result.md'})
    return book


def test_mail_tells_what_rem_did_then_the_decisions(morning_book, monkeypatch):
    from connectonion.rem import morning
    monkeypatch.setattr(morning, 'today_link', lambda root: LIVE)
    value = morning.preview(mail_book(morning_book))
    text = visible(value['html'])
    assert value['subject'] == 'REM 早报 · 昨夜 REM 替你做了 5 件事，2 件要你拍板'
    assert text.index('昨夜 REM 替你做了 5 件事') < text.index('2 件要你拍板，在下面') < text.index('Fern Ivers')
    for words in ('Fern Ivers', '06:05 前可撤回', 'Avery Stone', 'Fernhill invoice', '02:00 发出', 'Mara Quill',
                  'Fernhill pilot dates', 'Tell Mara the pilot starts Monday', 'Fernhill Labs', '打开看结果',
                  'CI is red on main', '已查清', '看稿并发送', '打开 Today'):
        assert words in text, words
    assert text.index('Fernhill Labs') < text.index('看稿并发送')  # done first, decisions after
    assert '@' not in text and '/fictional' not in text and 'draft-mara' not in text and 'Re:' not in text
    assert f'{LIVE}#r=orgs/fernhill-labs.md' in value['html']
    assert value['html'].count('#22d27a;border') == 1  # one primary action


def test_mail_without_a_live_reader_has_no_dead_buttons(morning_book):
    from connectonion.rem import morning
    html = morning.preview(mail_book(morning_book))['html']
    assert 'href="co rem open"' not in html and '看稿并发送' not in html
    assert 'Today 现在打不开' in visible(html)


def test_quiet_morning_has_no_mail(tmp_path, monkeypatch):
    from connectonion.rem import morning
    prepare(tmp_path)
    set_config(tmp_path, ['schedule.timezone', 'UTC', 'notify.channel', 'outlook'])
    at(monkeypatch, 2026, 11, 8, 7)
    monkeypatch.setattr(morning, 'actionable', lambda root: [])
    value = morning.preview(tmp_path)
    assert (value['message'], value['html'], value['subject']) == ('', '', '')


def test_language_is_the_owners_detected_one_not_config_language(morning_book):
    from connectonion.rem import morning
    set_config(morning_book, ['languages', '', 'language', 'en'])
    write_json(state_path(morning_book, 'map.json'), {'owner': {'languages': {
        'languages': ['zh', 'en'], 'shares': {'zh': 0.75, 'en': 0.25}, 'english_terms': []}}})
    assert morning.preview(morning_book)['message'].startswith('昨夜：')
    write_json(state_path(morning_book, 'map.json'), {'owner': {'languages': {
        'languages': ['en', 'zh'], 'shares': {'en': 0.6, 'zh': 0.4}, 'english_terms': []}}})
    value = morning.preview(morning_book)
    assert value['message'].startswith('Overnight: ') and value['subject'].startswith('REM morning · ')


def outlook_mailbox(monkeypatch, own='mara@fernhill.example'):
    box = Mock()
    box.my_addresses.return_value = {own}
    monkeypatch.setattr('connectonion.useful_tools.outlook.Outlook', lambda: box)
    return box


def test_outlook_sends_from_and_to_the_linked_mailbox(monkeypatch):
    from connectonion.rem import morning
    box = outlook_mailbox(monkeypatch)
    morning.send_message('outlook', '', 'Fernhill ready', '<p>Fernhill ready</p>', 'REM 早报')
    box.send.assert_called_once_with('mara@fernhill.example', 'REM 早报', 'Fernhill ready', html='<p>Fernhill ready</p>')


def test_outlook_refuses_any_other_recipient(monkeypatch):
    from connectonion.rem import morning
    from connectonion.rem.files import RemError
    box = outlook_mailbox(monkeypatch)
    with pytest.raises(RemError, match='linked Outlook mailbox'):
        morning.send_message('outlook', 'team@fernhill.example', 'Fernhill ready', '<p>x</p>', 'REM')
    box.send.assert_not_called()


def test_outlook_run_sends_the_designed_mail(morning_book, monkeypatch):
    from connectonion.rem import morning
    set_config(morning_book, ['notify.channel', 'outlook', 'notify.target', ''])
    box = outlook_mailbox(monkeypatch)
    assert morning.run(morning_book)['status'] == 'sent'
    to, subject, body = box.send.call_args.args
    assert (to, body) == ('mara@fernhill.example', FULL['zh'])
    assert subject.startswith('REM 早报') and box.send.call_args.kwargs['html'].startswith('<!DOCTYPE html>')


def test_cli_dry_run_writes_the_mail_and_prints_its_path(morning_book, monkeypatch, tmp_path):
    import tempfile
    from connectonion.cli.main import app
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    set_config(morning_book, ['notify.channel', 'outlook', 'notify.target', ''])
    result = CliRunner().invoke(app, ['rem', '--root', str(morning_book), 'morning', '--dry-run'])
    assert result.exit_code == 0, result.output
    line = result.stdout.splitlines()[-1]
    path = tmp_path / 'rem-morning-2026-11-08.html'
    assert line == f'Mail preview: {path}' and path.read_text().startswith('<!DOCTYPE html>')
    assert not state_path(morning_book, 'morning.json').exists()


def test_outlook_is_a_valid_channel(tmp_path):
    prepare(tmp_path)
    set_config(tmp_path, ['notify.channel', 'outlook'])
    assert read_config(tmp_path)['notify']['channel'] == 'outlook'
