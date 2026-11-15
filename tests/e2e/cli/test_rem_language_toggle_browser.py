"""One button at the top of every page flips the reader between 中文 and English (opt in).

The owner, 2026-11-11: «语言切换应该有特别简洁的方式，就像日间模式和夜间模式切换的按钮一样，可以一键把语言切换成中文或者英文».
It is the same setter and storage as the language choice in Settings, so both agree and the choice persists;
the page redraws in place. The notebook is the invented one in tests/fixtures/rem_reader_notebook.py.
"""

import os
import re

import pytest

from tests.e2e.cli.test_rem_reader_polish_browser import reader  # noqa: F401  (fixture)
from tests.e2e.cli.test_rem_today_fuse_browser import OVERDUE, today  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

VIEWS = ["", "r=people%2Fmara-ostrowski.md", "c=projects", "view=graph"]


@pytest.mark.parametrize("width", [1440, 390])
def test_the_toggle_is_at_the_top_of_every_page(reader, width):
    page, _, _ = reader
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    for view in VIEWS:
        page.evaluate("view => { location.hash = view; }", view, isolated_context=False)
        page.wait_for_timeout(300)
        toggle = page.locator("header.top #lang-toggle")
        assert toggle.is_visible(), view
        box = toggle.bounding_box()
        assert box["y"] < 80 and box["x"] + box["width"] <= width and box["x"] > width / 2, (view, box)
        if width < 400:
            assert box["width"] >= 44 and box["height"] >= 44, box
        # Quiet: no fill of its own, and no green.
        assert toggle.evaluate("n => getComputedStyle(n).backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False), view


def test_one_click_flips_the_language_and_it_persists(reader):
    page, _, _ = reader
    page.evaluate("() => { setInterfaceLanguage('en'); }", isolated_context=False)
    toggle = page.locator("#lang-toggle")
    assert toggle.inner_text() == "中" and toggle.get_attribute("aria-label") == "切换到中文"
    toggle.click()
    assert toggle.inner_text() == "EN" and toggle.get_attribute("aria-label") == "Switch to English"
    assert re.search(r"[一-鿿]", page.locator("#main h1").inner_text())
    assert page.evaluate("localStorage.getItem('co-rem-ui-language')", isolated_context=False) == "zh"
    page.reload()
    page.locator("#main h1").wait_for()
    assert page.locator("#lang-toggle").inner_text() == "EN"
    assert re.search(r"[一-鿿]", page.locator("#main h1").inner_text())
    page.locator("#lang-toggle").click()
    assert not re.search(r"[一-鿿]", page.locator("#main h1").inner_text())
    assert page.evaluate("localStorage.getItem('co-rem-ui-language')", isolated_context=False) == "en"


def test_the_flip_keeps_scroll_and_open_sections(reader):
    page, _, _ = reader
    page.set_viewport_size({"width": 1440, "height": 600})
    page.evaluate("() => { setInterfaceLanguage('en'); }", isolated_context=False)
    details = page.locator("#main details").last
    details.locator("summary").click()
    page.evaluate("() => { document.querySelectorAll('#main details')[document.querySelectorAll('#main details').length - 1].scrollIntoView(); scrollBy(0, -40); }", isolated_context=False)
    before = page.evaluate("scrollY", isolated_context=False)
    assert before > 0
    count = page.locator("#main details").count()
    # The header scrolls with the page, so a pointer click would scroll to it first; the event itself
    # is what keeps the view, so it is sent without moving the page.
    page.locator("#lang-toggle").dispatch_event("click")
    assert page.locator("#main details").count() == count
    assert page.locator("#main details").last.evaluate("n => n.open")
    assert abs(page.evaluate("scrollY", isolated_context=False) - before) <= 2


# Today with one prepared reply whose slot is a field to type into. A draft with an id gives the field a stable
# key (data-keep), so a redraw can put its words back; one without an id gives a field no redraw can find again.
SLOT = r"""id => { REM.live = true; setInterfaceLanguage('en');
  REM.source_context['outlook:3d5f7b9e1a0c'] = {...REM.source_context['outlook:3d5f7b9e1a0c'], source: 'outlook', thread: 'mail:fixture:ines'};
  REM.drafts = [{...(id ? {id} : {}), version: 'v1', provider: 'outlook', thread: 'mail:fixture:ines', status: 'prepared',
    to: 'Ines Halvorsen <ines@example.test>', from: 'avery@example.test', subject: 'Re: Q3 receipts',
    body: 'Hi Ines,\n\nI can send the receipts 【需要你：the day you can send them — by Friday】.\n\nAvery'}];
  render(); }"""


def test_a_real_click_keeps_the_words_caret_and_focus_of_a_field_being_typed_in(today):
    """Review of #2955: the click drew the page again at once, and a reply half typed was gone."""
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(SLOT, "ines-receipts", isolated_context=False)
    slot = page.locator(".today-brief .qcard.open .owner-slot input")
    assert slot.get_attribute("data-keep") and slot.get_attribute("placeholder") == "Type your answer"
    slot.click()
    page.keyboard.type("Thursday afternoon")
    slot.evaluate("node => node.setSelectionRange(3, 8)")
    page.locator("#lang-toggle").click()
    assert page.locator("#lang-toggle").inner_text() == "EN" and page.locator("#updates-waiting").count() == 0
    slot = page.locator(".today-brief .qcard.open .owner-slot input")
    assert slot.get_attribute("placeholder") != "Type your answer"       # the page was drawn again, in 中文
    assert slot.input_value() == "Thursday afternoon"
    assert slot.evaluate("node => [node === document.activeElement, node.selectionStart, node.selectionEnd]") == [True, 3, 8]
    assert page.locator(".today-brief .qcard.open .mail-actions .btn-act").is_enabled()   # the answer is still in the reply


def test_a_real_click_waits_instead_of_wiping_words_it_could_not_put_back(today):
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(SLOT, "", isolated_context=False)
    slot = page.locator(".today-brief .qcard.open .owner-slot input")
    assert slot.get_attribute("data-keep") is None
    slot.click()
    page.keyboard.type("Thursday afternoon")
    page.evaluate("() => { document.querySelector('.today-brief').dataset.before = '1'; }", isolated_context=False)
    page.locator("#lang-toggle").click()
    # The choice is taken and saved, the button already names the way back, and the page says it has more to show.
    assert page.locator("#lang-toggle").inner_text() == "EN"
    assert page.evaluate("localStorage.getItem('co-rem-ui-language')", isolated_context=False) == "zh"
    mark = page.locator("#updates-waiting")
    assert mark.inner_text() == "有更新"
    mark.click()                                                         # not while the words are still there
    assert page.locator(".today-brief[data-before]").count() == 1
    assert slot.input_value() == "Thursday afternoon" and slot.get_attribute("placeholder") == "Type your answer"
    assert slot.evaluate("node => node === document.activeElement")
    slot.fill("")                                                        # the words are gone by the owner's own hand
    slot.blur()                                                          # and the field is left
    mark.wait_for(state="detached")
    assert page.locator(".today-brief[data-before]").count() == 0
    assert page.locator(".today-brief .qcard.open .owner-slot input").get_attribute("placeholder") != "Type your answer"
