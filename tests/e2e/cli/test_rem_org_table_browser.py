"""The organisation directory shares People's sortable table, chooser and phone cards."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from test_rem_people_table_browser import browser, _reader_html  # noqa: F401

pytestmark = pytest.mark.skipif(os.environ.get('CO_REM_BROWSER_TEST') != '1',
                                reason='opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome')

SETUP = r'''() => {
 const fact = value => [{value, citations:[], qualifier:''}];
 const records = [
  {path:'orgs/cedar.md',title:'Cedar Works',category:'orgs',kind:'company',people:['people/fern.md'],children:['orgs/team.md'],facts:{Website:fact('https://cedar.example'), Location:fact('Harbour'), 'What they do':fact('Builds instruments'), 'First contact':fact('2024-01-01'), 'Legal entity':fact('Cedar Works Ltd')},logo:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG1cAAAAASUVORK5CYII='},
  {path:'orgs/team.md',title:'Field team',category:'orgs',unit_kind:'team',kind:'team',parent:'orgs/cedar.md',people:['people/fern.md'],facts:{}},
  {path:'orgs/elm.md',title:'Elm Desk',category:'orgs',kind:'service',people:['people/elm.md'],facts:{}},
  {path:'orgs/ash.md',title:'Ash',category:'orgs',people:[],facts:{}},
  {path:'people/fern.md',title:'Fern Vale',category:'people',text:'# Fern Vale\n\n## Facts\n- Email: fern@cedar.example\n- First contact: 2024-01-01\n- Last contact: 2026-09-30', index:{relationship:{messages_90d:9,last_mail:'2026-09-30',weekly_messages:Array(52).fill(2)}}},
  {path:'people/elm.md',title:'Elm Reed',category:'people',text:'# Elm Reed\n\n## Facts\n- Email: elm@elm.example\n- Last contact: 2026-09-01',index:{relationship:{messages_90d:3,last_mail:'2026-09-01',weekly_messages:Array(52).fill(1)}}}
 ];
 REM.records.splice(0, REM.records.length, ...records.map(r=>({text:'# '+r.title+'\n\n## Facts\n- Last contact: Unknown',...r})));
 FACTS.clear(); render();
}'''


def _open(browser, tmp_path, monkeypatch, width):
    page = browser.new_page(viewport={'width':width, 'height':1000 if width > 500 else 844})
    page.route('http*://**/*', lambda route: route.abort())
    page.goto(_reader_html(tmp_path, monkeypatch) + '#c=orgs')
    page.evaluate(SETUP, isolated_context=False)
    page.locator('.org-table tbody tr').first.wait_for()
    return page


def _names(page):
    return page.locator('.org-table tbody td.c-name a').all_inner_texts()


@pytest.mark.parametrize('width', [1440, 390])
def test_org_table_columns_links_activity_and_calm_blanks(browser, tmp_path, monkeypatch, width):
    page = _open(browser, tmp_path, monkeypatch, width)
    assert page.locator('.org-table thead th').count() == 8
    assert page.locator('.org-table th.c-last').get_attribute('aria-sort') == 'descending'
    assert _names(page) == ['Cedar Works', 'Elm Desk', 'Ash']
    cedar = page.locator('.org-table tbody tr').filter(has_text='Cedar Works')
    assert cedar.locator('.c-people').inner_text() == '1'
    assert '9' in cedar.locator('.c-activity').inner_text()
    assert cedar.locator('.contact-spark rect').count() == 52
    assert cedar.locator('img').get_attribute('src').startswith('data:image/png;base64,')
    assert page.locator('.org-logo').count() == 3
    for a in page.locator('.c-website a').all():
        assert a.get_attribute('target') == '_blank' and a.get_attribute('rel') == 'noopener'
    assert 'Derived' in page.locator('tr').filter(has_text='Elm Desk').inner_text()
    assert page.locator('tr').filter(has_text='Ash').locator('.c-location').inner_text() == '—'
    text = page.locator('#main').inner_text().lower()
    for word in ('waiting','overdue','open items','who wrote last','reply speed','今天','等你'):
        assert word not in text
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    if width == 1440:
        assert page.locator('.people-scroll').evaluate('e => e.scrollWidth <= e.clientWidth + 1')
    else:
        assert page.locator('.people-sort').is_visible()
        assert page.locator('.org-kind-filters').is_visible()
        assert page.locator('.org-table thead').is_hidden()


def test_org_table_nesting_kind_filter_and_column_memory(browser, tmp_path, monkeypatch):
    page = _open(browser, tmp_path, monkeypatch, 1440)
    toggle = page.locator('.org-disclosure').first
    toggle.click()
    assert _names(page) == ['Cedar Works','Field team','Elm Desk','Ash']
    assert page.locator('tr').filter(has_text='Field team').locator('.org-table-name').evaluate('e => parseInt(e.style.paddingLeft)') == 18
    page.locator('.org-disclosure').first.click()
    assert 'Field team' not in _names(page)
    page.locator('.org-kind-filters button').filter(has_text='service').click()
    assert _names(page) == ['Elm Desk']
    page.locator('.org-kind-filters button').filter(has_text='All', exact=True).click()
    page.locator('.org-kind-filters button').filter(has_text='team', exact=True).click()
    assert _names(page) == ['Cedar Works', 'Field team']
    page.locator('.org-kind-filters button').filter(has_text='All', exact=True).click()
    page.locator('.org-disclosure').first.click()
    assert 'Field team' not in _names(page)
    page.locator('.people-columns-open').click()
    for key in ('first','legal','parent'):
        page.locator(f'.people-columns input[value={key}]').check()
    assert page.locator('.org-table thead th').count() == 11
    page.evaluate('async () => { orgTableColumns = peopleColumnKeys(await readerStorage("co-rem-org-columns"), ORG_COLUMNS); render(); }', isolated_context=False)
    assert page.locator('.org-table thead th').count() == 11
    assert page.evaluate("readerStorage('co-rem-people-columns')", isolated_context=False) is None


def test_org_table_every_header_sorts_both_ways_blank_last(browser, tmp_path, monkeypatch):
    page = _open(browser, tmp_path, monkeypatch, 1440)
    page.evaluate("() => { orgTableColumns = peopleColumnKeys('more', ORG_COLUMNS); render(); }", isolated_context=False)
    for key in ('name','kind','summary','website','location','people','activity','last','first','legal','parent'):
        for _ in range(2):
            page.locator(f'.org-table th.c-{key} button').click()
            assert page.evaluate(r'''key => {
              const col = ORG_COLUMNS.find(c=>c.key===key);
              const rows = orgRows().map(orgTableRow);
              const values = [...document.querySelectorAll('.org-table tbody tr')].map(tr=>col.sort(rows.find(d=>href(d.r)===tr.dataset.href)));
              const desc = document.querySelector('.org-table th.c-'+key).getAttribute('aria-sort')==='descending';
              const blank = values.indexOf(null);
              if(blank>=0 && values.slice(blank).some(v=>v!==null)) return false;
              const filled=values.filter(v=>v!==null), collator=new Intl.Collator('en',{numeric:true,sensitivity:'base'});
              return filled.every((v,i)=>!i || (typeof v==='string' ? collator.compare(filled[i-1],v) : filled[i-1]-v)*(desc?-1:1)<=0);
            }''', key, isolated_context=False)
