"""Archived coding sessions keep their order, client identity and privacy boundary."""

import json
import re

import pytest

from connectonion.rem.reader import TEMPLATE, snapshot
from connectonion.rem.reader_model import session_detail
from test_rem_reader import _run_reader_js


PAGE = """# Make the reader feel like home

## Facts
- Date: 2026-11-07
- Agent: Codex
- Folder: /work/lantern
- Session: fictional-session-42
- Turns: 3
- Ended: 2026-11-07 10:24

## What you typed
### 09:12
> Build a quiet transcript.

### 09:21
> A private instruction [personal]

### 10:02
> Keep the timestamps.

## Final reply
> Added the transcript and checked both themes.

## Sources
- codex:fictional-session-42:10
- codex:fictional-session-42:20
- codex:fictional-session-42:30
"""


def functions(*names):
    page = TEMPLATE.read_text()
    return '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S)[0] for name in names)


def test_reader_session_detail_has_ordered_turns_and_tool_kind():
    detail = session_detail(PAGE, private=True)
    assert detail['session_kind'] == 'codex'
    assert detail['session_id'] == 'fictional-session-42'
    assert [m['role'] for m in detail['session_messages']] == ['user', 'user', 'user', 'assistant']
    assert [m['time'] for m in detail['session_messages']] == ['09:12', '09:21', '10:02', '2026-11-07 10:24']
    assert detail['session_messages'][2]['source'] == 'codex:fictional-session-42:30'
    assert '<' not in detail['session_messages'][0]['text']


@pytest.mark.parametrize('label', ['[personal]', '［sensitive］'])
def test_reader_session_detail_omits_labelled_turns_without_owner_access(label):
    text = PAGE.replace('[personal]', label)
    detail = session_detail(text)
    assert 'private instruction' not in json.dumps(detail)
    assert [m['id'] for m in detail['session_messages']] == ['session-message-1', 'session-message-3', 'session-final']
    assert 'private instruction' in json.dumps(session_detail(text, private=True))
    assert session_detail(text.replace('Added the transcript and checked both themes.', 'Secret reply ' + label))['session_messages'][-1]['role'] == 'user'


def test_reader_session_snapshot_passes_owner_boundary(tmp_path):
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    (tmp_path / 'sessions').mkdir(exist_ok=True)
    (tmp_path / 'sessions' / 'example.md').write_text(PAGE)
    public = next(r for r in snapshot(tmp_path)['records'] if r['category'] == 'sessions')
    owner = next(r for r in snapshot(tmp_path, local=True)['records'] if r['category'] == 'sessions')
    assert len(public['session_messages']) == 3
    assert len(owner['session_messages']) == 4


@pytest.mark.parametrize('kind,name,expected', [
    ('codex', 'Codex', 'codex resume fictional-session-42'),
    ('claude-code', 'Claude Code', 'claude --resume fictional-session-42'),
])
def test_reader_session_resume_uses_exact_client_command(kind, name, expected):
    result = _run_reader_js(functions('sessionTool', 'sessionResumeCommand') + '''
      const sessionAgent = r => r.session_agent.toLowerCase().replaceAll(' ', '-');
      const r = ''' + json.dumps({'session_kind': kind, 'session_agent': name, 'session_id': 'fictional-session-42'}) + ''';
      console.log(JSON.stringify(sessionResumeCommand(r)));
    ''')
    assert result == expected


def test_reader_session_resume_quotes_shell_metacharacters_and_requires_metadata():
    result = _run_reader_js(functions('sessionTool', 'sessionResumeCommand', 'sessionSection') + r'''
      const sessionAgent = r => r.session_agent || '';
      const r = {session_kind: 'codex', session_id: "a'; touch /tmp/oops", text: ''};
      console.log(JSON.stringify([sessionResumeCommand(r), sessionResumeCommand({...r, session_id: ''}),
        sessionResumeCommand({...r, session_kind: 'other'})]));
    ''')
    assert result == ["codex resume 'a'\\''; touch /tmp/oops'", '', '']


@pytest.mark.parametrize('kind,name', [('codex', 'Codex'), ('claude-code', 'Claude Code')])
def test_reader_session_frame_renders_tool_name_and_archived_turns(kind, name):
    script = functions('sessionTool', 'sessionToolMark', 'sessionFrame', 'sessionTranscriptTurn',
                       'sessionMissingReply', 'sessionQuote')
    result = _run_reader_js(script + '''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        append(...nodes) {this.children.push(...nodes)}, appendChild(node) {this.children.push(node)}});
      const sessionFind = () => ({node: {tag: 'search'}}), route = () => ({});
      const sessionArchivedTools = () => null, sessionComposer = () => ({tag: 'composer'});
      const document = {createDocumentFragment: () => ({})};
      const sessionDuration = () => '72m', fmtDate = date => date;
      const r = ''' + json.dumps({'session_kind': kind, 'session_agent': name, 'session_date': '2026-11-07',
                                 'session_folder': '/work/lantern', 'session_messages': session_detail(PAGE, private=True)['session_messages']}) + ''';
      console.log(JSON.stringify(sessionFrame(r).node));
    ''')
    assert result['class'] == 'session-device ' + kind
    bar = result['children'][0]
    assert bar['children'][1]['children'][1] == name
    assert bar['children'][2]['text'] == 'lantern'
    body = result['children'][3]
    turns = [node for node in body['children'] if node.get('class', '').startswith('session-turn')]
    assert len(turns) == 4
    assert turns[1]['class'].endswith(' private')
    assert turns[-1]['children'][1]['text'] == 'Added the transcript and checked both themes.'


def test_reader_session_duration_uses_archived_range_including_midnight():
    result = _run_reader_js(functions('sessionDuration') + '''
      const sessionMessages = r => r.messages;
      const r = {session_date: '2026-11-07', messages: [{time: '23:50'}, {time: '2026-11-08 00:15'}]};
      console.log(JSON.stringify([sessionDuration(r), sessionDuration({...r, session_ended: '2026-11-08 00:30'}),
        sessionDuration({...r, messages: [{time: '23:50'}]})]));
    ''')
    assert result == ['At least 25m', '40m', 'Duration not archived']


def test_reader_session_command_privacy_keeps_markers_outside_code():
    page = PAGE.replace('## What you typed', '## Artifacts\n- Commands: 1 run; notable: `deploy confidential-project` [sensitive]\n\n## What you typed')
    assert session_detail(page)['session_commands'] == []
    assert session_detail(page, private=True)['session_commands'] == [{'text': 'deploy confidential-project', 'private': True}]
    result = _run_reader_js(functions('sessionArchivedTools', 'sessionSection') + '''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const r = ''' + json.dumps({'text': page, **session_detail(page, private=True)}) + ''';
      console.log(JSON.stringify(sessionArchivedTools(r)));
    ''')
    assert result['children'][1]['class'] == 'session-tool-call private'


def test_reader_session_tools_are_collapsed_and_keep_only_archived_commands():
    page = PAGE.replace('## What you typed', '## Artifacts\n- Commands: 2 run; notable: `co rem status`; `git diff --stat`\n\n## What you typed')
    result = _run_reader_js(functions('sessionArchivedTools', 'sessionSection') + '''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const r = ''' + json.dumps({'text': page, **session_detail(page)}) + ''';
      console.log(JSON.stringify(sessionArchivedTools(r)));
    ''')
    assert [node['children'][1]['children'][0]['text'] for node in result['children'][1:]] == ['co rem status', 'git diff --stat']
    assert all('open' not in node for node in result['children'][1:])


def test_reader_session_running_sorts_ahead_of_newer_archived_sessions():
    result = _run_reader_js(functions('sessionOrder') + '''
      const rows = [
        {path: 'new', session_date: '2026-11-07', session_time: '12:00'},
        {path: 'old', session_date: '2026-11-06', session_time: '12:00'},
        {path: 'running', session_date: '2026-11-05', session_status: 'running'}];
      console.log(JSON.stringify(rows.sort(sessionOrder).map(r => r.path)));
    ''')
    assert result == ['running', 'new', 'old']


def test_reader_session_find_keeps_hidden_text_and_refreshes_after_reveal():
    result = _run_reader_js(functions('sessionFind') + '''
      let hidden = true;
      const document = {documentElement: {classList: {contains: () => hidden}}};
      const quote = {textContent: 'Archived secret [personal]', closest: () => null};
      const body = {querySelectorAll: selector => selector === '.session-quote' ? [quote] : [], addEventListener() {}};
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children});
      const sessionButton = text => ({text});
      const calls = [];
      const sessionMarkText = (node, text, needle) => {node.textContent = text; calls.push([text, needle])};
      const find = sessionFind({}, body, 'secret');
      find.run(); hidden = false; find.node.refreshSessionFind();
      console.log(JSON.stringify(calls));
    ''')
    assert result == [['Archived secret [personal]', ''], ['Archived secret [personal]', 'secret']]


def test_reader_session_citation_jump_highlights_the_requested_turn():
    result = _run_reader_js(functions('sessionJump') + '''
      const calls = [];
      const target = {closest: () => null, parentElement: null,
        classList: {add: value => calls.push(value)}, scrollIntoView: options => calls.push(options)};
      const document = {getElementById: () => target, documentElement: {classList: {contains: () => false}}};
      sessionJump('session-message-2');
      console.log(JSON.stringify(calls));
    ''')
    assert result == ['session-cited', {'block': 'center'}]
