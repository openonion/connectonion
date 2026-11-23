"""Opening the reader starts no translation work (#3349).

The rc11 hunt saw the live reader POST /rem/translate-all three times in one session with no click: a status read on
every page load and reload, each making the Host count the whole translation queue (seconds on a real notebook). A read
never started a model turn, but opening a page should cost nothing. Translation is the night's job: opening the reader
asks nothing; the owner opening a translate control (Settings, the language menu, the phone's 显示 menu) reads the
job's state once per page load. Invented notebook, real Host handler.
"""

import os

import pytest

from tests.e2e.cli.test_rem_translate_all_browser import live  # noqa: F401  (the fixture)

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def test_opening_the_reader_posts_no_translate_all(live):  # noqa: F811
    page, _, calls, _, posts = live
    page.wait_for_timeout(10000)
    assert posts == [], posts           # no status read, no start: opening a page is free
    assert calls == []                  # and certainly no model turn


def test_opening_a_translate_control_reads_the_state_once(live):  # noqa: F811
    page, _, calls, _, posts = live
    page.evaluate("() => openSettings()", isolated_context=False)
    page.wait_for_timeout(1500)
    page.evaluate("() => { document.getElementById('settings').close(); openSettings(); }", isolated_context=False)
    page.wait_for_timeout(1500)
    assert len(posts) == 1, posts       # one read per page load, however often the owner opens it
    assert calls == []                  # a status read never translates
