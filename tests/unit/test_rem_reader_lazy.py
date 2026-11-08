"""Today works without loading the notebook's full records or conversations."""

import json
import re
import shutil
import subprocess

import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.reader import TEMPLATE, render
from test_rem_reader import _run_reader_js


def test_inline_detail_waits_for_document_and_preserves_queue_state():
    function = re.search(r'function loadDetails\(.*?\n\}', TEMPLATE.read_text(), re.S)[0]
    result = _run_reader_js(function + r'''
      const current = {path: 'people/alice.md', text: 'Queue projection', readLanguage: 'zh',
        original: 'Untranslated queue projection', shown: 'zh'};
      const REM = {records: [current], drafts: [{id: 'edited', body: 'Edited on Today'}],
        source_context: {'gmail:queue': {excerpt: 'Queue evidence'}}};
      let detailLoad = null, detailReady = false, ready, parsed = false;
      const KNOWN = new Map(), FACTS = new Map(), PARSED_FACTS = new Map(), SESSION_TEXT = new Map();
      let PEOPLE_BY_ADDRESS = new Map();
      const document = {readyState: 'loading', addEventListener(name, callback) {ready = callback;},
        getElementById() {parsed = true; return {textContent: JSON.stringify({
          records: [{path: current.path, text: 'Full fictional prose', translations: {zh: '全文'}}],
          drafts: [{id: 'old', body: 'Older draft'}],
          source_context: {'gmail:other': {excerpt: 'Full evidence'}}})};}};
      (async () => {
        const pending = loadDetails(), before = parsed;
        ready(); await pending;
        console.log(JSON.stringify({before, detailReady, text: current.text,
          language: current.readLanguage, sameRecord: REM.records[0] === current,
          original: current.original ?? null, shown: current.shown,
          body: REM.drafts[0].body, contexts: Object.keys(REM.source_context).sort()}));
      })();
    ''')
    assert result == {'before': False, 'detailReady': True, 'text': 'Full fictional prose',
                      'language': 'zh', 'sameRecord': True, 'original': None, 'shown': '',
                      'body': 'Edited on Today',
                      'contexts': ['gmail:other', 'gmail:queue']}


def test_full_snapshot_does_not_parse_a_deferred_payload():
    template = TEMPLATE.read_text()
    function = re.search(r'function loadDetails\(.*?\n\}', template, re.S)[0]
    readiness = re.search(r'let detailLoad = .*?;', template)[0]
    assert _run_reader_js('const REM = {};\n' + readiness + '\n' + function + r'''
      loadDetails().then(() => console.log(JSON.stringify('ready')));
    ''') == 'ready'


def test_offline_startup_finishes_details_without_navigation():
    template = TEMPLATE.read_text()
    loader = re.search(r'function loadDetails\(.*?\n\}', template, re.S)[0]
    startup = template[template.index('Promise.all([readerStorage('):].split('</script>')[0]
    result = _run_reader_js(loader + r'''
      const REM = {records: [], drafts: [], threads: {}, source_context: {}};
      let detailLoad = null, detailReady = false, morePeopleColumns,
        pendingThreads, threadStates, peopleMode, notDoneKeys;
      const KNOWN = new Map(), FACTS = new Map(), PARSED_FACTS = new Map(), SESSION_TEXT = new Map();
      let PEOPLE_BY_ADDRESS = new Map();
      const location = {protocol: 'file:'};
      const document = {readyState: 'complete', documentElement: {dataset: {}},
        getElementById() {return {textContent: JSON.stringify({records: [], logs: [], source_context: {}})};}};
      const readerStorage = () => Promise.resolve(null);
      const doneStorageKey = () => 'done', threadStorageKey = () => 'threads', notDoneStorageKey = () => 'not-done';
      const reconcileThreads = () => Promise.resolve();
      const frames = [];
      function render() {frames.push({ready: detailReady, logs: Array.isArray(REM.logs)});}
    ''' + 'const startup = ' + startup + r'''
      startup.then(() => console.log(JSON.stringify(frames)));
    ''')
    assert result[0] == {'ready': False, 'logs': False}
    assert result[-1] == {'ready': True, 'logs': True}


def test_today_renders_a_usable_first_card_without_parsing_detail(tmp_path, monkeypatch):
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    prepare(tmp_path)
    Notebook(tmp_path).write('people/alice.md', '''# Alice
## Facts
- Email: alice@example.test
## Open threads
- You owe Alice feedback by 2000-01-01 [1].
## Sources
- [1] gmail:fixture — feedback request
''')
    page = render(tmp_path, local=True)
    script = re.search(r'<script>\s*"use strict";(.*?)</script>', page, re.S)[1]
    script = script[:script.index('document.addEventListener("keydown"')]
    # Exercise the actual Today renderer with only its DOM construction stubbed.
    # No detail element or fetch exists: an eager parse/request fails this test.
    script = 'const window = {};\n' + script + r'''
      function el(tag, attrs = {}, children = []) {
        return {tag, ...attrs, children: children.filter(x => x != null),
          innerHTML: attrs.html || '',
          classList: {add() {}, toggle() {}, contains() {return false;}}, setAttribute() {},
          appendChild(node) {this.children.push(node); return node;},
          append(...nodes) {this.children.push(...nodes);},
          cloneNode() {return this;},
          querySelector() {return null;}, querySelectorAll() {return [];}};
      }
      const main = el('main');
      const document = {getElementById(id) {
        if (id === 'approval-undo') return null;
        if (id !== 'main') throw Error('Today tried to load ' + id);
        return main;
      }};
      uiLanguage = 'en';
      overview();
      console.log(JSON.stringify(main));
    '''
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required to execute the reader')
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    tree = json.loads(result.stdout)
    def nodes(node):
        if isinstance(node, dict):
            yield node
            for child in node.get('children', []):
                yield from nodes(child)
    rendered = list(nodes(tree))
    assert any(n['tag'] == 'h1' and n.get('text') == '1 person is waiting on you.' for n in rendered)
    assert any(n['tag'] == 'b' and 'overdue' in n.get('text', '') for n in rendered)
    card = next(n for n in rendered if 'qcard' in n.get('class', ''))
    assert any(n.get('class') == 'words' and 'feedback' in n.get('text', '').lower() for n in nodes(card))
    # REM cannot draft from an unarchived message yet, and a mail-app compose would start a new thread.
    assert not any(n.get('href', '').startswith('mailto:') for n in nodes(card))
    assert any(n.get('text') == 'Open Alice' for n in nodes(card))


def test_reader_shell_defers_full_prose_translations_and_conversations(tmp_path, monkeypatch):
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    prepare(tmp_path)
    Notebook(tmp_path).write('people/alice.md', '''# Alice

## Facts
- Email: alice@example.test

## Our relationship
Full relationship prose belongs in the lazy record.

## Open threads
- You owe Alice feedback since 2026-11-07 [1].

## Sources
- [1] gmail:fixture — feedback request
''')
    monkeypatch.setattr('connectonion.rem.reader_model.cited_context', lambda *a, **k: {
        'gmail:fixture': {'source': 'gmail', 'thread': 'fixture', 'excerpt': 'Please review.'}})
    monkeypatch.setattr('connectonion.rem.reader_model.cited_conversations', lambda *a, **k: {
        'fixture': {'messages': [{'excerpt': 'Heavy conversation history.'}]}})
    monkeypatch.setattr('connectonion.rem.translate.cached_languages', lambda *a: {
        'zh': '# Alice\n\n## Our relationship\nFull translated prose stays lazy.\n\n'
              '## Open threads\n- 请给 Alice 反馈 [1].\n'})
    page = render(tmp_path, local=True)
    shell = json.loads(re.search(r'const REM = (.*);', page).group(1))
    assert shell['deferred_details'] is True
    assert 'Full relationship prose' not in json.dumps(shell)
    assert 'Heavy conversation history' not in json.dumps(shell)
    assert 'Full translated prose' not in json.dumps(shell)
    assert not shell.get('conversations')
    assert not shell.get('logs')
    alice = next(r for r in shell['records'] if r['path'] == 'people/alice.md')
    assert 'You owe Alice feedback' in alice['text']
    assert shell['source_context']['gmail:fixture']['thread'] == 'fixture'
    lazy = json.loads(re.search(r'<script id="rem-detail" type="application/json">(.*?)</script>', page, re.S).group(1))
    assert 'Full relationship prose' in json.dumps(lazy)
    assert 'Heavy conversation history' in json.dumps(lazy)
    assert 'Full translated prose' in json.dumps(lazy)


def test_live_shell_does_not_build_conversations_or_relationships(tmp_path, monkeypatch):
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    prepare(tmp_path)
    Notebook(tmp_path).write('people/alice.md', '# Alice\n\n## Open threads\n- You owe feedback.\n')
    def heavy(*args, **kwargs):
        raise AssertionError('Today must not build the heavy notebook')
    monkeypatch.setattr('connectonion.rem.reader_model.cited_conversations', heavy)
    monkeypatch.setattr('connectonion.rem.reader_model.relationships', heavy)
    page = render(tmp_path, live=True, local=True)
    assert 'You owe feedback' in page
    assert '/rem/data.json' in page
