"""The main organisation table exposes the notebook's hierarchy at first paint (#3037)."""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_reader_design_browser import org_reader  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                              reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _open(org_reader, width=1440):
    page = org_reader(width, language="zh")
    page.evaluate("location.hash = 'c=orgs'", isolated_context=False)
    page.locator('.org-table tbody tr').first.wait_for()
    return page


def _row(page, name):
    return page.locator('.org-table tbody tr').filter(has=page.locator('.c-name a').filter(has_text=re.compile('^' + re.escape(name) + '$')))


@pytest.mark.parametrize('width', [1440, 390])
def test_structure_is_expanded_at_first_paint_to_every_depth(org_reader, width):
    page = _open(org_reader, width)
    root = _row(page, 'Fernhill University')
    assert root.locator('.org-disclosure').inner_text() == '▾'
    assert root.locator('.org-unit-summary').inner_text() == '3 个下属单位 · 12 人'
    assert page.evaluate("orgMembers(byPath('orgs/fernhill-university.md')).length", isolated_context=False) == 12
    expected = page.evaluate("""() => {
      const visit = (r, depth) => [{name:r.title, depth}, ...(r.children || []).flatMap(p => visit(byPath(p), depth+1))];
      return visit(byPath('orgs/fernhill-university.md'), 0);
    }""", isolated_context=False)
    names = page.locator('.org-table tbody .c-name a').all_inner_texts()
    positions = {name: names.index(name) for name in [r['name'] for r in expected]}
    root_x = root.locator('.c-name a').bounding_box()['x']
    for unit in expected:
        row = _row(page, unit['name'])
        assert row.locator('td').count() == 8
        assert row.locator('.org-table-name').evaluate('e => parseInt(e.style.paddingLeft)') == unit['depth'] * 18
        assert abs(row.locator('.c-name a').bounding_box()['x'] - root_x - unit['depth'] * 18) < 1
        if unit['depth']:
            assert row.locator('.org-tree-guide').count() == unit['depth']
            assert row.locator('.org-tree-guide').first.evaluate("e => getComputedStyle(e).borderLeftWidth") == '1px'
    # The entire branch is contiguous; no independent organisation interrupts it.
    assert sorted(positions.values()) == list(range(positions['Fernhill University'], positions['Fernhill University'] + len(expected)))
    assert page.locator('.org-layout-switch').get_by_role('button', name='按结构', exact=True).get_attribute('aria-pressed') == 'true'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_collapse_is_remembered_per_organisation_after_reload(org_reader):
    page = _open(org_reader)
    root = _row(page, 'Fernhill University')
    root.locator('.org-disclosure').click()
    assert _row(page, 'Fieldwork studio').count() == 0
    page.reload()
    page.locator('.org-table tbody tr').first.wait_for()
    assert root.locator('.org-disclosure').inner_text() == '▸'
    assert _row(page, 'Fieldwork studio').count() == 0
    root.locator('.org-disclosure').click()
    assert _row(page, 'Heron squad').count() == 1
    _row(page, 'Fieldwork studio').locator('.org-disclosure').click()
    page.reload()
    page.locator('.org-table tbody tr').first.wait_for()
    assert root.locator('.org-disclosure').inner_text() == '▾'
    assert _row(page, 'Fieldwork studio').locator('.org-disclosure').inner_text() == '▸'
    assert _row(page, 'Heron squad').count() == 0


@pytest.mark.parametrize('trigger', ['last', 'kind', 'switch', 'phone-sort'])
def test_sort_and_kind_filter_flatten_with_context_and_structure_can_return(org_reader, trigger):
    page = _open(org_reader, 390 if trigger == 'phone-sort' else 1440)
    if trigger == 'last':
        page.locator('.org-table th.c-last button').click()
    elif trigger == 'phone-sort':
        page.locator('.people-sort').select_option('last')
    elif trigger == 'kind':
        page.locator('.org-kind-filters').get_by_role('button', name='团队', exact=True).click()
    else:
        page.locator('.org-layout-switch').get_by_role('button', name='平铺', exact=True).click()
    assert page.locator('.org-layout-switch').get_by_role('button', name='平铺', exact=True).get_attribute('aria-pressed') == 'true'
    heron = _row(page, 'Heron squad')
    assert heron.locator('.org-unit-path').inner_text() == 'Fernhill University › Fieldwork studio › Heron squad'
    assert heron.locator('.org-table-name').evaluate('e => parseInt(e.style.paddingLeft)') == 0
    assert page.locator('.org-disclosure').count() == 0
    if trigger == 'kind':
        assert page.locator('.org-table tbody tr').count() == 6
        assert _row(page, 'Fernhill University').count() == 0
    page.locator('.org-layout-switch').get_by_role('button', name='按结构', exact=True).click()
    assert _row(page, 'Fernhill University').locator('.org-disclosure').inner_text() == '▾'
    assert heron.locator('.org-unit-path').count() == 0
    assert heron.locator('.org-table-name').evaluate('e => parseInt(e.style.paddingLeft)') == 36
