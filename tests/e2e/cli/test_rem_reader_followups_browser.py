"""The rail's follow-ups from the review of #2960 (#2961), in a real browser (opt in).

The rail itself is the owner's design (D-132) and stays: a picture and a word per place. These tests check
what the review found around it: a short word is the start of its place's name (WCAG 2.5.3, label in name),
More opens beside its button wherever the rail has scrolled and never past the window, your own face says
its name on keyboard focus, and the phone More sheet keeps every label in one column. The notebook is the
invented one in tests/fixtures/rem_reader_notebook.py.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_reader_design_browser import reader  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _shot(page, name):
    if os.environ.get("CO_REM_SHOTS"):
        page.screenshot(path=str(Path(os.environ["CO_REM_SHOTS"]) / name))


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_every_rail_word_is_the_start_of_its_places_name(reader, lang):
    page, uri = reader
    page.goto(uri)
    page.evaluate(f"setInterfaceLanguage('{lang}')", isolated_context=False)
    cells = page.locator(".rail .nav").evaluate_all("""nodes => nodes.filter(n => n.querySelector('.w'))
      .map(n => [n.querySelector('.w').textContent, n.getAttribute('aria-label')])""")
    assert len(cells) == 9 and all(name.startswith(word) for word, name in cells), cells
    if lang == "en":  # what a voice-control user says is what they see
        assert page.get_by_role("link", name="Orgs").get_attribute("href") == "#c=orgs"
        assert "Organisations" in page.locator('#nav a[href="#c=orgs"]').get_attribute("aria-label")


@pytest.mark.parametrize("height", [540, 400])
def test_more_opens_beside_its_button_after_the_rail_scrolls(reader, height):
    page, uri = reader
    page.set_viewport_size({"width": 960, "height": height})
    page.goto(uri)
    page.locator(".rail").evaluate("rail => rail.scrollTop = rail.scrollHeight")
    page.locator(".nav.more").click()
    button, menu = page.locator(".nav.more").bounding_box(), page.locator("#rail-more").bounding_box()
    _shot(page, f"rail-more-scrolled-{height}.png")
    assert menu["y"] >= 0 and menu["y"] + menu["height"] <= height, menu      # none of it past the window
    assert menu["y"] <= button["y"] + button["height"] and menu["y"] + menu["height"] >= button["y"], (menu, button)
    assert abs(menu["y"] + menu["height"] - (button["y"] + button["height"])) <= 8 or menu["y"] <= 8, (menu, button)
    assert page.locator("#rail-more a").last.evaluate("a => { a.scrollIntoView({block: 'nearest'}); const b = a.getBoundingClientRect(); return b.bottom <= innerHeight; }")


def test_your_face_says_your_name_on_keyboard_focus(reader):
    page, uri = reader
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(uri)
    page.keyboard.press("Tab")
    page.locator(".nav.you").focus()
    assert page.locator(".nav.you").evaluate("n => n.matches(':focus-visible')")
    page.evaluate("Promise.all(document.getAnimations().filter(a => a instanceof CSSTransition).map(a => a.finished))")  # its fade in
    label = page.locator(".nav.you").evaluate("""n => { const shown = [...n.querySelectorAll('*')].find(c => c.textContent.trim().startsWith('You')
        && getComputedStyle(c).opacity === '1' && c.getBoundingClientRect().width > 1);
      if (!shown) return null; const b = shown.getBoundingClientRect(); return {text: shown.textContent, right: b.right, top: b.top, bottom: b.bottom}; }""")
    _shot(page, "rail-you-focus-1440.png")
    assert label and label["text"] == "You · Avery Lin" and label["right"] <= 1440 and label["top"] >= 0 and label["bottom"] <= 900, label
    page.mouse.move(700, 450)
    page.locator("#nav a").first.focus()
    page.evaluate("Promise.all(document.getAnimations().filter(a => a instanceof CSSTransition).map(a => a.finished))")  # and out
    assert page.locator(".nav.you").evaluate("n => [...n.querySelectorAll('*')].every(c => getComputedStyle(c).opacity !== '1' || !c.textContent.trim().startsWith('You'))")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_phone_more_sheet_starts_every_label_in_one_column(reader, theme):
    page, uri = reader
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(uri)
    page.evaluate(f"setTheme('{theme}')", isolated_context=False)
    page.locator(".nav-toggle").click()
    starts = page.evaluate("""() => {
      const places = [...document.querySelectorAll('#nav .nav, #rail-end .nav.settings-open')].filter(n => n.getClientRects().length).map(n => {
        const picture = n.querySelector('svg.ic').getBoundingClientRect(); return Math.round(picture.right + parseFloat(getComputedStyle(n).columnGap)); });
      const more = [...document.querySelectorAll('#rail-more .mi span:not(.icw)')].map(s => Math.round(s.getBoundingClientRect().left));
      return {places, more}; }""")
    _shot(page, f"phone-more-sheet-{theme}-390.png")
    assert starts["more"] and len(set(starts["places"] + starts["more"])) == 1, starts

