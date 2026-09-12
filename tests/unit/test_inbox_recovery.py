"""History reconciliation must preserve its checkpoint through partial failures."""
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from connectonion.inbox.store import Inbox, Message
from connectonion.inbox.feishu import Feishu
from connectonion.inbox.recovery import HistoryRecovery


def history(identifier, *, sender_type='user', mentions=None):
    return {'message_id': identifier, 'chat_id': 'chat', 'msg_type': 'text',
            'create_time': '200000', 'body': {'content': '{"text":"@_user_1 hello"}'},
            'sender': {'sender_type': sender_type, 'id': 'user', 'id_type': 'open_id'},
            'mentions': mentions if mentions is not None else [{'key': '@_user_1', 'id': 'bot', 'name': 'One'}], 'deleted': False}


def setup(tmp_path):
    box = Inbox('lark', home=tmp_path)
    box.deliver(Message('seed', 'chat', 'user', 'seed', '1970-01-01T00:01:40Z'))
    bot = Feishu('lark')
    bot._bot_open_id = 'bot'
    recovery = HistoryRecovery(bot, box, started_at=100)
    return bot, box, recovery


def test_recovery_paginates_dedupes_and_keeps_completion(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    rows = [history('gap', mentions=[{'key': '@_user_1', 'id': 'bot', 'name': 'One'}]), history('bot', sender_type='app')]
    calls = []
    def get(path):
        query = parse_qs(urlsplit(path).query); calls.append(query)
        if 'page_token' not in query:
            return {'items': rows, 'has_more': True, 'page_token': 'next'}
        return {'items': [history('gap')], 'has_more': False}
    monkeypatch.setattr(bot, '_get', get)
    recovery.reconcile(until=210)
    gap = box.lookup('gap')
    assert gap.mentioned is True and gap.text == '@One hello'
    assert box.lookup('bot') is None
    assert len(calls) == 2 and calls[1]['page_token'] == ['next']
    box.done('gap')
    recovery.reconcile(until=220)
    assert not any('gap' in p.name for p in box.unread())
    assert json.loads(recovery.state.read_text())['through'] == 220


def test_partial_failure_keeps_checkpoint_across_restart(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    def get(path):
        if 'page_token' in path: raise RuntimeError('permission or transient failure')
        return {'items': [history('first')], 'has_more': True, 'page_token': 'next'}
    monkeypatch.setattr(bot, '_get', get)
    with pytest.raises(RuntimeError): recovery.reconcile(until=210)
    assert json.loads(recovery.state.read_text())['through'] == 100
    resumed = HistoryRecovery(bot, box, started_at=999)
    seen = []
    monkeypatch.setattr(bot, '_get', lambda path: seen.append(path) or {'items': [history('first'), history('second')], 'has_more': False})
    resumed.reconcile(until=220)
    assert parse_qs(urlsplit(seen[0]).query)['start_time'] == ['98']
    assert len(box.unread()) == 3


def test_invalid_pagination_and_malformed_records_do_not_advance(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    monkeypatch.setattr(bot, '_get', lambda path: {'items': [], 'has_more': True})
    with pytest.raises(ValueError, match='pagination'): recovery.reconcile(until=200)
    monkeypatch.setattr(bot, '_get', lambda path: {'items': [{'sender': {'sender_type': 'user'}}], 'has_more': False})
    with pytest.raises(ValueError): recovery.reconcile(until=200)
    assert json.loads(recovery.state.read_text())['through'] == 100


def test_first_start_does_not_import_old_history_and_never_discovers_other_chats(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    calls = []
    monkeypatch.setattr(bot, '_get', lambda path: calls.append(path) or {'items': [history('old') | {'create_time': '99000'}], 'has_more': False})
    recovery.reconcile(until=210)
    assert box.lookup('old') is None
    assert all(parse_qs(urlsplit(path).query)['container_id'] == ['chat'] for path in calls)


def test_direct_message_addressing_survives_listener_restart(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    recovery.note_chat('chat', 'p2p')
    resumed = HistoryRecovery(bot, box, started_at=999)
    monkeypatch.setattr(bot, '_get', lambda path: {'items': [history('dm')], 'has_more': False})
    resumed.reconcile(until=210)
    assert box.lookup('dm').mentioned is True


def test_thread_history_is_expanded_but_old_replies_are_not_imported(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    calls = []
    def get(path):
        query = parse_qs(urlsplit(path).query); calls.append(query)
        if query['container_id_type'] == ['chat']:
            return {'items': [history('root') | {'thread_id': 'thread'}], 'has_more': False}
        return {'items': [history('reply') | {'thread_id': 'thread'},
                          history('old-reply') | {'create_time': '1000'}], 'has_more': False}
    monkeypatch.setattr(bot, '_get', get)
    recovery.reconcile(until=210)
    assert box.lookup('reply').thread == 'thread'
    assert box.lookup('old-reply') is None
    assert len(calls) == 2 and 'start_time' not in calls[1]


def test_corrupt_checkpoint_fails_instead_of_resetting_past_missing_messages(tmp_path):
    bot, box, recovery = setup(tmp_path)
    recovery.state.write_text('{broken')
    with pytest.raises(ValueError): HistoryRecovery(bot, box, started_at=999)


def test_unrelated_group_history_never_becomes_agent_work(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    monkeypatch.setattr(bot, '_get', lambda path: {'items': [history('unrelated', mentions=[])], 'has_more': False})
    recovery.reconcile(until=210)
    assert box.lookup('unrelated') is None


def test_worker_exposes_failure_and_success_clears_it(tmp_path, monkeypatch):
    import threading
    bot, box, recovery = setup(tmp_path)
    monkeypatch.setattr(bot, '_get', lambda path: (_ for _ in ()).throw(RuntimeError('history denied')))
    attempted = threading.Event()
    original = recovery.reconcile
    def reconcile():
        try: return original(until=210)
        finally: attempted.set()
    monkeypatch.setattr(recovery, 'reconcile', reconcile)
    recovery.start()
    assert attempted.wait(2)
    recovery.stop()
    assert (box.root / 'recovery-error.txt').read_text() == 'history denied'
    assert json.loads(recovery.state.read_text())['through'] == 100
    resumed = HistoryRecovery(bot, box)
    monkeypatch.setattr(bot, '_get', lambda path: {'items': [], 'has_more': False})
    resumed.reconcile(until=220)
    assert not (box.root / 'recovery-error.txt').exists()


def test_stopping_idle_worker_does_not_start_another_reconciliation(tmp_path, monkeypatch):
    import threading
    bot, box, recovery = setup(tmp_path)
    finished = threading.Event()
    calls = []
    monkeypatch.setattr(recovery, 'reconcile', lambda: (calls.append(1), finished.set()))
    recovery.start()
    assert finished.wait(2)
    recovery.stop()
    assert calls == [1]
    assert not recovery.worker.is_alive()
    assert not (box.root / 'recovery-error.txt').exists()


def test_unknown_bot_identity_cannot_admit_mentions_of_someone_else(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    bot._bot_open_id = None
    monkeypatch.setattr(bot, 'bot_info', lambda: {})
    monkeypatch.setattr(bot, '_get', lambda path: pytest.fail('history must not be read without bot identity'))
    with pytest.raises(ValueError, match='bot identity'):
        recovery.reconcile(until=210)
    assert json.loads(recovery.state.read_text())['through'] == 100
