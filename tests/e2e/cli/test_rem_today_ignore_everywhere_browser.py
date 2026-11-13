"""Ignore is a visible word on every row Today shows, at first paint, desktop and phone (#2990, opt in).

Owner, opening the reader himself on 1.9.6rc7: «Today 页面：为什么没有"忽略"这个功能呢？». The top card had it;
the long-quiet fold offered only Mark done / Still open, Today's Gone quiet fold and Waiting's Gone quiet section
offered no close or only Mark done, and a snapshot (no Host) showed none of the three on any row. Each row type
here is asked for Mark done · Not now · Ignore, in that order, in its inner_text with the mouse away (no hover).
The notebook is the invented one in tests/fixtures/rem_reader_notebook.py, served as in
test_rem_today_fuse_browser.py.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    page.evaluate(ANCIENT, isolated_context=False)
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


@pytest.mark.parametrize("size", SIZES)
def test_a_snapshot_says_ignore_on_todays_rows_and_waitings(today, size):
    """No Host: a close is kept on this device until the live reader syncs it, so the three are words here too."""
    page, _, _ = today
    _at(page, size, live=False)
    assert page.evaluate("REM.live", isolated_context=False) is False
    rows = page.locator(".today-brief .qcard.focal .qitem")
    assert rows.count() >= 1
    _says_the_closes(rows.first)
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    waiting = page.locator(".task-band ul.threads > li")
    assert waiting.count() >= 2
    for row in waiting.all():
        _says_the_closes(row)


def test_ignore_in_a_snapshot_keeps_the_mark_on_this_device(today):
    page, calls, _ = today
    _at(page, SIZES[0], live=False)
    before = page.locator(".today-brief .qcard").count()
    page.locator(".today-brief .qcard.focal .qitem").first.get_by_role("button", name="Ignore", exact=True).click()
    page.locator("#done-notice").wait_for()
    assert "Ignored · this one will not come back" in page.locator("#done-notice").inner_text()
    assert "Stop showing mail from" not in page.locator("#done-notice").inner_text()   # a sender rule needs the Host
    assert "ignored" in page.evaluate("Object.values(threadStates).map(value => value.state)", isolated_context=False)
    assert not [call for call in calls if call[0] == "/rem/thread"]
    assert page.locator(".today-brief .qcard").count() <= before
