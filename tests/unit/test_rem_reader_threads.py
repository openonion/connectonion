"""Notebook-owned completion, recoverable skips and offline reader reconciliation."""
import json
import re

import pytest

from connectonion.rem import drafts, daily, native_round, reader
from connectonion.rem.config import read_config
from connectonion.rem.files import read_json, state_path
from tests.unit.test_rem_proactive import notebook, mail_thread  # noqa: F401
from tests.unit.test_rem_reader import _run_reader_js


def thread_key(root):
    from connectonion.rem import threads
    return threads.done_key('people/fern.md', 'You owe Fern a pilot review. [1]')


@pytest.mark.parametrize('state', ['done', 'skipped'])
def test_thread_persists_across_readers_and_undo_restores_queue(notebook, state):
    from connectonion.rem import threads
    mail_thread(notebook)
    key = thread_key(notebook)
    threads.set_state(notebook, key, state)
    saved = read_json(state_path(notebook, 'threads.json'), {})[key]
    assert saved['state'] == state and saved['at'] and saved['device']
    assert reader.snapshot(notebook, local=True)['threads'][key] == saved
    assert reader.snapshot(notebook)['threads'] == {}, 'shared snapshots must not leak private done keys'
    assert not drafts.queue(notebook)
    threads.set_state(notebook, key, 'open')
    assert key not in read_json(state_path(notebook, 'threads.json'), {})
    assert len(drafts.queue(notebook)) == 1


def test_skip_preserves_body_and_new_mail_returns_with_date(notebook):
    from connectonion.rem import threads
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'Review it today.', 'sources': ['gmail:one']})
    drafts.discard(notebook, row['id'])
    key = thread_key(notebook)
    assert threads.listing(notebook)[key]['draft_id'] == row['id']
    assert drafts._current(notebook, row['id'])['status'] == 'skipped'
    assert not drafts.queue(notebook)
    threads.set_state(notebook, key, 'open')
    assert drafts.listing(notebook)[0]['body'] == 'Review it today.'
    assert drafts.listing(notebook)[0]['status'] == 'prepared'
    drafts.discard(notebook, row['id'])
    mail_thread(notebook, latest='two')
    assert drafts.queue(notebook)[0]['version'] == 'gmail:two'
    returned = threads.listing(notebook)[key]
    assert returned['returned_at'] == '2026-11-07T02:00:00+00:00'
    assert not threads.blocked(notebook, key)


@pytest.mark.parametrize('state', ['done', 'skipped'])
def test_both_night_paths_honour_persisted_state(notebook, monkeypatch, state):
    from connectonion.rem import threads
    mail_thread(notebook)
    threads.set_state(notebook, thread_key(notebook), state)
    monkeypatch.setattr(drafts, 'prepare', lambda *a, **k: pytest.fail('closed thread drafted'))
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: (None, None))
    maintenance = {}
    daily._draft_replies(notebook, read_config(notebook), maintenance)
    cursor = {'phase': 'daily-update', 'batch': {'done': True}, 'current': None,
              'jobs': [], 'job_index': 0, 'summaries': [], 'same_new_left': 0,
              'same_left': 0, 'slot': None, 'changed': [], 'translations': []}
    monkeypatch.setattr(native_round, 'finish', lambda *a: None)
    directory = notebook / 'task'
    directory.mkdir()
    assert native_round.prepare_task(notebook, cursor, read_config(notebook), directory) is None


def test_reader_reconciles_only_pending_offline_changes_and_undo():
    page = reader.TEMPLATE.read_text()
    names = ['doneKey', 'doneStorageKey', 'threadStorageKey', 'isDone', 'reconcileThreads', 'saveThreadState', 'setDone']
    functions = '\n'.join(re.search(r'(?:async )?function ' + name + r'\(.*?\n\}', page, re.S)[0] for name in names)
    result = _run_reader_js(functions + r'''
      const REM = {root: '/test', live: true, threads: {remote: {state: 'done'}}};
      let threadStates = {}, pendingThreads = {offline: {state: 'skipped'}}, threadWrite = Promise.resolve();
      const shortHash = x => x, stored = {}, requests = [];
      const readerStorage = (k, v) => { stored[k] = v; };
      const fetch = async (url, options) => {
        if (options) { const body = JSON.parse(options.body); requests.push(body); return {ok: true, json: async () => ({state: body.state})}; }
        return {ok: true, json: async () => ({remote: {state: 'done'}})};
      };
      const window = {scrollY: 0, scrollTo: () => {}}, navigator = {platform: 'test'};
      const document = {getElementById: () => null};
      const render = () => {}, doneNotice = () => {};
      (async () => {
        await reconcileThreads();
        const entry = {r: {path: 'p'}, t: {text: 'promise'}};
        await setDone(entry, true); const done = isDone(entry);
        await setDone(entry, false);
        const onlinePending = {...pendingThreads};
        const decision = {state: 'done', keys: [doneKey(entry), 'alias']};
        threadStates[doneKey(entry)] = decision; threadStates.alias = decision;
        REM.live = false; await setDone(entry, false);
        console.log(JSON.stringify({requests, done, undone: !isDone(entry), remote: threadStates.remote, pendingThreads: onlinePending, offlineBatchUndone: !threadStates.alias}));
      })();
    ''')
    assert [r['state'] for r in result['requests']] == ['skipped', 'done', 'open']
    assert result['done'] and result['undone'] and result['remote']['state'] == 'done'
    assert result['pendingThreads'] == {} and result['offlineBatchUndone']


def test_copied_obligation_is_closed_and_undoable_from_either_record(notebook):
    from connectonion.rem import threads
    from connectonion.rem.census import open_threads
    from connectonion.rem.files import Notebook
    mail_thread(notebook)
    book = Notebook(notebook)
    book.write('people/me.md', book.read('people/fern.md').replace('# Fern Vale', '# Owner'))
    keys = threads.set_state(notebook, thread_key(notebook), 'done')['keys']
    assert len(keys) == 2
    assert drafts.queue(notebook) == []
    assert open_threads(notebook)['mine'] == 0
    threads.set_state(notebook, keys[1], 'open')
    assert threads.listing(notebook) == {}
    assert len(drafts.queue(notebook)) == 1


def test_offline_skip_replay_does_not_swallow_new_mail(notebook):
    from connectonion.rem import threads
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    mail_thread(notebook, latest='two')
    current = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**current, 'body': 'Reply to new mail.', 'sources': ['gmail:two']})
    decision = threads.set_state(notebook, thread_key(notebook), 'skipped', versions={row['thread']: row['version']})
    assert decision['returned_at'] == '2026-11-07T02:00:00+00:00'
    assert drafts.listing(notebook)[0]['status'] == 'prepared'
    assert not threads.blocked(notebook, thread_key(notebook))
    assert drafts.listing(notebook)[0]['version'] == 'gmail:two'


def test_in_flight_native_reply_cannot_overwrite_a_done_thread(notebook):
    from connectonion.rem import threads
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    directory = notebook / 'task'
    directory.mkdir()
    task = drafts.prepare(notebook, row, read_config(notebook), directory=directory)
    threads.set_state(notebook, thread_key(notebook), 'done')
    result = native_round.check_task(notebook, {'handler': 'draft', 'task': task},
                                     {'result': json.dumps({'body': 'Review.', 'sources': ['gmail:one']})})
    assert result['discarded']
    assert not drafts.path(notebook, row['id']).exists()


def test_record_retains_undo_for_a_thread_removed_from_markdown():
    function = re.search(r'function threadDecisionHistory\(.*?\n\}', reader.TEMPLATE.read_text(), re.S)[0]
    value = _run_reader_js(function + r'''
      const REM = {as_of: '2026-11-07'}, r = {path: 'people/fern.md'};
      const threadStates = {'people/fern.md\nOld promise': {state: 'done', at: '2026-11-06'}};
      const threads = () => ({items: []}), privateFallback = x => x;
      const el = (tag, attrs, children) => ({tag, ...attrs, children});
      const fmtDate = x => x, calendarDay = x => x, actions = [];
      const setDone = (entry, done) => actions.push([entry.t.text, done]);
      const history = threadDecisionHistory(r);
      history.children[1].children[0].children.at(-1).onclick();
      console.log(JSON.stringify({history, actions}));
    ''')
    assert value['actions'] == [['Old promise', False]]
    assert value['history']['class'] == 'done-details thread-history'


def test_batch_skip_undo_restores_every_obligation_and_preserved_body(notebook):
    from connectonion.rem import threads
    from connectonion.rem.files import Notebook
    mail_thread(notebook)
    book = Notebook(notebook)
    text = book.read('people/fern.md').replace('## Sources', '- You owe Fern a budget decision. [1]\n\n## Sources')
    book.write('people/fern.md', text)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'Review and budget.', 'sources': ['gmail:one']})
    keys = [threads.done_key(item['record'], item['text']) for item in row['obligations']]
    threads.set_state(notebook, keys[0], 'skipped', keys=keys)
    saved = threads.listing(notebook)
    assert len(saved) == 2 and len({value['at'] for value in saved.values()}) == 1
    threads.set_state(notebook, keys[-1], 'open')
    assert threads.listing(notebook) == {}
    assert drafts.listing(notebook, include_pending=True)[0]['body'] == 'Review and budget.'
    assert drafts.listing(notebook)[0]['status'] == 'prepared'
