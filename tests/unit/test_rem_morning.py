"""Fictional overnight work; no real transport or model is used."""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from connectonion.rem import service
from connectonion.rem.config import prepare, set_config, read_config
from connectonion.rem.files import read_json, state_path, write_json


@pytest.fixture
def morning_book(tmp_path, monkeypatch):
    from connectonion.rem import morning
    prepare(tmp_path)
    set_config(tmp_path, ['schedule.timezone', 'Australia/Sydney', 'notify.channel', 'telegram',
                          'notify.target', 'fictional-owner'])
    monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, 7, 19, tzinfo=timezone.utc))
    monkeypatch.setattr(morning, 'today_link', lambda root: 'co rem open')
    monkeypatch.setattr(morning, 'actionable', lambda root: [
        {'title': 'Mara Quill', 'text': 'Review Fernhill pilot'},
        {'title': 'Fernhill', 'text': 'Approve the plan'}])
    write_json(state_path(tmp_path, 'night.json'), {'date': '2026-11-07', 'items': {
        'one': {'outcome': {'kind': 'prepared', 'draft_id': 'draft-one', 'prepared_at': '2026-11-07T23:30:00+11:00'}},
        'two': {'outcome': {'kind': 'prepared', 'draft_id': 'draft-one', 'prepared_at': '2026-11-07T23:30:00+11:00'}},
        'old': {'outcome': {'kind': 'prepared', 'draft_id': 'old', 'prepared_at': '2026-11-06T23:30:00+11:00'}}}})
    write_json(state_path(tmp_path, 'approvals.json'), {
        'one': {'kind': 'reply', 'by': 'rem', 'status': 'sent', 'release_at': '2026-11-08T02:00:00+11:00'},
        'two': {'kind': 'reply', 'by': 'owner', 'status': 'sent', 'release_at': '2026-11-08T02:00:00+11:00'},
        'hold': {'kind': 'reply', 'by': 'rem', 'status': 'held', 'release_at': '2026-11-08T06:05:00+11:00'}})
    write_json(state_path(tmp_path, 'tasks/do-fern/receipt.json'), {
        'started_at': '2026-11-08T01:00:00+11:00', 'finished_at': '2026-11-08T03:00:00+11:00', 'result': 'completed'})
    write_json(state_path(tmp_path, 'investigations/index.json'), {'items': [
        {'status': 'explained', 'explained_at': '2026-11-08T04:00:00+11:00'}]})
    return tmp_path


@pytest.mark.parametrize('language', ['zh', 'en'])
def test_counts_and_plain_names(morning_book, language):
    from connectonion.rem import morning
    set_config(morning_book, ['language', language])
    value = morning.preview(morning_book)
    assert value['counts'] == {'drafts': 1, 'sent': 1, 'dispatched': 1, 'finished': 1, 'investigations': 1}
    assert value['pending'] == 2
    assert len(value['message'].splitlines()) <= 5
    assert 'Mara Quill' in value['message'] and 'Fernhill' in value['message']
    assert '2 件等你点一下' in value['message'] if language == 'zh' else '2 need one click' in value['message']
    assert value['message'].endswith('co rem open')
    assert 'draft-one' not in value['message']


def test_send_once_and_dry_run_does_not_claim(morning_book, monkeypatch):
    from connectonion.rem import morning
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    expected = morning.preview(morning_book)['message']
    assert morning.run(morning_book, dry_run=True)['message'] == expected
    assert not state_path(morning_book, 'morning.json').exists()
    assert morning.run(morning_book)['status'] == 'sent'
    assert morning.run(morning_book)['status'] == 'sent'
    send.assert_called_once_with('telegram', 'fictional-owner', expected)


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
    monkeypatch.setattr(morning, 'actionable', lambda root: [])
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    assert morning.run(tmp_path)['status'] == 'quiet'
    assert read_json(state_path(tmp_path, 'morning.json'), {})
    send.assert_not_called()


def test_before_six_waits_and_missing_investigations_are_zero(morning_book, monkeypatch):
    from connectonion.rem import morning
    state_path(morning_book, 'investigations/index.json').unlink()
    assert morning.preview(morning_book)['counts']['investigations'] == 0
    monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, 7, 18, 59, tzinfo=timezone.utc))
    assert morning.run(morning_book)['status'] == 'not_due'
    assert not state_path(morning_book, 'morning.json').exists()


def test_cli_preview_exact(morning_book):
    from connectonion.rem import morning
    from connectonion.cli.main import app
    result = CliRunner().invoke(app, ['rem', '--root', str(morning_book), 'morning', '--dry-run'])
    assert result.exit_code == 0, result.output
    assert result.stdout == 'Channel: telegram\n' + morning.preview(morning_book)['message'] + '\n'


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
    monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, 8, 19, tzinfo=timezone.utc))
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


def test_malformed_optional_index_records_failure_without_blocking(morning_book, monkeypatch):
    from connectonion.rem import morning
    write_json(state_path(morning_book, 'investigations/index.json'), {'items': [
        {'status': 'explained', 'explained_at': 'not-a-date'}]})
    send = Mock()
    monkeypatch.setattr(morning, 'send_message', send)
    assert morning.scheduled_check(morning_book)['status'] == 'failed'
    assert morning.run(morning_book)['status'] == 'failed'
    send.assert_not_called()


def test_busy_notification_does_not_block_round(morning_book, monkeypatch):
    from connectonion.rem import morning, native
    from connectonion.rem.files import RemError
    monkeypatch.setattr(morning, 'run', Mock(side_effect=RemError('Fictional busy notebook')))
    monkeypatch.setattr(native, 'pending', lambda root: [])
    monkeypatch.setattr(native, '_next_round', lambda *a, **kw: {'outcome': 'done', 'reason': 'round reached'})
    assert native.next_task(morning_book, scheduled=True)['reason'] == 'round reached'


def test_sent_draft_is_still_counted_as_prepared(morning_book):
    from connectonion.rem import morning
    write_json(state_path(morning_book, 'night.json'), {'items': {}})
    write_json(state_path(morning_book, 'drafts/fern.json'), {
        'id': 'fern', 'status': 'sent', 'prepared_at': '2026-11-07T23:00:00+11:00'})
    assert morning.preview(morning_book)['counts']['drafts'] == 1


def test_late_check_excludes_daytime_work(morning_book, monkeypatch):
    from connectonion.rem import morning
    monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, 8, 5, tzinfo=timezone.utc))
    write_json(state_path(morning_book, 'investigations/index.json'), {'items': [
        {'status': 'explained', 'explained_at': '2026-11-08T10:00:00+11:00'}]})
    assert morning.preview(morning_book)['counts']['investigations'] == 0


def test_english_singular_counts(morning_book):
    from connectonion.rem import morning
    message = morning.preview(morning_book)['message']
    assert '1 draft prepared' in message and '1 reply sent' in message
    assert '1 task dispatched' in message and '1 investigation explained' in message


def test_doctor_flags_unconfigured_selected_sender(morning_book, monkeypatch):
    from connectonion.rem import morning
    monkeypatch.setattr(morning, 'sender_status', lambda: [
        {'channel': 'telegram', 'configured': False, 'next': 'co telegram check'}])
    rows = morning.doctor(morning_book)
    assert any(not row['ok'] and 'telegram' in row['detail'] for row in rows)
