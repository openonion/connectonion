"""History reconciliation must preserve its checkpoint through partial failures."""
import json
from types import SimpleNamespace
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
            return {'items': [history('root') | {'thread_id': 'omt_thread'}], 'has_more': False}
        return {'items': [history('reply') | {'thread_id': 'omt_thread'},
                          history('old-reply') | {'create_time': '1000'}], 'has_more': False}
    monkeypatch.setattr(bot, '_get', get)
    recovery.reconcile(until=210)
    assert box.lookup('reply').thread == 'omt_thread'
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


def test_a_missing_scope_is_logged_once_and_not_retried(tmp_path, monkeypatch):
    """#2084: an app without im:message.group_msg got 230027 and logged it
    every 60 s for 3.5 days (5,404 lines). Only an admin can grant a scope,
    so the worker says so once and stops; live messages still arrive."""
    import connectonion.inbox.feishu as feishu
    bot, box, recovery = setup(tmp_path)

    class Denied:
        status_code = 400
        def json(self):
            return {'code': 230027, 'msg': 'Lack of necessary permissions, ext=need scope: im:message.group_msg'}

    monkeypatch.setattr(bot, '_get', lambda path: feishu._data(Denied(), bot.brand))
    recovery.start()
    recovery.worker.join(2)

    assert not recovery.worker.is_alive()
    lines = box.logfile.read_text().splitlines()
    assert len([line for line in lines if '230027' in line]) == 1
    assert 'im:message.group_msg' in lines[-1] and 'restart' in lines[-1]
    assert 'im:message.group_msg' in (box.root / 'recovery-error.txt').read_text()
    recovery.stop()


def test_remembered_chat_recovers_after_interrupted_first_journal_write(tmp_path,monkeypatch):
    bot=Feishu('lark');bot._bot_open_id='bot'
    box=Inbox('lark',home=tmp_path)
    recovery=HistoryRecovery(bot,box,started_at=100)
    # Listener saves this before durable deliver. A crash can leave no journal.
    recovery.note_chat('chat','p2p')
    resumed=HistoryRecovery(bot,box,started_at=999)
    monkeypatch.setattr(bot,'_get',lambda path:{'items':[history('gap')], 'has_more':False})
    assert resumed.reconcile(until=210)==1
    assert box.lookup('gap').mentioned is True


def test_recovered_file_preserves_normalized_resources_and_original_sender_id(tmp_path,monkeypatch):
    bot,box,recovery=setup(tmp_path)
    row=history('archive') | {'msg_type':'file','body':{'content':json.dumps({
        'file_key':'file_zip','file_name':'8月发票.zip'})}}
    monkeypatch.setattr(bot,'_get',lambda path:{'items':[row], 'has_more':False})
    recovery.reconcile(until=210)
    got=box.lookup('archive')
    assert got.kind=='file'
    assert got.sender_ids=={'open_id':'user'}
    assert got.attachments==[{'type':'file','key':'file_zip','name':'8月发票.zip'}]


def test_new_empty_inbox_still_does_not_discover_any_conversations(tmp_path,monkeypatch):
    bot=Feishu('lark');box=Inbox('lark',home=tmp_path)
    recovery=HistoryRecovery(bot,box,started_at=100)
    monkeypatch.setattr(bot,'_get',lambda path:pytest.fail('unknown conversation discovery'))
    assert recovery.reconcile(until=210)==0
    assert json.loads(recovery.state.read_text())['through']==210


# ---- #2690: recovery that can actually finish, and finishes cheaply ----------

def rejected(code=230001):
    import connectonion.inbox.feishu as feishu

    class Rejected:
        status_code = 400
        def json(self):
            return {'code': code, 'msg': 'The request you send is not a valid {container_id}. ext=invalid container_id..'}
    return feishu._data(Rejected(), 'Lark')


def test_a_reply_root_id_is_never_queried_as_a_thread_container(tmp_path, monkeypatch):
    """A group reply carries root_id (om_…), not a thread id (omt_…). Querying
    it as container_id_type=thread got 230001 every run, forever (#2690)."""
    bot, box, recovery = setup(tmp_path)
    reply = SimpleNamespace(event=SimpleNamespace(
        message=SimpleNamespace(message_id='om_reply', chat_id='chat', chat_type='group',
                                message_type='text', content='{"text":"hi"}', create_time=150000,
                                thread_id=None, root_id='om_root', mentions=[]),
        sender=SimpleNamespace(sender_type='user', sender_id=SimpleNamespace(open_id='ou_1'))))
    box.deliver(bot.to_message(reply))
    calls = []
    monkeypatch.setattr(bot, '_get', lambda path: calls.append(parse_qs(urlsplit(path).query))
                        or {'items': [], 'has_more': False})
    recovery.reconcile(until=210)
    assert [q['container_id'] for q in calls if q['container_id_type'] == ['thread']] == []


def test_one_rejected_container_is_skipped_and_the_others_still_recover(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    box.deliver(Message('seed-bad', 'oc_bad', 'user', 'seed', '1970-01-01T00:01:40Z'))
    def get(path):
        if parse_qs(urlsplit(path).query)['container_id'] == ['oc_bad']:
            return rejected()
        return {'items': [history('gap')], 'has_more': False}
    monkeypatch.setattr(bot, '_get', get)
    assert recovery.reconcile(until=210) == 1
    assert box.lookup('gap') is not None
    assert json.loads(recovery.state.read_text())['through'] == 210
    skipped = [line for line in box.logfile.read_text().splitlines() if 'oc_bad' in line]
    assert len(skipped) == 1 and '230001' in skipped[0]


def test_a_failed_run_is_not_retried_on_a_timer(tmp_path, monkeypatch):
    """23k identical lines came from a 60-second retry loop. A run that fails
    waits for the next reconnect or restart; Lark API calls are a quota."""
    import threading
    bot, box, recovery = setup(tmp_path)
    calls = []
    monkeypatch.setattr(bot, '_get', lambda path: calls.append(path) or (_ for _ in ()).throw(RuntimeError('network down')))
    attempted = threading.Event()
    original = recovery.reconcile
    def reconcile():
        try: return original(until=210)
        finally: attempted.set()
    monkeypatch.setattr(recovery, 'reconcile', reconcile)
    recovery.start()
    assert attempted.wait(2)
    recovery.stop()
    log = box.logfile.read_text()
    assert 'retrying in 60' not in log
    assert 'next reconnect' in log
    assert len(calls) == 1


def test_one_run_makes_a_bounded_number_of_api_calls(tmp_path, monkeypatch):
    from connectonion.inbox import recovery as recovery_module
    bot, box, recovery = setup(tmp_path)
    for n in range(60):
        box.deliver(Message(f'seed-{n}', f'oc_{n}', 'user', 'seed', '1970-01-01T00:01:40Z'))
    calls = []
    def get(path):
        calls.append(path)
        return {'items': [history(f'm{len(calls)}', mentions=[])], 'has_more': len(calls) < 10_000,
                'page_token': f't{len(calls)}'}
    monkeypatch.setattr(bot, '_get', get)
    recovery.reconcile(until=210)
    assert len(calls) <= 100, f'{len(calls)} calls in one run'
    assert len(calls) <= recovery_module.CALL_BUDGET
    assert json.loads(recovery.state.read_text())['through'] == 210


def test_an_addressed_message_missed_while_connected_names_the_other_client(tmp_path, monkeypatch):
    """Lark sends each event to one long connection per app. A DM the bot got
    while this listener was connected, that only history knows, was taken by
    another client; say so loudly and keep it where `check` reads it."""
    bot, box, recovery = setup(tmp_path)
    recovery.live_from = 150
    monkeypatch.setattr(bot, '_get', lambda path: {'items': [history('taken')], 'has_more': False})
    recovery.reconcile(until=210)
    warning = 'message taken reached the bot but not this listener — another client may be connected with this app_id'
    assert warning in box.logfile.read_text()
    assert warning in (box.root / 'missed-live.txt').read_text()


def test_a_message_sent_while_disconnected_is_recovered_without_the_split_warning(tmp_path, monkeypatch):
    bot, box, recovery = setup(tmp_path)
    recovery.live_from = 150
    recovery.disconnected(at=190)
    recovery.connected(at=205)
    monkeypatch.setattr(bot, '_get', lambda path: {'items': [history('gap')], 'has_more': False})
    recovery.reconcile(until=210)
    assert box.lookup('gap') is not None
    assert 'another client' not in box.logfile.read_text()
    assert not (box.root / 'missed-live.txt').exists()
