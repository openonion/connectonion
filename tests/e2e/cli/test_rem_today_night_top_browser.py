"""Today opens with the night (#3311, sprint T3): the sleep curve on top, the night's work under it on the same clock,
and every Today card with one primary step (#3312). Owner, 2026-11-22: «那个睡眠曲线……可以留着放在最上面……那个线
的下面，就是晚上做事情的时候». Invented notebook (tests/fixtures/rem_reader_notebook.py)."""
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


@pytest.fixture(scope="module")
def page_file(tmp_path_factory):
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    root = tmp_path_factory.mktemp("t3") / "rem"
    build(root, datetime(2026, 11, 22, tzinfo=timezone.utc))
    path = root.parent / "reader.html"
    path.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    return path


def _open(page_file, width, height, mobile=False, reduced=False):
    from patchright.sync_api import sync_playwright
    api = sync_playwright().start()
    browser = api.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=mobile, has_touch=mobile,
                              locale="en-US", reduced_motion="reduce" if reduced else "no-preference")
    page = ctx.new_page()
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(page_file.as_uri())
    page.locator("#main .night-card").wait_for()
    return api, browser, page


def test_the_curve_and_the_nights_work_open_today_above_the_first_card(page_file):
    api, browser, page = _open(page_file, 1440, 900)
    try:
        state = page.evaluate("""() => {
          const card = document.querySelector('#main .night-card'), hypno = card.querySelector('.hypno');
          const first = document.querySelector('#main .qcard');
          return {hypno: !!hypno, hypnoBottom: hypno && hypno.getBoundingClientRect().bottom,
                  firstTop: first && first.getBoundingClientRect().top, inFold: document.querySelectorAll('#processing .hypno').length};
        }""", isolated_context=False)
        assert state["hypno"], "the sleep curve is in Today's first card"
        assert state["inFold"] == 0, "the curve no longer hides in the bottom fold"
        assert state["firstTop"] is not None and state["hypnoBottom"] < state["firstTop"] < 900, state
    finally:
        browser.close(); api.stop()


def test_each_stretch_of_work_sits_under_its_own_dip_and_opens_to_its_pages(page_file):
    api, browser, page = _open(page_file, 1440, 900)
    try:
        rows = page.evaluate("""() => {
          const hypno = document.querySelector('#main .night-card .hypno').getBoundingClientRect();
          return [...document.querySelectorAll('#main .night-card .stretch')].map(s => {
            const box = s.getBoundingClientRect(), from = hypno.left + hypno.width * s.dataset.from / 100, to = hypno.left + hypno.width * s.dataset.to / 100;
            return {text: s.innerText, left: box.left, right: box.right, from, to, fromRight: s.classList.contains('from-right'), top: box.top, curveBottom: hypno.bottom};
          });
        }""", isolated_context=False)
        assert len(rows) >= 2, rows
        for row in rows:
            assert row["top"] >= row["curveBottom"] - 2, "the words hang under the curve"
            # Left-hung words start under the dip's start; right-hung ones end under the dip's end.
            edge, mark = (row["right"], row["to"]) if row["fromRight"] else (row["left"], row["from"])
            assert abs(edge - mark) < 48, row
            assert "–" in row["text"] or ":" in row["text"], "each stretch says when"
        stretch = page.locator("#main .night-card .stretch").filter(has=page.locator(".stretch-pages")).first
        stretch.locator("summary").click()
        assert stretch.locator(".stretch-pages a").count() >= 1, "a stretch opens to the pages it changed"
        page.keyboard.press("Escape")
        assert stretch.evaluate("el => el.open") is False
    finally:
        browser.close(); api.stop()


def test_a_phone_keeps_the_three_biggest_stretches_stacked(page_file):
    api, browser, page = _open(page_file, 390, 844, mobile=True)
    try:
        n = page.locator("#main .night-card .stretches.stacked .stretch").count()
        assert 1 <= n <= 3
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        browser.close(); api.stop()


def test_reduced_motion_draws_the_curve_without_animation(page_file):
    api, browser, page = _open(page_file, 1440, 900, reduced=True)
    try:
        name = page.evaluate("getComputedStyle(document.querySelector('#main .night-card .hypno .trace')).animationName")
        assert name in ("none", ""), name
    finally:
        browser.close(); api.stop()


def test_a_codex_debt_row_has_one_primary_the_three_closes_and_a_worded_more(page_file):
    """The handed row had eight links in one line (Mac rc11 pass); now: status, one step, the closes, 更多操作."""
    api, browser, page = _open(page_file, 1440, 900)
    try:
        page.evaluate("""() => { const row = REM.today_queue.find(row => row.section === 'today');
          row.task = {id: 'a'.repeat(32), agent: 'codex', result: 'completed', record: 'people/ines-halvorsen.md'};
          REM.live = true; render(); }""", isolated_context=False)
        # People waiting come before an agent's not-overdue work, so the handed card is dealt behind them.
        order = page.evaluate("[...document.querySelectorAll('.today-brief .qcard')].map(c => !!c.querySelector('.handed'))", isolated_context=False)
        assert True in order and order[0] is False, order
        page.locator('.deal[data-path="people/ines-halvorsen.md"]').first.click()
        item = page.locator(".today-brief .qcard.focal .qitem").filter(has=page.locator(".handed")).first
        item.hover()
        line = item.locator(".handoff-line")
        outside = line.evaluate("""line => [...line.querySelectorAll('button, a')].filter(n => !n.closest('.row-more-menu'))
          .map(n => n.textContent.trim())""")
        assert line.locator(".strip-lead").count() == 1, outside
        for word in ("Mark done", "Not now", "Ignore"):
            assert word in outside, outside
        assert len(outside) <= 4, outside  # one step and the three closes; the rest is under More actions
        more = line.locator(".row-more > summary")
        assert more.inner_text().strip() == "More actions"  # a word, never a bare glyph (D-100)
        more.click()
        assert line.locator(".row-more-menu > *").first.is_visible()
        page.keyboard.press("Escape")
        assert line.locator(".row-more").evaluate("el => el.open") is False
        assert page.evaluate("document.activeElement.classList.contains('row-more-btn')", isolated_context=False)
    finally:
        browser.close(); api.stop()
