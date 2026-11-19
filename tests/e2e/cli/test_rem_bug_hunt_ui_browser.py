"""The bug hunt's UI findings on rc30 (#3158, #3161, #3162, #3163), as checks that run on every build.

Found live on the owner's notebook, 2026-11-19: a filled 现在起草 on every row of 等你处理, rows of English quotes,
ISO dates and citation numbers, list tables at 11px, phone controls under 44px, and 372 graph records drawn nowhere.
The notebook here is the invented one in tests/fixtures/rem_reader_notebook.py.
"""

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

SHOTS = os.environ.get("REM_PR_SHOTS")
VISIBLE = """e => { const r = e.getBoundingClientRect(), c = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0 && c.visibility !== 'hidden' && c.display !== 'none' && c.opacity !== '0'; }"""


@pytest.fixture
def page_at(monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = Path(tempfile.mkdtemp()) / "rem"
    build(root, datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    path = Path(tempfile.mkdtemp()) / "reader.html"
    path.write_text(rem_reader.render(root, live=False, local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)

        def open_at(hash_, width=1440):
            phone = width < 500
            context = browser.new_context(viewport={"width": width, "height": 844 if phone else 900}, is_mobile=phone,
                                          has_touch=phone, locale="zh-CN", reduced_motion="reduce")
            context.route("http*://**/*", lambda route: route.abort())
            page = context.new_page()
            page.goto(path.as_uri() + ("#" + hash_ if hash_ else ""))
            page.locator("#main *").first.wait_for()
            page.wait_for_timeout(800)
            return page
        yield open_at
        browser.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_the_waiting_list_has_one_filled_action_and_rows_read_at_a_glance(page_at, width):
    """#3158: one primary per screen; dates in words; a long quote one click down; sources on hover."""
    page = page_at("view=open", width)
    filled = page.evaluate(f"""() => [...document.querySelectorAll('ul.threads .btn-act')].filter({VISIBLE})
      .filter(n => !n.classList.contains('act-quiet')).length""", isolated_context=False)
    assert filled <= 1, filled
    rows = page.locator("ul.threads .what").all_inner_texts()
    assert rows and not any(__import__("re").search(r"\b\d{4}-\d{2}-\d{2}\b", row) for row in rows), rows
    assert page.evaluate(f"""() => [...document.querySelectorAll('ul.threads .what .cite')].filter({VISIBLE}).length""",
                         isolated_context=False) == 0
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, f"waiting-{width}.png"))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_a_long_quote_in_a_row_folds_under_its_words(page_at):
    """#3158: the row leads with its own line; the quote is kept, one click down (原话)."""
    page = page_at("view=open")
    page.evaluate("""() => { const row = threadRow(byPath('people/mara-ostrowski.md'), { dir: 'mine', since: '2026-09-22',
        text: 'You owe Mara the usage export by 2026-10-09 — "Could you send the usage export before the renewal call next week?" [5]' }, true);
      row.id = 'quote-row'; document.querySelector('ul.threads').prepend(row); }""", isolated_context=False)
    row = page.locator("#quote-row")
    what = row.locator(".what").inner_text()
    assert "Could you send" not in what and "2026-10-09" not in what and "10月9日" in what
    fold = row.locator("details.row-quote")
    assert fold.locator("summary").inner_text() == "原话"
    fold.locator("summary").click()
    assert "Could you send the usage export" in fold.inner_text()


@pytest.mark.parametrize("hash_", ["c=people", "c=orgs", "c=skills"])
def test_list_tables_read_at_thirteen_pixels(page_at, hash_):
    """#3162: table body text and headers are at least 13px on the lists the owner reads."""
    page = page_at(hash_)
    small = page.evaluate(f"""() => [...document.querySelectorAll('#main table *')].filter({VISIBLE})
      .filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
      .filter(e => !e.closest('.ov-tile') && parseFloat(getComputedStyle(e).fontSize) < 13)
      .map(e => e.tagName + '.' + e.className)""", isolated_context=False)
    assert not small, small


@pytest.mark.parametrize("hash_", ["", "view=open", "r=people%2Fmara-ostrowski.md"])
def test_every_phone_control_is_a_44px_target(page_at, hash_):
    """#3163: on a phone each control is at least 44px; words inside a sentence and source marks are exempt."""
    page = page_at(hash_, 390)
    small = page.evaluate(f"""() => {{ const inline = e => e.matches('a.cite, .cite *') || (getComputedStyle(e).display === 'inline'
        && e.tagName === 'A' && e.closest('p, .what, .x, li > span, .note, .lead'));
      return [...document.querySelectorAll('#main button, #main a[href], #main summary, #main [role=button], #main input, #main select')]
        .filter({VISIBLE}).filter(e => !inline(e)).filter(e => {{ const r = e.getBoundingClientRect(); return r.height < 44 || r.width < 44; }})
        .map(e => e.tagName + '.' + e.className + ' ' + (e.textContent || '').trim().slice(0, 12)); }}""", isolated_context=False)
    assert not small, small
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, f"phone-{hash_.split('%2F')[-1] or 'today'}-390.png".replace("=", "-")))


def test_the_graph_lists_what_it_does_not_draw_and_says_it_in_words(page_at):
    """#3161: records linked to nothing are one click away as a list to open, not dots; titles read in the UI language."""
    page = page_at("view=graph")
    page.evaluate("""() => { const r = REM.records.find(r => r.category === 'decisions');
      REM.graph = { ...REM.graph, nodes: [...REM.graph.nodes, { id: 'decisions/lonely.md', kind: 'decision' }] };
      REM.records.push({ path: 'decisions/lonely.md', title: 'Lonely decision', category: 'decisions', text: '# Lonely decision\\n',
        translations: { zh: '# 孤立的决定\\n' } });
      GRAPH = null; render(); }""", isolated_context=False)
    button = page.locator(".gx-unlinked")
    assert button.is_visible()
    button.click()
    sheet = page.locator("dialog.list-sheet")
    sheet.wait_for()
    assert "孤立的决定" in sheet.inner_text()  # the translated heading, not the English title
    box = sheet.bounding_box()
    points = [[box["x"] + 16 + (box["width"] - 32) * i / 4, box["y"] + 16 + (box["height"] - 32) * j / 4] for i in range(5) for j in range(5)]
    assert page.evaluate("""([sel, points]) => { const n = document.querySelector(sel);
      return points.filter(([x, y]) => y < innerHeight && x < innerWidth).every(([x, y]) => n.contains(document.elementFromPoint(x, y))); }""",
                         ["dialog.list-sheet", points], isolated_context=False)
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, "graph-unlinked-1440.png"))


def test_the_updating_line_leaves_when_no_newer_page_is_coming(page_at):
    """Mac review of rc30: "正在更新…" stayed bottom-right on a current page. It stays only while a build runs."""
    page = page_at("")
    page.evaluate("""() => document.body.append(Object.assign(document.createElement('p'), { id: 'rem-updating', textContent: '正在更新…' }))""",
                  isolated_context=False)
    page.evaluate("() => clearUpdating({ as_of: REM.as_of, building: true })", isolated_context=False)
    assert page.locator("#rem-updating").count() == 1  # a newer page is still being built
    page.evaluate("() => clearUpdating({ as_of: REM.as_of, building: false })", isolated_context=False)
    assert page.locator("#rem-updating").count() == 0


@pytest.mark.parametrize("width", [1440, 390])
def test_last_night_is_said_in_words_and_counts_not_a_chart(page_at, width):
    """Mac review of rc30: the night chart (flat lines, spikes, 'RU +4') could not be read."""
    page = page_at("", width)
    card = page.locator(".night-card")
    assert card.locator(".hyp, .hyp-wrap, svg.hyp").count() == 0
    head = card.locator(".nh")
    if head.count():
        assert "昨夜" in head.inner_text() and any(word in head.inner_text() for word in ("读了", "写了", "起草了", "准备了", "没有新的事"))
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, f"today-night-{width}.png"))


def test_a_wrapped_dotted_row_never_starts_a_line_with_a_dot(page_at):
    """Mac review of rc30: '· 在 Codex 里接着做' began line 2. One rule for every dotted row."""
    page = page_at("view=open")
    page.evaluate("""() => { const words = ['标为完成', '暂不处理', '忽略', '在 Codex 里接着做', '看结果', '从 Codex 撤回交办', '更多背景'];
      const row = Object.assign(document.createElement('div'), { className: 'handoff-line', id: 'dots' });
      row.style.cssText = 'display:flex;flex-wrap:wrap;width:260px;gap:0 6px';
      row.append(...dotted(words.map(w => Object.assign(document.createElement('button'), { className: 'btn-quiet', textContent: w }))));
      document.getElementById('main').prepend(row); tidyDots(); }""", isolated_context=False)
    orphans = page.evaluate("""() => { const kids = [...document.querySelectorAll('#dots > *')];
      return kids.filter((n, i) => n.classList.contains('sep') && getComputedStyle(n).visibility !== 'hidden'
        && (i === 0 || n.getBoundingClientRect().top > kids[i - 1].getBoundingClientRect().bottom - 2
            || (kids[i + 1] && kids[i + 1].getBoundingClientRect().top >= n.getBoundingClientRect().bottom - 2))).length; }""", isolated_context=False)
    rows = page.evaluate("() => new Set([...document.querySelectorAll('#dots > button')].map(n => Math.round(n.getBoundingClientRect().top))).size",
                         isolated_context=False)
    assert rows >= 2 and orphans == 0, (rows, orphans)


@pytest.mark.parametrize("hash_", ["", "view=open", "r=people%2Fmara-ostrowski.md"])
def test_the_phone_tab_bar_never_covers_the_last_block(page_at, hash_):
    """Mac review of rc30: on a phone the bottom tab bar hid the last content block."""
    page = page_at(hash_, 390)
    page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)", isolated_context=False)
    page.wait_for_timeout(300)
    # The page ends at least the tab bar's reach above the screen's edge, so its last block scrolls clear of the bar.
    gap = page.evaluate("""() => { const bar = document.querySelector('.tabbar').getBoundingClientRect();
      return parseFloat(getComputedStyle(document.getElementById('main')).paddingBottom) - (innerHeight - bar.top); }""", isolated_context=False)
    assert gap >= 0, gap
