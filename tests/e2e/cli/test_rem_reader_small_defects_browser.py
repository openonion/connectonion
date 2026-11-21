"""Projects and Today tell the truth at desktop and phone sizes (#3042, #2947)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_projects_board_browser import _open, reader  # noqa: E402,F401
from test_rem_today_fuse_browser import today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get('CO_REM_BROWSER_TEST') != '1',
                                reason='opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome')


def test_phone_project_board_switch_is_one_unwrapped_scrollable_row(reader):
    page = _open(reader, '#c=projects', 390)
    page.evaluate("setInterfaceLanguage('zh')", isolated_context=False)
    segments = page.locator('.pd-asks a')
    assert segments.count() == 4
    measurements = segments.evaluate_all('''nodes => nodes.map(node => {
      const range = document.createRange(); range.selectNodeContents(node);
      return {top: node.getBoundingClientRect().top, lines: range.getClientRects().length};
    })''')
    assert all(item['lines'] == 1 for item in measurements), measurements
    assert max(item['top'] for item in measurements) - min(item['top'] for item in measurements) <= 1
    segments.last.scroll_into_view_if_needed()
    segments.last.click()
    assert page.locator('.pd-board').get_attribute('data-ask') == 'same'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1440, 390])
def test_today_leads_with_owner_debt_and_uses_only_its_overdue_days(today, width):
    page, _, _ = today
    page.set_viewport_size({'width': width, 'height': 900 if width == 1440 else 844})
    page.evaluate(r'''async () => {
      const r = byPath('people/mara-ostrowski.md');
      r.original = undefined;
      r.text = '# Mara Ostrowski\n\n## Facts\n- Role: Designer.\n\n## Open threads\n'
        + '- The user asked Mara to arrange a call; due 2026-09-16.\n'
        + '- Mara asked the user to review the proposal; due 2026-09-29.\n';
      const other = {...r, path: 'people/fern.md', title: 'Fern Vale',
        text: '# Fern Vale\n\n## Open threads\n- The user asked Fern to send a contract; due 2026-09-15.\n'};
      REM.records = [r, other]; REM.drafts = []; REM.threads = {}; REM.live = true;
      KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); setInterfaceLanguage('zh');
    }''', isolated_context=False)
    card = page.locator('.today-brief .qcard')
    assert card.count() == 1
    assert 'review the proposal' in card.locator('.qitem .words').first.inner_text()
    assert 'arrange a call' not in card.inner_text()
    assert '2' in card.locator('.qage.late').inner_text()
    assert '15' not in card.locator('.qhead').inner_text()
    assert page.locator('.deal .dd').inner_text() == '2 天'
    assert page.locator('.night-card .count').inner_text() == '1'
    assert card.locator('.handoff-line button').all_inner_texts()[:5] == [
        '标为完成', '暂不处理', '忽略', '交给 Codex', '交给 Claude']
    # Their late task remains available in Waiting on others, with its true direction.
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    assert 'arrange a call' in page.locator('#main').inner_text()
