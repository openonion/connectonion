"""#3147 hand-offs at desktop/phone widths; invented notebook and faked Host/agents."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get('CO_REM_BROWSER_TEST') != '1', reason='browser opt in')
SHOTS = Path('/private/tmp/claude-501/-Users-changxing-projects-connectonion/5e15bb44-2240-42c5-8595-673a9dbd14c9/scratchpad/pr-shots/rc30')


def setup_row(page, width):
    page.set_viewport_size({'width': width, 'height': 900 if width == 1440 else 844})
    page.evaluate('''() => {
      setInterfaceLanguage('zh'); REM.live = true;
      window.testEntry = threadEntries().find(e => todayRow(e));
      const row = todayRow(testEntry); row.outcome = null; row.task = null;
      document.getElementById('main').replaceChildren(handOff(testEntry));
    }''', isolated_context=False)


def screenshot(page, name, width):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f'handoff-{name}-{width}.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('.handoff :is(button, [role=status])').evaluate_all('nodes => nodes.every(n => parseFloat(getComputedStyle(n).fontSize) >= 13)')


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('agent', ['codex', 'claude'])
def test_click_is_optimistic_before_host_answer_and_survives_queue_refresh(today, width, agent):
    page, calls, answers = today
    setup_row(page, width)
    page.evaluate('''() => {
      window.realPost = hostPost;
      hostPost = (url, body) => body.action === 'run' ? new Promise(resolve => window.answerRun = resolve) : realPost(url, body);
    }''', isolated_context=False)
    page.locator(f'.handoff [data-agent={agent}]').click()
    name = 'Codex' if agent == 'codex' else 'Claude'
    page.get_by_role('status').filter(has_text=name + ' 正在做 · 0:00').wait_for(timeout=950)
    # A fresh snapshot while the Host still starts its worker used to erase the optimistic receipt.
    page.evaluate('''() => {
      REM.today_queue = REM.today_queue.map(r => ({...r, task: null, outcome: null}));
      document.getElementById('main').replaceChildren(handOff(testEntry));
    }''', isolated_context=False)
    assert name + ' 正在做' in page.locator('.handoff').inner_text()
    screenshot(page, 'running-' + agent, width)
    page.evaluate('answerRun({ok:false, code:409})', isolated_context=False)
    page.locator('.handoff [data-agent=codex]').wait_for()


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('reply', [True, False])
def test_finished_has_summary_one_primary_and_report_in_side_card(today, width, reply):
    page, calls, answers = today
    setup_row(page, width)
    task = {'id': 'a' * 32, 'agent': 'codex', 'result': 'completed', 'summary': '已核对合同，等你确认。',
            'reply': '你好，合同已收到。' if reply else '', 'has_output': True}
    answers['/rem/task'] = lambda body: (200, {'id': 'draft-one', 'status': 'prepared', 'body': '你好，合同已收到。', 'to': 'mara@example.test', 'provider': 'outlook', 'sources': [], 'subject': 'Re: 合同', 'from': 'owner@example.test'} if body.get('action') == 'prepare_reply'
        else {'text': '已核对合同，等你确认。\n\n[合同证据](work/evidence/contract.txt)\n\noutlook:message-one\n\n详细报告。'})
    page.evaluate('(task) => { keepTask(testEntry, task); document.getElementById("main").replaceChildren(handOff(testEntry)); }', task, isolated_context=False)
    assert task['summary'] in page.locator('.handoff').inner_text()
    action = page.get_by_role('button', name='用这个回复起草' if reply else '标为完成', exact=True)
    # With a reply to draft that is the one lead action; without one, the strip's own Mark done is the next step.
    assert action.is_visible() and page.locator('.handoff .strip-lead').count() == (1 if reply else 0)
    screenshot(page, 'finished-' + ('reply' if reply else 'done'), width)
    page.get_by_role('button', name='看结果', exact=True).click()
    panel = page.locator('#evidence-panel')
    panel.get_by_text('详细报告。', exact=True).wait_for()
    assert '详细报告。' not in page.locator('.handoff').inner_text()
    assert panel.get_by_role('link', name='合同证据').get_attribute('href').startswith('/rem/task-file?')
    page.route('**/rem/task-file?**', lambda route: route.fulfill(status=200, body='合同附件里的证据', content_type='text/plain'))
    panel.get_by_role('link', name='合同证据').click()
    panel.get_by_text('合同附件里的证据', exact=True).wait_for()
    panel.locator('.evidence-close').click()
    page.get_by_role('button', name='看结果', exact=True).click()
    # The report is fetched again on reopen; wait for it before counting what it carries.
    panel.get_by_text('详细报告。', exact=True).wait_for()
    chip = panel.locator('.task-source')
    assert chip.count() == 1
    page.evaluate("REM.source_context['outlook:message-one'] = {source:'outlook', excerpt:'合同原文', subject:'合同'}", isolated_context=False)
    chip.click()
    if not panel.get_by_text('合同原文', exact=True).is_visible():
        panel.get_by_role('button', name='显示已标记段落').click()
    assert '合同原文' in panel.inner_text()
    panel.locator('.evidence-close').click()
    if reply:
        action.click()
        page.wait_for_function("REM.drafts.some(d => d.id === 'draft-one')")
        assert any(body.get('action') == 'prepare_reply' for path, body in calls if path == '/rem/task')
    else:
        answers['/rem/thread'] = [(200, {'state': 'done'})]
        action.click()
        assert any(path == '/rem/thread' for path, body in calls)


@pytest.mark.parametrize('width', [1440, 390])
def test_old_failure_has_reason_retry_and_bulk_clear(today, width):
    page, calls, answers = today
    setup_row(page, width)
    task = {'id': 'a' * 32, 'agent': 'codex', 'result': 'failed', 'finished_at': '2026-11-09T12:00:00Z',
            'reason': 'codex app-server: initialize failed: Operation not permitted (os error 1)', 'has_output': False}
    page.evaluate('(task) => { keepTask(testEntry, task); document.getElementById("main").replaceChildren(handOff(testEntry), workStrip()); }', task, isolated_context=False)
    line = page.locator('.handoff')
    assert 'Codex 当时无法启动（已修复），可以重试' in line.inner_text()
    assert 'Operation not permitted' not in line.inner_text()
    assert line.get_by_role('button', name='看结果').count() == 0
    assert page.locator('#work-strip').count() == 1  # old failures remain reachable until cleared
    screenshot(page, 'failed', width)
    answers['/rem/task'] = [(200, {'id': task['id'], 'agent': 'codex', 'result': 'starting'})]
    line.get_by_role('button', name='重试', exact=True).click()
    page.get_by_role('status').filter(has_text='Codex 正在做').first.wait_for()
    assert calls[-1] == ('/rem/task', {'id': task['id'], 'action': 'retry'})


@pytest.mark.parametrize('width', [1440, 390])
def test_clear_failed_from_work_strip(today, width):
    page, calls, answers = today
    setup_row(page, width)
    page.evaluate('''() => {
      keepTask(testEntry, {id:'a'.repeat(32), agent:'codex', result:'failed', has_output:false});
      workOpen = true;
      document.getElementById('main').replaceChildren(handOff(testEntry), workStrip());
    }''', isolated_context=False)
    answers['/rem/task'] = [(200, {'cleared': ['a' * 32]})]
    page.locator('#work-strip').get_by_role('button', name='清除失败记录', exact=True).click()
    page.wait_for_function('rowTask(testEntry) === null')
    assert ('/rem/task', {'action': 'clear_failed'}) in calls  # the language line polls its own route meanwhile


@pytest.mark.parametrize('agent', ['codex', 'claude'])
def test_uncertain_response_does_not_undo_the_click(today, agent):
    page, calls, answers = today
    setup_row(page, 1440)
    answers['/rem/task'] = [(503, {}), (200, {'id': 'a' * 32, 'agent': agent, 'result': 'running'})]
    page.locator(f'.handoff [data-agent={agent}]').click()
    assert page.locator('.handoff [data-agent]').count() == 0
    page.wait_for_function("rowTask(testEntry)?.id === 'a'.repeat(32)")
    assert calls[-1] == ('/rem/task', {'action': 'status', 'key': page.evaluate('obligationKey(testEntry)', isolated_context=False)})


@pytest.mark.parametrize('summary, shown', [('Richard Lai — written feedback preparation', False), ('已核对合同，等你确认。', True)])
def test_a_finished_rows_title_reads_in_the_readers_language(today, summary, shown):
    """rc34 check: hand-offs made before the language rule left English summaries on the row ("Richard Lai — written
    feedback preparation"). In the zh reader the row keeps its own Chinese words; an English heading stays in the report."""
    page, calls, answers = today
    setup_row(page, 1440)
    page.evaluate('(task) => { keepTask(testEntry, task); document.getElementById("main").replaceChildren(handOff(testEntry)); }',
                  {'id': 'a' * 32, 'agent': 'codex', 'result': 'completed', 'summary': summary, 'reply': '', 'has_output': True},
                  isolated_context=False)
    status = page.locator('.handoff [role=status]').first.inner_text()
    assert 'Codex 做完了' in status
    assert (summary in status) == shown, status


def test_a_long_finished_line_wraps_inside_a_today_card_on_a_phone(today):
    """A finished hand-off's line is a sentence: on a 390px phone, inside a Today card, it wraps.

    Kept on one line (white-space: nowrap, meant for the buttons beside it) it widened Today to
    1174px, and a phone zoomed the whole page out to fit it."""
    page, calls, answers = today
    setup_row(page, 390)
    task = {'id': 'b' * 32, 'agent': 'codex', 'result': 'completed', 'has_output': True, 'reply': '',
            'summary': '已备妥案件的证据底稿、时间线和三份附件的核对清单，等你确认后再回复对方，并附上需要补充的材料说明。'}
    page.evaluate('''(task) => {
      keepTask(testEntry, task);
      const card = document.createElement('div'); card.className = 'qcard';
      const item = document.createElement('div'); item.className = 'qitem';
      item.append(handOff(testEntry)); card.append(item);
      document.getElementById('main').replaceChildren(card);
    }''', task, isolated_context=False)
    line = page.locator('.qcard .handed')
    line.wait_for()
    assert task['summary'][:10] in line.inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    box = line.bounding_box()
    assert box['x'] + box['width'] <= 390 + 1
    assert box['height'] > 30  # it wrapped onto more than one line


@pytest.mark.parametrize('size', [(1440, 900), (390, 844)])
def test_completed_codex_task_draft_drawer_opens_full_screen(today, size):
    page, calls, answers = today
    width, height = size
    page.set_viewport_size({'width': width, 'height': height})
    draft = {
        'id': 'draft-q3-receipts', 'status': 'prepared', 'provider': 'outlook', 'sources': [],
        'to': 'Inès Halvorsen <ines@example.test>', 'from': 'avery@example.test',
        'subject': 'Re: Q3 receipts',
        'body': 'Hi Inès,\n\nI checked the Q3 receipts and can send the complete set on Thursday.\n\nAvery',
    }
    task = {
        'id': 'a' * 32, 'agent': 'codex', 'result': 'completed', 'has_output': True,
        'summary': 'Checked the Q3 receipts and drafted a reply.', 'reply': draft['body'],
    }
    answers['/rem/task'] = [(200, draft)]
    page.evaluate("""task => {
      REM.live = true;
      const group = todayGroups(threadEntries().filter(entry => !isDone(entry)))[0];
      keepTask(group.entries[0], task);
      todayLead = group.r.path;
      setInterfaceLanguage('en');
    }""", task, isolated_context=False)

    page.locator('.qcard').get_by_role('button', name='Draft with this reply', exact=True).click()
    assert ('/rem/task', {'id': task['id'], 'action': 'prepare_reply'}) in calls
    panel = page.locator('#evidence-panel')
    panel.get_by_text('Reply draft prepared', exact=True).wait_for()
    assert panel.get_by_role('region', name='Reply draft').is_visible()
    actions = panel.locator('.mail-actions')
    write = actions.get_by_role('button', name='Write full screen', exact=True)
    assert write.is_visible()
    assert write.inner_text().strip() == 'Write full screen'
    assert actions.get_by_role('button', name='Send', exact=True).is_visible()
    assert actions.get_by_label('More', exact=True).is_visible()
    box = write.bounding_box()
    assert 0 <= box['x'] <= box['x'] + box['width'] <= width
    assert 0 <= box['y'] <= box['y'] + box['height'] <= height
    if width == 390:
        assert min(box['width'], box['height']) >= 44

    shots = os.environ.get('CO_REM_SHOTS')
    if shots:
        page.screenshot(path=str(Path(shots) / f'handoff-draft-drawer-{width}.png'))
    if width == 390:
        write.click()
    else:
        write.press('Enter')
    writer = page.locator('dialog.writer[open]')
    writer.wait_for()
    assert writer.get_by_role('textbox', name='Reply body').inner_text() == draft['body']
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    if shots:
        page.screenshot(path=str(Path(shots) / f'handoff-fullscreen-writer-{width}.png'))
    writer.get_by_role('button', name='Cancel' if width == 390 else 'Close', exact=True).click()
    writer.wait_for(state='hidden')
    assert write.is_visible()
    assert not any(path in ('/rem/draft', '/rem/approve') for path, _ in calls)
