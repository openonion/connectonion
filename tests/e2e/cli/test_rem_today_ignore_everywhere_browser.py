"""Ignore is a visible word on every row Today shows, at first paint, desktop and phone (#2990, opt in).

Owner, opening the reader himself on 1.9.6rc7: «Today 页面：为什么没有"忽略"这个功能呢？». The top card had it;
the long-quiet fold offered only Mark done / Still open, Today's Gone quiet fold and Waiting's Gone quiet section
offered no close or only Mark done, and a snapshot (no Host) showed none of the three on any row. Each row type
here is asked for Mark done · Not now · Ignore, in that order, in its inner_text with the mouse away (no hover).
A snapshot shows them too, disabled with its reason in words, since nothing carries its marks to the notebook.
The notebook is the invented one in tests/fixtures/rem_reader_notebook.py, served as in
test_rem_today_fuse_browser.py.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_reader_design_browser import reader  # noqa: E402,F401
from test_rem_today_fuse_browser import OVERDUE, today  # noqa: E402,F401
from test_rem_today_hierarchy_browser import ANCIENT_TOO  # noqa: E402
from test_rem_today_truth_browser import ANCIENT  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

SIZES = [(1440, 900), (390, 844)]
CLOSES = ["Mark done", "Not now", "Ignore"]
LIVE = "() => { REM.live = true; render(); }"


def _at(page, size, live=True):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    if live:
        page.evaluate(LIVE, isolated_context=False)
    page.mouse.move(0, 0)


def _says_the_closes(row):
    """Mark done · Not now · Ignore are words in the row as drawn now, in D-100's order."""
    text = row.inner_text()
    at = [text.find(word) for word in CLOSES]
    assert all(i >= 0 for i in at) and at == sorted(at), (at, text)
    for word in CLOSES:
        assert row.get_by_role("button", name=word, exact=True).first.is_visible(), (word, text)


@pytest.mark.parametrize("size", SIZES)
def test_every_dealt_cards_rows_say_ignore(today, size):
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    _at(page, size)
    faces = page.locator(".deal .dd").count()
    assert faces >= 3
    for i in range(faces):
        page.locator(".deal").nth(i).click()
        page.mouse.move(0, 0)
        rows = page.locator(".today-brief .qcard.focal .qitem")
        for j in range(rows.count()):
            if rows.nth(j).is_visible():
                _says_the_closes(rows.nth(j))


@pytest.mark.parametrize("size", SIZES)
def test_a_row_handed_to_codex_still_says_ignore(today, size):
    page, _, _ = today
    page.evaluate("""() => { const row = REM.today_queue.find(row => row.section === 'today');
      row.task = {id: 'a'.repeat(32), agent: 'codex', result: 'completed', record: 'people/ines-halvorsen.md'}; }""", isolated_context=False)
    _at(page, size)
    handed = page.locator(".today-brief .qcard.focal .qitem").filter(has=page.locator(".handed"))
    assert handed.count() == 1
    _says_the_closes(handed)


@pytest.mark.parametrize("size", SIZES)
def test_the_long_quiet_fold_says_ignore_on_every_row(today, size):
    page, _, _ = today
    page.evaluate(ANCIENT, isolated_context=False)
    page.evaluate(ANCIENT_TOO, isolated_context=False)
    _at(page, size)
    page.locator("#today-stale > summary").click()
    page.mouse.move(0, 0)
    rows = page.locator("#today-stale li")
    assert rows.count() == 2
    for row in rows.all():
        _says_the_closes(row)
        assert row.get_by_role("button", name="Still open", exact=True).is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)


@pytest.mark.parametrize("size", SIZES)
def test_todays_gone_quiet_fold_says_ignore_on_every_row(today, size):
    page, _, _ = today
    page.evaluate(QUIET, isolated_context=False)
    _at(page, size)
    page.locator("#gone-quiet > summary").click()
    page.mouse.move(0, 0)
    rows = page.locator("#gone-quiet li")
    assert rows.count() >= 1
    for row in rows.all():
        _says_the_closes(row)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)


@pytest.mark.parametrize("size", SIZES)
def test_waitings_gone_quiet_section_says_ignore_on_every_row(today, size):
    page, _, _ = today
    page.evaluate(ANCIENT, isolated_context=False)
    _at(page, size)
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    page.locator("#gone-quiet > summary").click()
    page.mouse.move(0, 0)
    rows = page.locator("#gone-quiet ul.threads > li")
    assert rows.count() >= 1
    for row in rows.all():
        _says_the_closes(row)


@pytest.mark.parametrize("size", SIZES)
def test_waiting_rows_say_ignore(today, size):
    page, _, _ = today
    _at(page, size)
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    rows = page.locator(".task-band ul.threads > li")
    assert rows.count() >= 2
    for row in rows.all():
        _says_the_closes(row)


CLOSE_WHY = "This is an offline snapshot; open REM to mark it."
HAND_WHY = "Handing work to an agent happens in the live reader."
STRIP = ["Mark done", "Not now", "Ignore", "Hand to Codex", "Hand to Claude", "More"]
WRITTEN = """() => ({states: Object.keys(threadStates).length, stored: localStorage.getItem(threadStorageKey())})"""
# A thread on Today that has gone quiet but is not a long-past promise, so it belongs to Today's Gone quiet fold.
QUIET = """() => { REM.today_queue.find(row => row.section === 'today').quiet = true; threadEntries.cached = null; render(); }"""


def _why(page, button):
    """The reason a disabled button gives: its title, and the text aria-describedby points at."""
    described = button.get_attribute("aria-describedby")
    return button.get_attribute("title"), page.locator(f"#{described}").text_content() if described else None


def _disabled_with_reason(page, row, words, why):
    for word in words:
        button = row.get_by_role("button", name=word, exact=True).first
        assert button.is_visible() and button.is_disabled(), (word, row.inner_text())
        assert _why(page, button) == (why, why), word


@pytest.mark.parametrize("size", SIZES)
def test_a_file_snapshot_shows_the_closes_disabled_and_says_why_in_words(reader, size):
    """Review of #2990: a file:// snapshot's marks never reach the notebook, so its closes are words it cannot use.

    Each card and each band says so once, in words; every close and hand-off says why on the button; and nothing,
    not E either, writes a mark on this device."""
    page, uri = reader
    assert uri.startswith("file://")
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.mouse.move(0, 0)
    card = page.locator(".today-brief .qcard.focal")
    row = card.locator(".qitem").first
    _says_the_closes(row)
    _disabled_with_reason(page, row, CLOSES, CLOSE_WHY)
    _disabled_with_reason(page, row, ["Hand to Codex", "Hand to Claude"], HAND_WHY)
    assert card.inner_text().count(CLOSE_WHY) == 1
    if size[0] < 400:
        for button in row.locator(".handoff-line > button").all():
            assert button.bounding_box()["height"] >= 44, button.inner_text()
    before, stored = page.locator(".today-brief .qcard").count(), page.evaluate(WRITTEN, isolated_context=False)
    assert stored["states"] == 0
    card.focus()
    page.keyboard.press("e")
    assert page.evaluate(WRITTEN, isolated_context=False) == stored
    assert page.locator(".today-brief .qcard").count() == before
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    bands = page.locator(".task-band")
    bands.first.wait_for()
    for band in bands.all():
        assert band.inner_text().count(CLOSE_WHY) == 1
        for waiting in band.locator("ul.threads > li").all():
            _disabled_with_reason(page, waiting, CLOSES, CLOSE_WHY)
    assert page.evaluate(WRITTEN, isolated_context=False) == stored


def _strip_order(line):
    text = line.inner_text()
    at = [text.find(word) for word in STRIP]
    assert all(i >= 0 for i in at) and at == sorted(at), (at, text)


def test_one_strip_order_on_today_waiting_and_the_folds(today):
    """D-100, one order everywhere: 标为完成 · 暂不处理 · 忽略 · 交给 Codex · 交给 Claude · 更多 (#2990 review)."""
    page, _, _ = today
    page.evaluate(ANCIENT, isolated_context=False)
    _at(page, SIZES[0])
    _strip_order(page.locator(".today-brief .qcard.focal .qitem .handoff-line").first)
    page.locator("#today-stale > summary").click()
    _strip_order(page.locator("#today-stale li .handoff-line").first)
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    page.locator(".task-band").first.wait_for()
    for line in page.locator(".task-band ul.threads > li .handoff-line").all():
        _strip_order(line)
    page.locator("#gone-quiet > summary").click()
    _strip_order(page.locator("#gone-quiet li .handoff-line").first)


def test_a_long_quiet_promise_is_one_row_on_today(today):
    """Review of #2990: the long-quiet fold holds it, so Today's Gone quiet leaves it out; Waiting still lists it."""
    page, _, _ = today
    page.evaluate(ANCIENT, isolated_context=False)
    page.evaluate(ANCIENT_TOO, isolated_context=False)
    _at(page, SIZES[0])
    page.evaluate("document.querySelectorAll('#today-stale, #gone-quiet').forEach(d => { d.open = true; d.fill?.(); })", isolated_context=False)
    for words in ("loan agreement", "banner files"):
        rows = page.locator("#today-stale li, #gone-quiet li").filter(has_text=words)
        assert rows.count() == 1, words
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    page.locator("#gone-quiet > summary").click()
    assert page.locator("#gone-quiet li").filter(has_text="loan agreement").count() == 1


def test_a_folds_rows_are_drawn_when_it_first_opens(today):
    """Review of #2990: sixty strips nobody has opened are not built; opening the fold builds them, once."""
    page, _, _ = today
    page.evaluate(ANCIENT, isolated_context=False)
    _at(page, SIZES[0])
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    fold = page.locator("#gone-quiet")
    fold.wait_for(state="attached")
    assert fold.locator("li").count() == 0
    fold.locator(":scope > summary").click()
    rows = fold.locator("ul.threads > li").count()
    assert rows >= 1
    fold.locator(":scope > summary").click()
    fold.locator(":scope > summary").click()
    assert fold.locator("ul.threads > li").count() == rows
