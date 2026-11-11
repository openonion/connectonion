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
    names = ['doneKey', 'doneStorageKey', 'threadStorageKey', 'isDone', 'citedVersions', 'keyEntry', 'reconcileThreads', 'showNotebookThreads',
             'notebookTook', 'sendThreadState', 'saveThreadState', 'threadMark', 'markDrafts', 'setDone']
    functions = '\n'.join(re.search(r'(?:async )?function ' + name + r'\(.*?\n\}', page, re.S)[0] for name in names)
    result = _run_reader_js(functions + r'''
      const REM = {root: '/test', live: true, threads: {remote: {state: 'done'}}};
      const byPath = () => undefined, obligationEvidence = () => ({ids: new Set()});
      let threadStates = {}, notebookThreads = {}, pendingThreads = {offline: {state: 'skipped'}}, threadWrite = Promise.resolve();
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


@pytest.mark.parametrize('state', ['done', 'skipped'])
def test_no_reply_restored_after_thread_undo(notebook, state):
    from connectonion.rem import threads
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': '', 'verdict': 'no_reply', 'sources': ['gmail:one']})
    threads.set_state(notebook, thread_key(notebook), state)
    assert threads.listing(notebook)[thread_key(notebook)]['draft_statuses'][row['id']] == {'status': 'no_reply', 'version': row['version']}
    threads.set_state(notebook, thread_key(notebook), 'open')
    assert drafts.listing(notebook)[0]['status'] == 'no_reply'


@pytest.mark.parametrize('state', ['done', 'skipped'])
def test_reader_no_reply_undo_survives_offline_reload(state):
    page = reader.TEMPLATE.read_text()
    names = ['doneKey', 'threadStorageKey', 'citedVersions', 'saveThreadState', 'threadMark', 'markDrafts', 'setDone']
    functions = '\n'.join(re.search(r'(?:async )?function ' + name + r'\(.*?\n\}', page, re.S)[0] for name in names)
    result = _run_reader_js(functions + 'const decision = ' + json.dumps(state) + ';' + r'''
      const REM = {root: '/test', live: false, drafts: [{id: 'draft', provider: 'gmail', thread: 'mail:gmail:pilot', version: 'gmail:one', status: 'no_reply', body: ''}]};
      let threadStates = {}, pendingThreads = {}, threadWrite = Promise.resolve(), stored;
      const shortHash = x => x, readerStorage = (k, v) => {stored = v;};
      const navigator = {platform: 'test'}, window = {scrollY: 0, scrollTo() {}}, document = {getElementById: () => null};
      const render = () => {}, doneNotice = () => {};
      const obligationEvidence = () => ({ids: new Set(['thread:gmail:mail:gmail:pilot'])});
      (async () => {
        const entry = {r: {path: 'people/fern.md'}, t: {text: 'Review [1]'}};
        await setDone(entry, true, decision);
        threadStates = JSON.parse(stored).states; pendingThreads = JSON.parse(stored).pending;
        await setDone(entry, false);
        console.log(JSON.stringify({status: REM.drafts[0].status}));
      })();
    ''')
    assert result['status'] == 'no_reply'


def test_skip_versions_include_owner_last_citation_and_ignore_unobserved(notebook):
    from connectonion.rem import threads
    from connectonion.rem.files import Notebook
    from connectonion.rem.mail_archive import retain_message
    from connectonion.rem.store import refresh
    mail_thread(notebook)
    retain_message(notebook, 'gmail', {'id': 'owner-old', 'from': 'owner@example.test', 'to': ['fern@example.test'],
        'subject': 'Earlier context', 'date': '2026-11-01T01:00:00+00:00', 'thread': 'context'}, 'Earlier context.', fetched_at='2026-11-01T01:00:00+00:00')
    refresh(notebook)
    book = Notebook(notebook)
    book.write('people/fern.md', book.read('people/fern.md').replace('review. [1]', 'review. [1] [2]').replace(
        '- [1] gmail:one', '- [1] gmail:one\n- [2] gmail:owner-old'))
    key = threads.done_key('people/fern.md', 'You owe Fern a pilot review. [1] [2]')
    snapshot = reader.snapshot(notebook, local=True)
    assert snapshot['mail_versions'] == {'mail:gmail:pilot': 'gmail:one', 'mail:gmail:context': 'gmail:owner-old'}
    assert reader.snapshot(notebook)['mail_versions'] == {}
    for versions in ({}, {'mail:gmail:pilot': 'gmail:one'}, snapshot['mail_versions']):
        threads.set_state(notebook, key, 'open')
        threads.set_state(notebook, key, 'skipped', versions=versions)
        assert threads.blocked(notebook, key)
        assert read_json(drafts.path(notebook, drafts.candidates(notebook)[0]['id']), {}) == {}
    threads.set_state(notebook, key, 'open')
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'Review.', 'sources': ['gmail:one']})
    threads.set_state(notebook, key, 'skipped', versions={})
    assert drafts._current(notebook, row['id'])['status'] == 'skipped'
    threads.set_state(notebook, key, 'open')
    threads.set_state(notebook, key, 'skipped', versions=snapshot['mail_versions'])
    retain_message(notebook, 'gmail', {'id': 'context-new', 'from': 'fern@example.test', 'to': ['owner@example.test'],
        'subject': 'Earlier context', 'date': '2026-11-07T03:00:00+00:00', 'thread': 'context'}, 'New context.', fetched_at='2026-11-07T03:00:00+00:00')
    refresh(notebook)
    assert not threads.blocked(notebook, key)
    assert threads.listing(notebook)[key]['returned_at'] == '2026-11-07T03:00:00+00:00'


@pytest.mark.parametrize('versions', [{}, {'mail:gmail:other': 'gmail:old'}])
def test_skip_unobserved_thread_stays_blocked_and_skips_saved_draft(notebook, versions):
    from connectonion.rem import threads
    mail_thread(notebook)
    row = drafts.queue(notebook)[0]
    drafts.promote(notebook, {**row, 'body': 'Review.', 'sources': ['gmail:one']})
    threads.set_state(notebook, thread_key(notebook), 'skipped', versions=versions)
    assert threads.blocked(notebook, thread_key(notebook))
    assert drafts._current(notebook, row['id'])['status'] == 'skipped'


@pytest.mark.parametrize('new_mail', [False, True])
def test_reader_skip_reconcile_and_fresh_snapshot_undo_uses_saved_status(new_mail):
    page = reader.TEMPLATE.read_text()
    names = ['doneKey', 'threadStorageKey', 'citedVersions', 'showNotebookThreads', 'notebookTook', 'sendThreadState', 'saveThreadState',
             'threadMark', 'markDrafts', 'setDone', 'reconcileThreads', 'threadActions', 'threadDraft', 'draftNote']
    functions = '\n'.join(re.search(r'(?:async )?function ' + name + r'\(.*?\n\}', page, re.S)[0] for name in names)
    result = _run_reader_js(functions + 'const newMail = ' + json.dumps(new_mail) + ';' + r'''
      // The mark names both threads it cites, the one no draft answers too, and not the mail of another page (#2936).
      const REM = {root: '/test', live: true, mail_versions: {'mail:gmail:pilot': 'gmail:one', 'mail:gmail:context': 'gmail:old', 'mail:gmail:elsewhere': 'gmail:other'},
        source_context: {'gmail:one': {source: 'gmail', thread: 'mail:gmail:pilot'}, 'gmail:old': {source: 'gmail', thread: 'mail:gmail:context'}},
        drafts: [{id: 'draft', provider: 'gmail', thread: 'mail:gmail:pilot', version: 'gmail:one', status: 'no_reply', body: '', gist: 'Already acknowledged'}]};
      let threadStates = {}, notebookThreads = {}, pendingThreads = {}, threadWrite = Promise.resolve(), stored, server = {}, requests = [];
      const shortHash = x => x, readerStorage = (k, v) => {stored = v;};
      const navigator = {platform: 'test'}, window = {scrollY: 0, scrollTo() {}}, document = {getElementById: () => null};
      const render = () => {}, doneNotice = () => {}, isDone = () => false;
      const obligationEvidence = () => ({ids: new Set(['gmail:one', 'gmail:old', 'thread:gmail:mail:gmail:pilot'])});
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const primaryAction = () => ({text: 'Draft the reply'});
      const fetch = async (url, options) => {
        if (!options) return {ok: true, json: async () => server};
        const request = JSON.parse(options.body); requests.push(request);
        const decision = {...request, draft_statuses: {draft: {status: 'no_reply', version: 'gmail:one'}}};
        server = request.state === 'open' ? {} : {[request.key]: decision};
        return {ok: true, json: async () => decision};
      };
      (async () => {
        const entry = {r: {path: 'people/fern.md'}, t: {text: 'Review [1] [2]'}};
        await setDone(entry, true, 'skipped');
        // A fresh live snapshot supplies server decisions and the persisted skipped draft.
        REM.drafts[0] = {...REM.drafts[0], status: 'skipped', status_before_skip: 'no_reply'};
        threadStates = {};
        await reconcileThreads();
        if (newMail) REM.drafts[0] = {...REM.drafts[0], status: 'prepared', version: 'gmail:two', body: 'Fresh reply'};
        await setDone(entry, false);
        console.log(JSON.stringify({status: REM.drafts[0].status, versions: requests[0].versions,
          actions: newMail ? null : threadActions(entry), note: newMail ? null : draftNote(REM.drafts[0])}));
      })();
    ''')
    assert result['status'] == ('prepared' if new_mail else 'no_reply')
    assert result['versions'] == {'mail:gmail:pilot': 'gmail:one', 'mail:gmail:context': 'gmail:old'}
    if not new_mail:
        assert [node['text'] for node in result['actions']['children'] if node] == ['Mark done']
        assert result['note']['text'] == 'No reply needed: Already acknowledged'


def crowd_the_version_table(root):
    """A second person's page citing enough long-id mail that the notebook's version table passes 64 KB (#2936)."""
    from connectonion.rem.files import Notebook
    from connectonion.rem.mail_archive import retain_message
    from connectonion.rem.store import refresh
    mails = [f'{n:03d}' + 'k' * 150 for n in range(260)]
    for mail in mails:
        retain_message(root, 'outlook', {'id': mail, 'from': 'juniper@example.test', 'to': ['owner@example.test'],
            'subject': 'Orchard note', 'date': '2026-10-01T01:00:00+00:00', 'thread': mail[::-1]}, 'An orchard note.',
            fetched_at='2026-10-01T01:00:00+00:00')
    Notebook(root).write('people/juniper-hale.md', '# Juniper Hale\n\n## Facts\n- Juniper sends orchard notes. '
        + ' '.join(f'[{n}]' for n in range(1, 261)) + '\n\n## Sources\n'
        + ''.join(f'- [{n}] outlook:{mail}\n' for n, mail in enumerate(mails, 1)) + '\nInvestigation: 2026-11-01\n')
    refresh(root)
    assert len(json.dumps(reader.snapshot(root, local=True)['mail_versions'])) > 65536


def mark_script(setup, steps):
    """Run the page's own thread-mark code, from the evidence a mark cites to its notice, on a small stand-in page."""
    page = reader.TEMPLATE.read_text()
    helpers = [re.search(pattern, page, re.S)[0] for pattern in (
        r'const COMMENT = [^\n]*', r'function byPath\([^\n]*', r'function shortHash\(.*?\n\}', r'function rawSection\(.*?\n\}')]
    marks = page[page.index('function obligationWords('):page.index('// The one thing to do next')]
    return _run_reader_js('\n'.join(helpers) + '\n' + marks + setup + r'''
      let stored, answer = 'saved', release;
      const shown = [], requests = [], readerStorage = (key, value) => { stored = value; };
      const navigator = {platform: 'test'}, window = {scrollY: 0, scrollTo() {}}, render = () => {}, setTimeout = () => {};
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children, focus() {}, contains: () => false,
        appendChild(child) { this.children.push(child); }, remove() { shown.splice(shown.indexOf(this), 1); }});
      const inside = (node, id) => node.id === id ? node : (node.children || []).map(child => inside(child, id)).find(Boolean);
      const words = node => typeof node === 'string' ? node : (node.textContent ?? node.text ?? '') + (node.children || []).map(words).join('');
      const document = {getElementById: id => shown.map(node => inside(node, id)).find(Boolean) || null,
        body: {appendChild: node => shown.push(node)}, querySelector: () => null};
      const fetch = async (url, options) => {
        if (!options) return {ok: true, json: async () => ({})};
        requests.push(options.body);
        // One answer for every mark, or a list with one for each in turn: 'refused' is the Host's 400, a number
        // is that status, and 'slow' is saved only once the test calls release().
        const said = Array.isArray(answer) ? answer.shift() : answer;
        if (said === 'unreachable') throw new TypeError('Failed to fetch');
        if (said === 'slow') await new Promise(resume => { release = resume; });
        return ['saved', 'slow'].includes(said) ? {ok: true, json: async () => JSON.parse(options.body)}
          : {ok: false, status: said === 'refused' ? 400 : said, json: async () => ({error: 'Invalid JSON'})};
      };
      const entry = {r: byPath('people/fern.md'), t: {text: 'You owe Fern a pilot review. [1]'}};
      (async () => {''' + steps + '})();')


def notebook_page(root):
    """What the live page holds of this notebook when its owner marks a thread."""
    snapshot = reader.snapshot(root, local=True)
    return 'const REM = ' + json.dumps({'root': '/test', 'live': True, **{key: snapshot[key] for key in (
        'records', 'source_context', 'mail_versions', 'drafts')}}) + ';'


def host_answers(root, tmp_path_factory, body):
    from connectonion.rem.live_host import reader_token
    from tests.unit.test_rem_live_reader import call
    identity = tmp_path_factory.mktemp('identity')
    return call({'rem_root': root, 'identity_dir': identity}, 'POST', '/rem/thread',
                cookie='co_rem=' + reader_token(identity), body=body.encode())[0]


MARK_THEN_UNDO = "await setDone(entry, true); await setDone(entry, false); console.log(JSON.stringify(requests));"


def test_done_and_undo_from_a_crowded_notebook_reach_threads_json(notebook, tmp_path_factory):
    """#2936: over 64 KB of versions the Host answered 400, and the page called that "sync pending"."""
    mail_thread(notebook)
    crowd_the_version_table(notebook)
    done, undo = mark_script(notebook_page(notebook), MARK_THEN_UNDO)
    assert host_answers(notebook, tmp_path_factory, done) == 200
    assert read_json(state_path(notebook, 'threads.json'), {})[thread_key(notebook)]['state'] == 'done'
    assert host_answers(notebook, tmp_path_factory, undo) == 200
    assert thread_key(notebook) not in read_json(state_path(notebook, 'threads.json'), {})


def test_mark_request_does_not_grow_with_the_notebook(notebook):
    mail_thread(notebook)
    alone = mark_script(notebook_page(notebook), MARK_THEN_UNDO)
    crowd_the_version_table(notebook)
    crowded = mark_script(notebook_page(notebook), MARK_THEN_UNDO)
    assert crowded == alone
    assert json.loads(crowded[0])['versions'] == {'mail:gmail:pilot': 'gmail:one'}


def test_mark_kept_with_the_whole_table_goes_through_on_the_next_load(notebook, tmp_path_factory):
    """A browser that marked Done before the fix still holds that mark, whole table and all, in its pending list."""
    mail_thread(notebook)
    crowd_the_version_table(notebook)
    sent, = mark_script(notebook_page(notebook), r'''
      const key = doneKey(entry);
      pendingThreads = {[key]: {state: 'done', at: '2026-11-08T01:00:00.000Z', device: 'test', keys: [key], versions: REM.mail_versions}};
      await reconcileThreads();
      console.log(JSON.stringify(requests));''')
    assert json.loads(sent)['versions'] == {'mail:gmail:pilot': 'gmail:one'}
    assert host_answers(notebook, tmp_path_factory, sent) == 200
    assert read_json(state_path(notebook, 'threads.json'), {})[thread_key(notebook)]['state'] == 'done'


FERN_PAGE = r'''const REM = {root: '/test', live: true, mail_versions: {'mail:gmail:pilot': 'gmail:one'},
  records: [{path: 'people/fern.md', text: '# Fern Vale\n\n## Open threads\n- You owe Fern a pilot review. [1]\n\n## Sources\n- [1] gmail:one\n'}],
  source_context: {'gmail:one': {thread: 'mail:gmail:pilot', source: 'gmail'}},
  drafts: [{id: 'draft', provider: 'gmail', thread: 'mail:gmail:pilot', version: 'gmail:one', status: 'prepared'}]};'''
PAGE_AFTER_MARK = r'''{pending: Object.keys(pendingThreads), kept: Object.keys(JSON.parse(stored).pending), marked: isDone(entry),
  draft: REM.drafts[0].status, notice: shown.map(words).join(' | '), requests: requests.length}'''


def test_refused_mark_is_not_saved_and_can_be_tried_again():
    """The Host answered and said no: nothing is waiting to sync, the thread is back, and the page says so."""
    refused, retried = mark_script(FERN_PAGE, r'''
      answer = 'refused';
      await setDone(entry, true, 'skipped');
      const refused = ''' + PAGE_AFTER_MARK + r''';
      answer = 'saved';
      await shown[0].children.find(child => child.tag === 'button' && child.text === 'Try again')?.onclick();
      console.log(JSON.stringify([refused, ''' + PAGE_AFTER_MARK + ']));')
    assert refused == {'pending': [], 'kept': [], 'marked': False, 'draft': 'prepared', 'notice': 'Not saved · Try again', 'requests': 1}
    assert retried['marked'] and retried['draft'] == 'skipped' and retried['requests'] == 2
    assert 'Saved in notebook' in retried['notice'] and retried['pending'] == []


@pytest.mark.parametrize('answer', ["'unreachable'", '409', '500', '503'])
def test_unreachable_busy_or_failing_notebook_leaves_a_mark_waiting_to_sync(answer):
    """409 is a notebook another writer holds for a moment, 5xx a Host that failed: neither said no to the mark."""
    waiting, = mark_script(FERN_PAGE, 'answer = ' + answer + "; await setDone(entry, true, 'skipped');"
                           'console.log(JSON.stringify([' + PAGE_AFTER_MARK + ']));')
    assert waiting['pending'] == waiting['kept'] == ['people/fern.md\nYou owe Fern a pilot review. [1]']
    assert waiting['marked'] and waiting['draft'] == 'skipped'
    assert 'Saved on this device — sync pending' in waiting['notice'] and 'Not saved' not in waiting['notice']


def test_refused_mark_kept_from_an_earlier_visit_stops_waiting_and_returns_to_the_notebook_state():
    state, = mark_script(FERN_PAGE, r'''
      const key = doneKey(entry);
      pendingThreads = {[key]: {state: 'done', keys: [key], versions: {}}};
      answer = 'refused';
      await reconcileThreads();
      console.log(JSON.stringify([{pending: Object.keys(pendingThreads), kept: Object.keys(JSON.parse(stored).pending), marked: isDone(entry)}]));''')
    assert state == {'pending': [], 'kept': [], 'marked': False}


@pytest.mark.parametrize('status', [409, 503])
def test_mark_kept_from_an_earlier_visit_waits_out_a_busy_notebook_and_is_saved_on_the_next_one(status):
    """A waiting mark met by a busy notebook used to be dropped without a word: it is sent again until it is taken."""
    busy, saved = mark_script(FERN_PAGE, r'''
      const key = doneKey(entry), state = () => ({pending: Object.keys(pendingThreads),
        kept: Object.keys(JSON.parse(stored).pending), marked: isDone(entry), requests: requests.length});
      pendingThreads = {[key]: {state: 'done', keys: [key], versions: {}}};
      answer = ''' + str(status) + r''';
      await reconcileThreads();
      const busy = state();
      answer = 'saved';
      await reconcileThreads();
      console.log(JSON.stringify([busy, state()]));''')
    key = 'people/fern.md\nYou owe Fern a pilot review. [1]'
    assert busy == {'pending': [key], 'kept': [key], 'marked': True, 'requests': 1}
    assert saved == {'pending': [], 'kept': [], 'marked': True, 'requests': 2}


def test_host_answers_409_for_a_busy_notebook_and_400_for_a_mark_it_will_never_take(notebook, tmp_path_factory):
    """The page waits on a 409 and gives up on a 400, so the Host must keep the two apart."""
    from connectonion.rem.files import maintenance_lock
    mail_thread(notebook)
    mark = json.dumps({'key': thread_key(notebook), 'state': 'done'})
    with maintenance_lock(notebook):
        assert host_answers(notebook, tmp_path_factory, mark) == 409
    assert host_answers(notebook, tmp_path_factory, mark) == 200
    gone = json.dumps({'key': 'people/juniper-hale.md\nYou owe Juniper an orchard note. [1]', 'state': 'done'})
    assert host_answers(notebook, tmp_path_factory, gone) == 400


@pytest.mark.parametrize('done, held', [
    ("answer = 'saved'; await setDone(entry, true); answer = 'refused';", True),
    ("answer = 'unreachable'; await setDone(entry, true); answer = 'refused';", False),
    ("answer = 'refused'; setDone(entry, true);", False)], ids=['taken', 'waiting', 'not yet sent'])
def test_refused_undo_shows_what_the_notebook_holds_not_a_done_it_never_took(done, held):
    """Undo of a Done the notebook took leaves it done; Undo of one still waiting, or not yet sent, leaves no mark."""
    state, = mark_script(FERN_PAGE, done + ' await setDone(entry, false);'
                         'console.log(JSON.stringify([' + PAGE_AFTER_MARK + ']));')
    assert state['marked'] is held and state['pending'] == state['kept'] == []
    assert state['notice'] == 'Not saved · Try again'


def test_refusal_of_one_mark_keeps_the_notice_of_the_mark_made_after_it():
    """Two quick marks, the first refused: the second keeps its Undo and says "Saved" only once it is saved."""
    during, after, marked = mark_script(FERN_PAGE, r'''
      const next = {r: entry.r, t: {text: 'You owe Fern a budget decision. [1]'}};
      answer = ['refused', 'slow'];
      const first = setDone(entry, true), second = setDone(next, true);
      await first;
      const during = shown.map(words).join(' | ');
      release();
      await second;
      console.log(JSON.stringify([during, shown.map(words).join(' | '), [isDone(entry), isDone(next)]]));''')
    assert during == 'Marked done · Undo · Saving…Not saved · Try again'
    assert after == 'Marked done · Undo · Saved in notebookNot saved · Try again'
    assert marked == [False, True]


def test_not_saved_notice_reads_in_chinese():
    page = reader.TEMPLATE.read_text()
    assert '"Not saved": "未保存"' in page and '"Try again": "重试"' in page


def test_skip_returns_on_new_mail_in_a_cited_thread_the_page_could_not_place(notebook):
    """The page names a thread only when it holds that mail's context; the notebook records the rest at its latest."""
    from connectonion.rem import threads
    mail_thread(notebook)
    threads.set_state(notebook, thread_key(notebook), 'skipped', versions={})
    assert threads.blocked(notebook, thread_key(notebook))
    mail_thread(notebook, latest='two')
    assert threads.listing(notebook)[thread_key(notebook)].get('returned_at') == '2026-11-07T02:00:00+00:00'
    assert not threads.blocked(notebook, thread_key(notebook))


def test_waiting_skip_keeps_the_versions_it_stored_when_the_page_cannot_place_its_mail(notebook, tmp_path_factory):
    """Mail that came while a Skip waited is not counted as seen: the mark goes out with what its reader saw."""
    from connectonion.rem import threads
    mail_thread(notebook)
    waiting = {'state': 'skipped', 'keys': [thread_key(notebook)], 'versions': {'mail:gmail:pilot': 'gmail:one'}}
    mail_thread(notebook, latest='two')
    sent, = mark_script(notebook_page(notebook) + 'REM.source_context = {};', 'pendingThreads = {[doneKey(entry)]: '
                        + json.dumps(waiting) + '}; await reconcileThreads(); console.log(JSON.stringify(requests));')
    assert json.loads(sent)['versions'] == {'mail:gmail:pilot': 'gmail:one'}
    assert host_answers(notebook, tmp_path_factory, sent) == 200
    assert threads.listing(notebook)[thread_key(notebook)].get('returned_at') == '2026-11-07T02:00:00+00:00'
    assert not threads.blocked(notebook, thread_key(notebook))
