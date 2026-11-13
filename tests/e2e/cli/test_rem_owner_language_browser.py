"""Today in the owner's language (opt in): the draft's gist column says what it is and in which language,
and a row whose words are not yet in the reader's language carries the page header's quiet 原文.

The notebook is the invented one in tests/fixtures/rem_reader_notebook.py; its pages are English.
"""

import os

import pytest

from tests.e2e.cli.test_rem_today_fuse_browser import DRAFT, OVERDUE, today  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

ENGLISH_GIST = "() => { REM.drafts[0].gist = 'Sends her the Q3 receipts.'; render(); }"


@pytest.mark.parametrize("width", [1440, 390])
def test_the_gist_column_names_its_language_never_the_chinese_side(today, width):
    page, _, _ = today
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("() => { setInterfaceLanguage('zh'); }", isolated_context=False)
    title = page.locator(".qcard.focal .mail-gist > .k")
    # On a phone the gist waits for the writer (display: none); its words are the same.
    read = title.inner_text if width > 400 else title.text_content
    assert read() == "要点"
    page.evaluate(ENGLISH_GIST, isolated_context=False)
    assert read() == "要点 · English"
    assert "中文对照" not in page.locator("#main").inner_text()


@pytest.mark.parametrize("width", [1440, 390])
def test_english_rows_on_a_chinese_today_carry_the_quiet_original_mark(today, width):
    page, _, _ = today
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate("() => { setInterfaceLanguage('zh'); }", isolated_context=False)
    words = page.locator("#main .qitem .words").first
    assert words.inner_text().startswith("原文")
    mark = words.locator(".lang-status")
    assert mark.is_visible() and mark.get_attribute("title") == "尚无中文译文，显示原文"
    # Quiet: meta size and grey, never the words' own ink.
    assert mark.evaluate("n => getComputedStyle(n).color") != words.evaluate("n => getComputedStyle(n).color")
    # In English nothing is marked: pages are not translated into English.
    page.evaluate("() => { setInterfaceLanguage('en'); }", isolated_context=False)
    assert page.locator("#main .qitem .lang-status").count() == 0
