"""Today says why the nights read nothing (sprint 14, opt in).

On the owner's notebook 30 scheduled turns in a row ended with no task because one person's page hit an Outlook
404 and then a timeout; Today said only «近 3 天没有读信、也没有整理页面». Now REM sets that page aside, and the night
card says why in one plain sentence, with the pages set aside folded under it. The notebook is the invented one in
tests/fixtures/rem_reader_notebook.py, served as in test_rem_today_fuse_browser.py.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

TOMAS = "people/tomas-reyes.md"

STUCK = r'''(stall) => { REM.night_stall = stall; render(); scrollTo(0, 0); }'''


def stall(**fields):
    return {"provider": "Outlook", "reason": "timeout", "times": 14, "pages": 1, "stopped": False,
            "parked": [{"record": TOMAS, "provider": "outlook", "reason": "timeout", "retry_at": "2026-10-02T06:00:00+00:00"}],
            **fields}


@pytest.mark.parametrize("size", [(1440, 900), (390, 844)])
def test_a_stalled_night_says_why_in_one_plain_sentence_and_folds_what_waits(today, size):
    page, _, _ = today
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.evaluate(STUCK, stall(), isolated_context=False)
    line = page.locator(".night-card .night-stall > summary")
    assert line.is_visible()
    assert line.inner_text().startswith(
        "Last night REM got stuck on Outlook: timed out 14 times; it set that page aside and did the rest")
    # Never an exception name or a command on screen.
    card = page.locator(".night-card").inner_text()
    assert "ReadTimeout" not in card and "co outlook" not in card and "HTTP" not in card
    # The page set aside is listed quietly, by name, with when it is tried again.
    assert not page.locator(".night-stall li").first.is_visible()
    line.click()
    waits = page.locator(".night-stall li").first
    assert waits.is_visible() and "Tomás Reyes" in waits.inner_text() and "tries again" in waits.inner_text()
    assert "people/" not in page.locator(".night-stall").inner_text()
    # The card still fits the phone: no sideways scroll.
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")

    page.evaluate("() => { setInterfaceLanguage('zh'); scrollTo(0, 0); }", isolated_context=False)
    assert page.locator(".night-card .night-stall > summary").inner_text().startswith(
        "REM 昨夜在 Outlook 上卡住了：超时 14 次，已跳过这一项，其余照常")


def test_once_fixed_the_line_says_how_many_were_skipped_and_that_rem_will_try_again(today):
    page, _, _ = today
    page.evaluate(STUCK, stall(times=1), isolated_context=False)
    page.evaluate("() => { setInterfaceLanguage('zh'); scrollTo(0, 0); }", isolated_context=False)
    assert page.locator(".night-stall > summary").inner_text().startswith("昨夜 1 项因 Outlook 超时跳过，会再试")


def test_a_mailbox_stopped_for_the_turn_is_said_once_without_a_command(today):
    page, _, _ = today
    page.evaluate(STUCK, stall(reason="auth", times=1, stopped=True), isolated_context=False)
    text = page.locator(".night-stall > summary").inner_text()
    assert text.startswith("Last night Outlook failed (authorization expired); REM stopped asking it for that turn")
    assert "co auth" not in text


def test_no_stall_no_line(today):
    page, _, _ = today
    assert page.locator(".night-stall").count() == 0
