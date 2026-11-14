"""#3036: organisation records, measured at desktop and phone widths."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_reader_design_browser import org_reader  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get('CO_REM_BROWSER_TEST') != '1',
                                reason='opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome')


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('language', ['zh', 'en'])
def test_untouched_org_list_and_page_have_no_task_projection(org_reader, width, language):
    page = org_reader(width, language=language)
    for selector in ('.ov-page', '.ov-list'):
        if selector == '.ov-list':
            page.evaluate("location.hash = 'c=orgs'", isolated_context=False)
            page.locator(selector).wait_for()
        text = page.locator('#main').inner_text().lower()
        for word in ('今天', '在等你', '等你', 'overdue', 'today', 'waiting on you'):
            assert word not in text, (selector, word, text)
        assert page.locator('.ov-today, .list-today, .ov-chip.late, .ov-grp').count() == 0
        assert not any('waiting' in name.lower() or '等你' in name
                       for name in page.locator('.ov-tabs button').all_inner_texts())


@pytest.mark.parametrize('width', [1440, 390])
def test_org_list_opens_in_recent_contact_order(org_reader, width):
    page = org_reader(width, language='en')
    page.evaluate("location.hash = 'c=orgs'", isolated_context=False)
    page.locator('.ov-list .ov-row').first.wait_for()
    page.locator('.ov-more').evaluate_all('buttons => buttons.forEach(b => b.click())')
    actual = page.locator('.ov-row').evaluate_all('rows => rows.map(r => r.getAttribute("href"))')
    expected = page.evaluate("""orgRows().sort((a,b) => b.last.localeCompare(a.last) || a.r.title.localeCompare(b.r.title)).map(o => href(o.r))""", isolated_context=False)
    assert actual == expected


@pytest.mark.parametrize('width', [1440, 390])
def test_org_page_blocks_have_no_reserved_empty_band_and_breadcrumb_leads(org_reader, width):
    page = org_reader(width)
    boxes = page.evaluate("""() => {
      const box = selector => { const b = document.querySelector(selector).getBoundingClientRect();
        return {top:b.top, bottom:b.bottom}; };
      return {over:box('.ov-over'), say:box('.ov-say'), tree:box('.ov-org-tree'),
        time:box('.ov-time'), stage:box('.ov-stage'), next:box('.ov-stage + *')};
    }""", isolated_context=False)
    assert boxes['over']['bottom'] <= boxes['say']['top'] + 1, boxes
    assert boxes['over']['bottom'] <= boxes['tree']['top'] + 1, boxes
    assert boxes['time']['top'] - max(boxes['say']['bottom'], boxes['tree']['bottom']) <= 120, boxes
    assert boxes['next']['top'] - boxes['stage']['bottom'] <= 120, boxes
    # Measure every consecutive record section too, not only the hero boundary.
    gaps = page.locator('.ov-col, .ov-one').evaluate_all("""cols => cols.flatMap(col =>
      [...col.children].slice(1).map((node, i) => node.getBoundingClientRect().top - col.children[i].getBoundingClientRect().bottom))""")
    assert all(gap <= 120 for gap in gaps), gaps
    if width == 390:
        assert page.locator('.ov-stage > :first-child').get_attribute('class') == 'ov-over'


@pytest.mark.parametrize('width', [1440, 390])
def test_org_tree_is_the_only_people_directory_and_local_graph_is_absent(org_reader, width):
    page = org_reader(width)
    assert page.locator('.ov-key, .ov-people, #main .gx-attach').count() == 0
    links = page.locator('.ov-org-tree .ov-trow:has(.ov-mk.person) a')
    first_screen = links.evaluate_all("""links => links.filter(a => a.checkVisibility() &&
      a.getBoundingClientRect().top < innerHeight).map(a => a.getAttribute('href'))""")
    assert first_screen
    assert len(first_screen) == len(set(first_screen)), first_screen
    # A tree contact is not repeated elsewhere above the fold (historical prose is not a directory).
    for href in first_screen:
        roster = page.locator(f'.ov-page a[href="{href}"]')
        visible = roster.evaluate_all("""links => links.filter(a => a.checkVisibility() && a.getBoundingClientRect().top < innerHeight &&
          !a.closest('.ov-tl')).length""")
        assert visible == 1, href
