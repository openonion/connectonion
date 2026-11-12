"""Today's open reply on a phone: the letter starts on the first screen and the Send bar's words stay whole (opt in).

Seen at 390 after the 1.9.5 overlap fix: with two items on the card, the letter sat under REM's question and began
behind the then-fixed Send bar, and "Skip" broke into "Ski / p". The notebook is the invented one in
tests/fixtures/rem_reader_notebook.py, served the same way as test_rem_today_fuse_browser.py.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import DRAFT, OVERDUE, today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

# Two owed items on Inès's card, the draft answering the second, with a long letter and a question slot.
TWO_ITEMS = r'''async lang => {
  REM.live = true;
  const r = byPath('people/ines-halvorsen.md');
  r.original = undefined;
  r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1- You owe Inès a reply on the Quinn Alder introduction: "Could you reply to her directly with a time that works for both of you next week"; due 2026-09-30 [2].\n')
    .replace(/(^## Sources[^\n]*\n)/mi, '$1- [2] outlook:7c1e9b3a5d20 — intro to Quinn; confidence high; observed 2026-09-25.\n');
  REM.source_context['outlook:3d5f7b9e1a0c'] = {...REM.source_context['outlook:3d5f7b9e1a0c'], source: 'outlook', thread: 'mail:fixture:ines'};
  REM.drafts = [{id: 'ines-receipts', version: 'v1', provider: 'outlook', thread: 'mail:fixture:ines', status: 'prepared',
    to: 'Ines Halvorsen <ines@example.test>', from: 'avery@example.test', subject: 'Re: Q3 receipts and the two autumn workshops',
    body: 'Inès,\n\nThanks for the note about the receipts and the two workshops. I would rather keep our conversation on what your clients need from the forecast, and on who looks after the books once the return is filed.\n\n【需要你：确认是否参加 11/11 工作坊、11/12 年终复盘，或都不参加】\n\nAvery',
    gist: '建议把交流重点放在她客户对预测的需求、报税之后谁来维护账目这两件事上。', why: 'She files the return soon.'}];
  KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); setInterfaceLanguage(lang); render(); scrollTo(0, 0);
}'''

# The tops of the text lines inside a node, one entry per line.
LINE_TOPS = r'''node => { const range = document.createRange(); range.selectNodeContents(node);
  return [...new Set([...range.getClientRects()].filter(l => l.width > 0 && l.height > 0).map(l => Math.round(l.top)))]; }'''


def _open(page, lang, scene, shot=True):
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate(OVERDUE, isolated_context=False)
    if scene == "two":
        page.evaluate(TWO_ITEMS, lang, isolated_context=False)
    else:
        page.evaluate(DRAFT, True, isolated_context=False)
        page.evaluate(f"() => {{ setInterfaceLanguage('{lang}'); render(); scrollTo(0, 0); }}", isolated_context=False)
    if shot and os.environ.get("CO_REM_SHOTS"):
        page.screenshot(path=str(Path(os.environ["CO_REM_SHOTS"]) / f"today-phone-{scene}-{lang}-390.png"))
    return page.locator(".today-brief .qcard.open")


@pytest.mark.parametrize("scene", ["one", "two"])
@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_letter_starts_on_the_first_phone_screen_above_the_send_bar(today, lang, scene):
    page, _, _ = today
    card = _open(page, lang, scene)
    bar = card.locator(".mail-actions").bounding_box()
    head, letter = card.locator(".mail-head").bounding_box(), card.locator(".mail-text")
    first = page.evaluate(r'''node => { const range = document.createRange(); range.selectNodeContents(node);
      const line = [...range.getClientRects()].find(l => l.height > 0); return [line.top, line.bottom]; }''',
                          letter.element_handle(), isolated_context=False)
    assert first[0] >= head["y"] + head["height"] - 0.5 and first[1] <= bar["y"] + 0.5, (first, head, bar)
    # The reply's needed parts fit the first screen: REM's question and its answer box sit above the bar too.
    for part in (".mail-choices .owner-slot .k", ".mail-choices .owner-slot :is(input, button)"):
        box = card.locator(part).first.bounding_box()
        assert box["y"] >= 0 and box["y"] + box["height"] <= bar["y"] + 0.5, (part, box, bar)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_more_on_a_phone_brings_back_every_item_and_its_hand_off(today, lang):
    page, _, _ = today
    card = _open(page, lang, "two")
    # The first row's strip (and its Mark done, Not now, Ignore) shows from the start (sprint 13); the second row waits.
    assert card.locator(".qitem").nth(1).is_hidden() and card.locator(".handoff").first.is_visible()
    card.locator(".qitem .words").first.click()  # a tap opens the row's second level (D-120)
    card.locator(".qfull").click()
    assert card.locator(".qitem").nth(1).is_visible() and card.locator(".handoff").first.is_visible()


@pytest.mark.parametrize("scene", ["one", "two"])
@pytest.mark.parametrize("lang", ["zh", "en"])
def test_every_word_on_the_phone_send_bar_stays_whole(today, lang, scene):
    page, _, _ = today
    card = _open(page, lang, scene)
    bar = card.locator(".mail-actions")
    box = bar.bounding_box()
    rows = set()
    for button in bar.locator("button").all():
        if not button.is_visible():
            continue
        rows.add(round(button.bounding_box()["y"]))
        tops = page.evaluate(LINE_TOPS, button.element_handle(), isolated_context=False)
        b = button.bounding_box()
        assert len(tops) == 1, (button.inner_text(), tops)
        assert b["x"] >= box["x"] - 0.5 and b["x"] + b["width"] <= box["x"] + box["width"] + 0.5, (button.inner_text(), b, box)
    assert len(rows) == 1, rows  # one row above the thumb
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_with_motion_on_the_send_bar_follows_the_question_inside_the_draft(today, lang):
    """Sprint 13: Send is no longer pinned over the card; with motion on too, it ends the draft, under REM's question."""
    page, _, _ = today
    page.emulate_media(reduced_motion="no-preference")
    card = _open(page, lang, "two", shot=False)
    page.wait_for_timeout(1000)  # the cards' rise has ended
    bar, choices = card.locator(".mail-actions").bounding_box(), card.locator(".mail-choices").bounding_box()
    draft = card.locator(".mailcard").bounding_box()
    assert choices["y"] + choices["height"] - 0.5 <= bar["y"] and bar["y"] + bar["height"] <= draft["y"] + draft["height"] + 0.5, (bar, choices, draft)
