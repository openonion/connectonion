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
                       for name in page.locator('.org-kind-filters button').all_inner_texts())


@pytest.mark.parametrize('width', [1440, 390])
def test_org_list_opens_in_recent_contact_order(org_reader, width):
    page = org_reader(width, language='en')
    page.evaluate("location.hash = 'c=orgs'", isolated_context=False)
    page.locator('.ov-list .org-table-row').first.wait_for()
    page.locator('.ov-more').evaluate_all('buttons => buttons.forEach(b => b.click())')
    actual = page.locator('.org-table-row').evaluate_all('rows => rows.map(r => r.dataset.href)')
    expected = page.evaluate("""orgRows().map(orgTableRow).sort((a,b) => b.last.localeCompare(a.last) || a.r.title.localeCompare(b.r.title)).map(o => href(o.r))""", isolated_context=False)
    assert actual == expected


@pytest.mark.parametrize('width', [1440, 390])
def test_org_page_blocks_have_no_reserved_empty_band_and_breadcrumb_leads(org_reader, width):
    page = org_reader(width)
    blocks = page.locator('.ov-over, .ov-say, .ov-org-tree, .ov-milestones, .ov-connections, .ov-coda')
    boxes = blocks.evaluate_all("nodes => nodes.map(n => {const r=n.getBoundingClientRect(); return {top:r.top,bottom:r.bottom};})")
    assert len(boxes) >= 5
    assert all(0 <= b['top'] - a['bottom'] <= 120 for a, b in zip(boxes, boxes[1:])), boxes
    assert page.locator('.ov-stage > :first-child').get_attribute('class') == 'ov-over'



@pytest.mark.parametrize('width', [1440, 390])
def test_org_tree_is_the_only_people_directory_and_local_graph_is_absent(org_reader, width):
    page = org_reader(width)
    assert page.locator('.ov-key, .ov-people, #main .gx-attach').count() == 0
    links = page.locator('.ov-org-tree .ov-trow[data-kind=person] a')
    first_screen = links.evaluate_all("""links => links.filter(a => a.checkVisibility() &&
      a.getBoundingClientRect().top < innerHeight).map(a => a.getAttribute('href'))""")
    assert first_screen
    assert len(first_screen) == len(set(first_screen)), first_screen
    # A tree contact is not repeated elsewhere above the fold (historical prose is not a directory).
    for href in first_screen:
        roster = page.locator(f'.ov-page a[href="{href}"]')
        visible = roster.evaluate_all("""links => links.filter(a => a.checkVisibility() && a.getBoundingClientRect().top < innerHeight &&
          !a.closest('.ov-milestones')).length""")
        assert visible == 1, href


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('language', ['zh', 'en'])
def test_org_article_says_facts_in_one_reading_column(org_reader, width, language):
    page = org_reader(width, language=language)
    article = page.locator('.ov-page')
    assert article.locator('.ov-chip, .ov-dot, .ov-mk, .ov-tbar, .ov-tc, .ov-time, svg, .updated-label, .fresh-label, .fresh-dot, .ov-stats, .ov-sq, .pill, .badge, .chip, .ov-card, .ov-unsure-d, .ov-cool, .ov-two').count() == 0
    opening = article.locator('.ov-opening').inner_text()
    facts = page.evaluate("""() => ({summary: known(orgCurrent.r).summary, n: orgCurrent.people.length,
      first: calendarDate(orgCurrent.events[0].day)})""", isolated_context=False)
    assert facts['summary'] in opening
    assert str(facts['n']) in opening and facts['first'] in opening
    bounds = article.bounding_box()
    assert bounds['width'] <= 760
    aligned = article.locator('.ov-say, .ov-org-tree, .ov-milestones, .ov-coda').evaluate_all(
        'nodes => nodes.map(n => n.getBoundingClientRect().left)')
    assert all(abs(left - bounds['x']) <= 1 for left in aligned), aligned
    assert article.locator('.ov-milestones time').count() == 4
    assert article.locator('.ov-milestones').inner_text().count('confirmed the final demo week') == 1
    assert article.locator('.ov-coda .ov-src').get_attribute('href').endswith('&h=full-memory-heading')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#main').inner_text().count('完整记忆与来源' if language == 'zh' else 'Full memory and sources') == 1
    article.locator('.ov-coda .ov-src').click()
    assert page.locator('details.deep-note').evaluate('node => node.open')
