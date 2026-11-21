"""#3147: reviewable outcomes, isolated files and fresh retries, with no real agents."""
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

from tests.unit.test_rem_live_reader import call, host  # noqa: F401
from tests.unit.test_rem_tasks import task_notebook  # noqa: F401
from connectonion.rem import drafts, night, tasks
from connectonion.rem.config import set_config
from connectonion.rem.files import RemError, read_json, write_json


def finished(root, result='completed', text='已检查合同，等你确认。\n\n详细证据。'):
    receipt = tasks.reserve(root, night.listing(root)[0])
    receipt.update(result=result, finished_at='2026-11-09T12:00:00+00:00', reason='Operation not permitted (os error 1)')
    write_json(Path(receipt['receipt']), receipt)
    if text:
        Path(receipt['deliverable']).write_text(text)
    return receipt


def test_prompt_uses_owner_language_summary_reply_fence_and_own_browser_tab(task_notebook):
    set_config(task_notebook, ['languages', 'en,zh'])
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    prompt = tasks._prompt(receipt)
    assert '中文 (zh)' in prompt
    assert 'Start with a one-line summary' in prompt
    assert '```reply' in prompt
    tab = 'rem-' + receipt['id']
    assert f'co browser tab open {tab}' in prompt
    assert f'-t {tab}' in prompt and 'every browser command' in prompt
    assert f'co browser tab close {tab}' in prompt


def test_result_summary_comes_from_report_and_reply_is_not_a_completion_notice(task_notebook):
    receipt = finished(task_notebook, text='# 已核对合同。\n\n证据在这里。\n\n```reply\n你好，合同已收到。\n```')
    projected = tasks.receipt_for(task_notebook, receipt['key'])
    assert projected['summary'] == '已核对合同。'
    assert projected['reply'] == '你好，合同已收到。'
    assert projected['has_output'] is True
    assert not projected.get('prepared_reply')


def test_reply_action_promotes_only_a_prepared_local_draft(task_notebook, monkeypatch):
    receipt = finished(task_notebook, text='已核对合同。\n\n```reply\n你好，合同已收到。\n```')
    row = {'id': 'b' * 32, 'version': 'outlook:latest', 'provider': 'outlook', 'thread': 'mail:outlook:one',
           'to': 'mara@example.test', 'obligations': [{'record': receipt['record'], 'text': receipt['text']}],
           'material': [{'source': 'outlook:latest'}]}
    monkeypatch.setattr(drafts, 'candidates', lambda *a, **kw: [row])
    monkeypatch.setattr(drafts, 'send', lambda *a: pytest.fail('must never send'))
    monkeypatch.setattr(drafts, 'open_provider', lambda *a: pytest.fail('local draft only'))
    prepared = tasks.prepare_reply(task_notebook, receipt['id'])
    saved = read_json(drafts.path(task_notebook, row['id']), {})
    assert prepared['id'] == row['id'] and saved['status'] == 'prepared'
    assert saved['body'] == '你好，合同已收到。' and saved['send'] == 'owner'
    assert saved['sources'] == ['outlook:latest']


def test_retry_archives_old_work_and_starts_fresh_for_same_item(task_notebook, monkeypatch):
    receipt = finished(task_notebook, 'failed', text='')
    folder = Path(receipt['receipt']).parent
    (folder / 'events.jsonl').write_text('{"summary":"stale"}\n')
    (folder / 'work').mkdir()
    (folder / 'work' / 'stale.txt').write_text('old attempt')
    seen = []
    monkeypatch.setattr(tasks, 'start', lambda root, key, agent=None: seen.append(key) or tasks.receipt_for(root, receipt['key']))
    fresh = tasks.retry(task_notebook, receipt['id'])
    assert seen == [receipt['id']] and fresh['result'] == 'queued'
    assert not (folder / 'events.jsonl').exists() and not (folder / 'work').exists()
    assert list(folder.parent.glob('history/*/work/stale.txt'))
    assert fresh['agent'] == 'codex' and fresh['key'] == receipt['key']


def test_failed_without_output_has_chinese_reason_and_can_be_cleared(task_notebook):
    receipt = finished(task_notebook, 'failed', text='')
    projected = tasks.receipt_for(task_notebook, receipt['key'])
    assert projected['failure'] == 'Codex 当时无法启动（已修复），可以重试'
    assert projected['has_output'] is False
    assert tasks.clear_failed(task_notebook)['cleared'] == [receipt['id']]
    assert tasks.receipt_for(task_notebook, receipt['key']) is None
    assert Path(receipt['receipt']).exists()  # clearing preserves the audit trail


def test_task_files_are_owner_only_and_confined_to_that_tasks_work_folder(host):
    task_id = 'a' * 32
    folder = tasks.directory(host.root, task_id)
    (folder / 'work' / 'evidence').mkdir(parents=True)
    (folder / 'receipt.json').write_text('{}')
    (folder / 'work' / 'evidence' / '合同.txt').write_text('合同证据')
    outside = folder / 'private.txt'
    outside.write_text('secret')
    (folder / 'work' / 'escape.txt').symlink_to(outside)
    endpoint = '/rem/task-file'
    query = lambda path: urlencode({'id': task_id, 'path': path}).encode()
    assert call(host.routes, 'GET', endpoint, query=query('work/evidence/合同.txt'))[0] == 401
    cookie = f'co_rem={host.token}'
    status, headers, body = call(host.routes, 'GET', endpoint, cookie=cookie, query=query('work/evidence/合同.txt'))
    assert status == 200 and body == '合同证据' and headers['content-type'].startswith('text/plain')
    for path in ('../private.txt', 'work/../private.txt', '/etc/passwd', 'escape.txt', '../do-' + 'b' * 32 + '/work/a.txt'):
        assert call(host.routes, 'GET', endpoint, cookie=cookie, query=query(path))[0] == 404, path
    assert call(host.routes, 'GET', endpoint, cookie=cookie, query=query('missing.txt'))[0] == 404
    for kwargs in ({'client': '192.168.1.2'}, {'host_header': 'evil.test'}):
        assert call(host.routes, 'GET', endpoint, cookie=cookie, query=query('evidence/合同.txt'), **kwargs)[0] == 404


def test_task_actions_validate_retry_draft_and_bulk_clear(host, monkeypatch):
    calls = []
    for name in ('retry', 'prepare_reply'):
        monkeypatch.setattr(tasks, name, lambda root, key: calls.append(key) or {'id': key}, raising=False)
        payload = json.dumps({'action': name, 'id': 'a' * 32}).encode()
        assert call(host.routes, 'POST', '/rem/task', body=payload)[0] == 401
        assert call(host.routes, 'POST', '/rem/task', cookie=f'co_rem={host.token}', body=payload)[0] == 200
    assert calls == ['a' * 32, 'a' * 32]


def test_optimistic_handoff_survives_snapshot_until_explicit_refusal():
    import re
    from connectonion.rem.reader import TEMPLATE
    from tests.unit.test_rem_reader import _run_reader_js
    names = ['todayRow', 'obligationKey', 'rowTask', 'keepTask', 'handOver', 'handRefusal', 'clockNow', 'refreshHandoff']
    code = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0) for name in names)
    value = _run_reader_js(code + '''
      const REM = {today_queue: [{key:'item', keys:['item'], task:null}]};
      const HAND_FAILED = new Map(), PENDING_HANDOFFS = new Map(), AGENT_NAMES = {codex:'Codex', claude:'Claude'};
      const doneKey = e => e.key, railActive = () => 'waiting';
      let answer; const hostPost = () => new Promise(resolve => answer = resolve);
      const entry = {key:'item'};
      const pending = handOver(entry, 'codex', () => {}, null, {});
      const immediate = rowTask(entry);
      REM.today_queue = [{key:'item', keys:['item'], task:null}];
      const refreshed = rowTask(entry);
      answer({ok:false, code:409});
      pending.then(() => console.log(JSON.stringify({immediate, refreshed, refused:rowTask(entry)})));
    ''')
    assert value['immediate']['result'] == 'starting'
    assert value['refreshed'] == value['immediate']
    assert value['refused'] is None


def test_bulk_clear_endpoint_and_status_by_key_are_owner_only(host, monkeypatch):
    monkeypatch.setattr(tasks, 'clear_failed', lambda root: {'cleared': ['a' * 32]})
    monkeypatch.setattr(tasks, 'status', lambda root, key: {'id': key, 'result': 'starting'})
    cookie = f'co_rem={host.token}'
    for body in ({'action': 'clear_failed'}, {'action': 'status', 'key': 'item'}):
        payload = json.dumps(body).encode()
        assert call(host.routes, 'POST', '/rem/task', body=payload)[0] == 401
        status, _, result = call(host.routes, 'POST', '/rem/task', cookie=cookie, body=payload)
        assert status == 200
        assert json.loads(result) == ({'cleared': ['a' * 32]} if body['action'] == 'clear_failed' else
                                      {'id': tasks.identity('item'), 'result': 'starting'})


def test_running_words_include_elapsed_and_report_links_survive_markdown():
    import re
    from connectonion.rem.reader import TEMPLATE
    from tests.unit.test_rem_reader import _run_reader_js
    names = ['taskStatus', 'taskElapsed', 'taskStep', 'taskReportLinks', 'taskLinkPath', 'safeHref']
    code = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0) for name in names)
    value = _run_reader_js(code + '''
      const ACTIVE_TASK = ['starting', 'running'], AGENT_NAMES = {codex:'Codex', claude:'Claude'};
      const clockNow = () => Date.parse('2026-11-19T12:01:05Z');
      const words = taskStatus({result:'starting', agent:'codex', queued_at:'2026-11-19T12:00:00Z'});
      const links = taskReportLinks('[证据](work/evidence/合同.txt)\\n```\\n[x](code.txt)\\n```', 'aaa');
      console.log(JSON.stringify({words, links, href:safeHref('', '/rem/task-file?id=aaa&path=work%2Fevidence%2Fa.txt')}));
    ''')
    assert value['words'] == 'Codex is working · 1:05'
    assert '[证据](/rem/task-file?id=aaa&path=work%2Fevidence%2F' in value['links']
    assert '[x](code.txt)' in value['links']
    assert value['href']['href'].startswith('/rem/task-file?')


def test_preparing_same_reply_preserves_later_owner_edits(task_notebook, monkeypatch):
    receipt = finished(task_notebook, text='已核对合同。\n\n```reply\n原稿\n```')
    row = {'id': 'b' * 32, 'version': 'outlook:latest', 'provider': 'outlook', 'to': 'mara@example.test',
           'obligations': [{'record': receipt['record'], 'text': receipt['text']}], 'material': [{'source': 'outlook:latest'}]}
    monkeypatch.setattr(drafts, 'candidates', lambda *a, **kw: [row])
    tasks.prepare_reply(task_notebook, receipt['id'])
    path = drafts.path(task_notebook, row['id'])
    write_json(path, {**read_json(path, {}), 'body': '主人修改过的回复'})
    assert tasks.prepare_reply(task_notebook, receipt['id'])['body'] == '主人修改过的回复'


def test_handoff_prompt_requires_named_tab_on_every_browser_command_and_cleanup(task_notebook):
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tab = 'rem-' + receipt['id']
    prompt = tasks._prompt(receipt)
    assert f'co browser tab open {tab}' in prompt
    assert f'-t {tab} on every browser command' in prompt
    assert f'co browser tab close {tab}' in prompt


@pytest.mark.parametrize('agent', ['codex', 'claude'])
def test_successful_handoff_outside_today_queue_keeps_its_running_receipt(agent):
    import re
    from connectonion.rem.reader import TEMPLATE
    from tests.unit.test_rem_reader import _run_reader_js
    names = ['todayRow', 'obligationKey', 'rowTask', 'keepTask', 'handOver', 'handRefusal', 'clockNow', 'refreshHandoff',
             'taskStatus', 'taskElapsed', 'taskStep']
    code = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0) for name in names)
    value = _run_reader_js(code + '''
      const REM = {today_queue: []}, HAND_FAILED = new Map(), PENDING_HANDOFFS = new Map();
      const AGENT_NAMES = {codex:'Codex', claude:'Claude'}, ACTIVE_TASK = ['starting', 'running'];
      const doneKey = e => e.key, railActive = () => 'waiting';
      const hostPost = async () => ({ok:true, id:'aaa', result:'starting', agent:CHOSEN});
      const entry = {key:'item'};
      handOver(entry, CHOSEN, () => {}, null, {}).then(() => console.log(JSON.stringify(rowTask(entry))));
    '''.replace('CHOSEN', json.dumps(agent)))
    assert value['id'] == 'aaa' and value['agent'] == agent and value['result'] == 'starting'


def test_retry_keeps_git_work_reviewable_and_uses_a_new_branch(task_notebook, tmp_path, monkeypatch):
    from tests.unit.test_rem_tasks import _git, _link_project, _repository
    repo = _repository(tmp_path / 'project')
    _link_project(task_notebook, repo)
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    folder = Path(receipt['receipt']).parent
    work = tasks.workspace(task_notebook, receipt, folder)
    (work / 'uncommitted.txt').write_text('review me')
    receipt.update(result='failed', cwd=str(work))
    write_json(folder / 'receipt.json', receipt)
    monkeypatch.setattr(tasks, 'start', lambda root, key, agent=None: tasks.receipt_for(root, receipt['key']))
    fresh = tasks.retry(task_notebook, receipt['id'])
    archive = next(folder.parent.glob('history/*/work'))
    assert (archive / 'uncommitted.txt').read_text() == 'review me'
    assert _git(archive, 'branch', '--show-current') == 'rem/task-' + receipt['id']
    new_work = tasks.workspace(task_notebook, fresh, folder)
    assert _git(new_work, 'branch', '--show-current') == 'rem/task-' + receipt['id'] + '-1'
    assert not (new_work / 'uncommitted.txt').exists()
