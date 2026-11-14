"""Sparse organisation records and long summaries, without owner notebook data."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_org_table_browser import _names, _open, browser  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get('CO_REM_BROWSER_TEST') != '1',
                              reason='opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome')


def test_long_org_summary_is_two_lines_and_preserves_full_text(browser, tmp_path, monkeypatch):
    page = _open(browser, tmp_path, monkeypatch, 1440)
    row = page.locator('.org-table tbody tr').filter(has_text='Cedar Works')
    summary = ('Builds instruments for field research and supports independent laboratories. ' * 8)[:400]
    page.evaluate('''summary => {
      const r = byPath('orgs/cedar.md');
      r.kind = '';
      r.text = '# Cedar Works\\n\\n' + summary + '\\n\\n## Facts\\n- What they do: ' + summary;
      r.facts['What they do'] = [{value:summary}];
      KNOWN.clear(); FACTS.clear(); render();
    }''', summary, isolated_context=False)
    cell = row.locator('.c-summary .clamp')
    assert cell.get_attribute('title') == summary
    assert row.bounding_box()['height'] <= 88, 'Two summary lines, logo/unit caption and cell padding must fit within 88px'
    assert cell.evaluate('e => e.getBoundingClientRect().height <= 2 * parseFloat(getComputedStyle(e).lineHeight) + 1')
    assert page.locator('.people-scroll').evaluate('e => e.scrollWidth <= e.clientWidth + 1')
    row.locator('.c-name a').click()
    assert summary in page.locator('.ov-opening').inner_text()


@pytest.mark.parametrize('language,placeholder', [('en', 'Unknown — not investigated yet.'),
                                                 ('zh', '未知 — 尚未调查。')])
@pytest.mark.parametrize('width', [1440, 390])
def test_mapped_org_shows_known_people_link_only_connections_and_no_empty_facts(
        browser, tmp_path, monkeypatch, language, placeholder, width):
    page = _open(browser, tmp_path, monkeypatch, width)
    page.evaluate('''({language,placeholder}) => {
      for (const path of ['orgs/cedar.md','orgs/team.md']) {
        const r = byPath(path);
        r.kind = '';
        r.text = '# ' + r.title + '\\n\\n' + placeholder + '\\n\\n## Facts\\n- Website: Unknown\\n- First contact: 2024-01-01';
        r.facts = {};
      }
      byPath('orgs/cedar.md').organisations = ['orgs/team.md'];
      byPath('people/fern.md').text = '# Fern Vale\\n\\n## Facts\\n- First contact: 2024-01-01';
      setInterfaceLanguage(language); KNOWN.clear(); FACTS.clear(); render();
    }''', {'language': language, 'placeholder': placeholder}, isolated_context=False)
    assert placeholder not in page.locator('.org-table').inner_text()
    assert page.locator('.org-table tbody .c-summary').first.inner_text() == '—'
    page.locator('.org-table .c-name a').filter(has_text='Cedar Works').click()
    opening = page.locator('.ov-opening').inner_text()
    assert opening.startswith('你认识这里的 1 个人。' if language == 'zh' else 'You know 1 person here.')
    assert 'Fern Vale' in opening and '2024' in opening
    assert placeholder not in page.locator('.ov-page').inner_text()
    assert page.locator('.ov-connections p').all_inner_texts() == ['Field team']
    assert page.locator('.ov-connections p a').get_attribute('href')
    assert page.locator('.ov-about dt').count() == 0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('stored', [False, True], ids=['page-en', 'cached-zh'])
@pytest.mark.parametrize('source', ['lead', 'who', 'relationship', 'what', 'to-you', 'model-to-you', 'model-what'])
def test_org_placeholder_paths_show_dash_in_source_and_cached_translation(
        browser, tmp_path, monkeypatch, width, stored, source):
    page = _open(browser, tmp_path, monkeypatch, width)
    page.evaluate(r'''({stored,source}) => {
      const placeholder = stored ? 'Unknown — 尚未调查' : 'Unknown — not investigated yet.';
      const sections = {who:'Who they are', relationship:'Our relationship'};
      const fields = {what:'What they do', 'to-you':'To you'};
      for (const path of ['orgs/cedar.md','orgs/team.md']) {
        const r = byPath(path);
        delete r.original; delete r.shown; delete r.readLanguage;
        r.kind = ''; r.facts = {}; r.to_you = ''; r.translations = {};
        const body = source === 'lead' ? placeholder
          : sections[source] ? '## ' + sections[source] + '\n- ' + placeholder
          : fields[source] ? '## Facts\n- ' + fields[source] + ': ' + placeholder : '';
        const text = '# ' + r.title + '\n\n' + body;
        r.text = stored ? '# ' + r.title + '\n\nUnknown — not investigated yet.' : text;
        if (stored) r.translations.zh = text;
        if (source === 'model-to-you') r.to_you = placeholder;
        if (source === 'model-what') r.facts['What they do'] = [{value:placeholder}];
      }
      byPath('orgs/cedar.md').organisations = ['orgs/team.md'];
      KNOWN.clear(); FACTS.clear(); PARSED_FACTS.clear(); setInterfaceLanguage(stored ? 'zh' : 'en'); render();
    }''', {'stored': stored, 'source': source}, isolated_context=False)
    for name in ['Cedar Works', 'Field team']:
        row = page.locator('.org-table tbody tr').filter(has_text=name)
        assert row.locator('.c-summary').inner_text() == '—'
        assert row.locator('.c-summary [title]').count() == 0
    page.locator('.org-table .c-name a').filter(has_text='Cedar Works').click()
    assert page.locator('.ov-opening').inner_text().startswith('你认识这里的 1 个人。' if stored else 'You know 1 person here.')
    assert page.locator('.ov-connections p').all_inner_texts() == ['Field team']
    # Fern's business email still supplies a known website; only unknown/empty facts disappear.
    assert page.locator('.ov-about dt').all_inner_texts() == ['网站' if stored else 'Website']
    assert page.locator('.ov-about dd').all_inner_texts() == ['cedar.example']
    assert page.locator('.ov-about dd a').get_attribute('href') == 'https://cedar.example'
    assert '尚未调查' not in page.locator('.ov-page').inner_text()
    assert 'not investigated yet' not in page.locator('.ov-page').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('suffix', ['（邮件签名）。', ' (mail footer)'], ids=['free-text', 'qualifier'])
def test_long_org_location_is_two_lines_with_full_title_and_page_text(
        browser, tmp_path, monkeypatch, width, suffix):
    page = _open(browser, tmp_path, monkeypatch, width)
    location = '47 Lantern Avenue, Suite 820, Port Alder, OR 97000, Fictionland' + suffix
    page.evaluate(r'''location => {
      const r = byPath('orgs/cedar.md');
      r.text = '# Cedar Works\n\nBuilds instruments.\n\n## Facts\n- Location: ' + location;
      r.facts = {};
      KNOWN.clear(); FACTS.clear(); PARSED_FACTS.clear(); setInterfaceLanguage('zh'); render();
    }''', location, isolated_context=False)
    row = page.locator('.org-table tbody tr').filter(has_text='Cedar Works')
    cell = row.locator('.c-location .clamp')
    assert cell.inner_text() == location
    assert cell.get_attribute('title') == location
    if width == 1440:
        assert cell.evaluate('e => getComputedStyle(e).webkitLineClamp') == '2'
        assert cell.evaluate('e => e.getBoundingClientRect().height <= 2 * parseFloat(getComputedStyle(e).lineHeight) + 1')
        assert row.bounding_box()['height'] <= 88
        assert page.locator('.people-scroll').evaluate('e => e.scrollWidth <= e.clientWidth + 1')
    row.locator('.c-name a').click()
    assert page.locator('.ov-crumb').inner_text().endswith('公司')
    assert location in page.locator('.ov-about').inner_text()
    assert page.locator('.ov-about dt').all_inner_texts() == ['所在', '网站']
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_zero_org_and_unit_activity_is_dash_and_sorts_last(browser, tmp_path, monkeypatch):
    page = _open(browser, tmp_path, monkeypatch, 1440)
    page.evaluate('''() => {
      const r = byPath('people/fern.md');
      r.index.relationship.messages_90d = 0;
      r.index.relationship.weekly_messages = Array(52).fill(0);
      render();
    }''', isolated_context=False)
    for name in ['Cedar Works', 'Field team', 'Ash']:
        assert page.locator('.org-table tbody tr').filter(has_text=name).locator('.c-activity').inner_text() == '—'
    for _ in range(2):
        page.locator('.org-table th.c-activity button').click()
        assert _names(page)[0] == 'Elm Desk'
        assert '0 messages' not in page.locator('.org-table').inner_text()


@pytest.mark.parametrize('language,label', [('en', 'Unclassified'), ('zh', '未分类')])
@pytest.mark.parametrize('width', [1440, 390])
def test_unclassified_filter_keeps_blank_kind_and_survives_render(
        browser, tmp_path, monkeypatch, language, label, width):
    page = _open(browser, tmp_path, monkeypatch, width)
    page.evaluate('''language => {
      delete byPath('orgs/team.md').unit_kind; delete byPath('orgs/team.md').kind;
      setInterfaceLanguage(language);
    }''', language, isolated_context=False)
    page.locator('.org-kind-filters').get_by_role('button', name=label, exact=True).click()
    assert set(_names(page)) == {'Field team', 'Ash'}
    assert page.locator('.org-layout-switch button[data-mode=flat]').get_attribute('aria-pressed') == 'true'
    assert page.locator('.org-table tbody .c-kind').all_inner_texts() == ['—', '—']
    assert page.locator('.org-unit-path').inner_text() == 'Cedar Works › Field team'
    page.evaluate('render()', isolated_context=False)
    assert set(_names(page)) == {'Field team', 'Ash'}
    assert page.locator('.org-kind-filters').get_by_role('button', name=label, exact=True).get_attribute('aria-pressed') == 'true'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
