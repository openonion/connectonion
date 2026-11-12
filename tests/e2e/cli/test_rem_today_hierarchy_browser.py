"""Today has one primary action per card and numbers you can act on (sprint 14, opt in).

Seen on the owner's own notebook at rc7: the side rail's «60 等对方回 / 19 可一键批准» were two big numbers with
nothing to press; the header said «5 人在等你» while the rail badge said 21; every row of a card carried eight
equal links and on a phone wrapped to two lines beside a bare «»» glyph; promises months old took the rail above
the fold; and «关于 X，有什么值得记住?» asked a question with no reason and no way to answer it. The notebook is the
invented one in tests/fixtures/rem_reader_notebook.py, served as in test_rem_today_fuse_browser.py.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import DRAFT, today  # noqa: E402,F401
from test_rem_today_truth_browser import ANCIENT  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

SIZES = [(1440, 900), (390, 844)]
LIVE = "() => { REM.live = true; render(); }"

# Two outcomes the Host can send at once and one waiting for the owner to fill a gap.
OUTCOMES = r'''blocked => {
  const item = (id, kind, title, extra = {}) => ({id, kind, title, to: title, body: 'Done, thanks.', keys: [], ...extra});
  REM.live = true;
  REM.approval_outcomes = [item('a', 'handled', 'Mara Ostrowski', {blocked}), item('b', 'task', 'Tomás Reyes', {blocked}),
    item('c', 'reply', 'Ines Halvorsen', {blocked: true})];
  render();
}'''


def _phone(page, size):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.evaluate("scrollTo(0, 0)", isolated_context=False)


@pytest.mark.parametrize("size", SIZES)
def test_the_rails_numbers_are_worded_controls(today, size):
    page, _, _ = today
    _phone(page, size)
    page.evaluate(OUTCOMES, False, isolated_context=False)
    others = page.locator("#today-others")
    batch = others.locator("#approve-all")
    assert batch.inner_text() == "Approve all 2"          # the two that can go; the one with a gap waits
    assert batch.evaluate("node => node.tagName") == "BUTTON"
    batch.click()
    assert page.locator("#approval-sheet").is_visible()
    assert page.locator("#approval-title").inner_text() == "Approve all 2"   # the sheet says the button's number
    page.keyboard.press("Escape")
    waiting = others.locator("a.waiting-more")
    assert waiting.get_attribute("href") == "#view=open"
    theirs = page.evaluate("threadCounts().theirs", isolated_context=False)
    assert waiting.inner_text() == f"See the {theirs} waiting on others →"
    # Nothing that can go at once: no button at all, not a greyed one and not a zero.
    page.evaluate(OUTCOMES, True, isolated_context=False)
    assert page.locator("#approve-all").count() == 0
    assert "approve" not in others.inner_text().lower()


@pytest.mark.parametrize("size", SIZES)
def test_the_header_and_the_badge_say_the_same_number_and_the_people_are_a_subset_in_words(today, size):
    page, _, _ = today
    _phone(page, size)
    mine = page.evaluate("threadCounts().mine", isolated_context=False)
    people = page.locator(".deal").count()
    assert mine and people
    badge = page.locator("#nav .n.waiting" if size[0] > 640 else "#tabbar .tab .n")
    assert int(page.locator(".night-card .count").inner_text()) == int(badge.inner_text()) == mine
    line = page.locator(".night-card .count-line")
    assert line.locator(".count-words").inner_text() == "things waiting on you"
    assert line.locator(".count-words").is_visible()       # a phone says what the number counts, too
    if size[0] > 640:
        assert line.locator(".count-of").inner_text() == f"Start with these {people} people"


def _primaries(card):
    return card.evaluate("""card => [...card.querySelectorAll('.btn-act, .strip-lead')].filter(node => {
      const box = node.getBoundingClientRect();
      return box.width > 0 && box.height > 0;
    }).map(node => node.textContent.trim())""")


@pytest.mark.parametrize("size", SIZES)
def test_every_card_has_one_primary_and_the_three_closes_are_words_without_a_hover(today, size):
    page, _, _ = today
    _phone(page, size)
    page.evaluate(LIVE, isolated_context=False)
    page.mouse.move(1, size[1] - 1)
    cards = page.locator(".today-brief .qcard")
    assert cards.count() >= 3
    for i in range(cards.count()):
        page.locator(".deal").nth(i).click()
        page.mouse.move(1, size[1] - 1)
        card = page.locator(".today-brief .qcard.focal")
        assert len(_primaries(card)) == 1, (i, _primaries(card))
        line = card.locator(".qitem").first.locator(".handoff-line")
        for word in ("Mark done", "Not now", "Ignore"):
            assert line.get_by_role("button", name=word, exact=True).is_visible(), (i, word)
        # The hand-offs stay visible words (D-100); only the talk folds under a worded More, never a bare glyph.
        for word in ("Hand to Codex", "Hand to Claude"):
            assert line.get_by_role("button", name=word, exact=True).is_visible(), (i, word)
        assert line.locator(":scope > .strip-more > summary").inner_text().startswith("More")


def test_the_reply_card_leads_with_send(today):
    page, _, _ = today
    page.evaluate(DRAFT, True, isolated_context=False)
    card = page.locator(".today-brief .qcard.focal")
    assert _primaries(card) == ["Send"]


def test_a_card_with_nothing_else_to_do_leads_with_mark_done_in_bold(today):
    page, _, _ = today
    page.evaluate(LIVE, isolated_context=False)
    leads = page.evaluate("""() => [...document.querySelectorAll('.qcard .strip-lead')].map(node =>
      [node.textContent.trim(), Number(getComputedStyle(node).fontWeight)])""", isolated_context=False)
    assert leads and all(weight >= 600 for _, weight in leads), leads
    assert {text for text, _ in leads} <= {"Mark done", "Hand to Codex"}


def test_on_a_phone_the_closes_are_one_line_and_no_glyph_stands_alone(today):
    page, _, _ = today
    _phone(page, (390, 844))
    page.evaluate(LIVE, isolated_context=False)
    card = page.locator(".today-brief .qcard.focal")
    line = card.locator(".qitem").first.locator(".handoff-line")
    tops = [round(button.bounding_box()["y"]) for button in line.locator(":scope > :is(.strip-done, .strip-later, .strip-ignore)").all()]
    assert len(tops) == 3 and max(tops) - min(tops) <= 4, tops            # the three closes are the first line
    codex = line.get_by_role("button", name="Hand to Codex", exact=True).bounding_box()
    assert codex["y"] > max(tops) + 10                                      # the hand-offs start the second
    assert "Hand to Codex" in line.inner_text() and "Hand to Claude" in line.inner_text()
    assert line.evaluate("line => line.scrollWidth <= line.clientWidth + 1")
    for button in card.locator(".qhead button").all():
        if button.is_visible():
            assert button.inner_text().strip(), button.get_attribute("aria-label")


# A second promise as old, on another page: closing both at once must not link them as one thread.
ANCIENT_TOO = r'''async () => {
  const r = byPath('people/mara-ostrowski.md');
  r.original = undefined;
  r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1- You owe Mara the old banner files; requested 2026-04-01, due 2026-04-03.\n');
  KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
}'''


def test_long_quiet_promises_are_one_folded_line_below_the_desk_with_close_all_and_undo(today):
    page, _, _ = today
    page.evaluate(ANCIENT, isolated_context=False)
    page.evaluate(ANCIENT_TOO, isolated_context=False)
    stale = page.locator("#today-stale")
    assert stale.evaluate("node => node.tagName") == "DETAILS" and stale.get_attribute("open") is None
    assert stale.locator("summary").inner_text() == "2 have gone quiet for a long time · Look"
    assert page.locator(".tgrid > .side #today-stale").count() == 0          # not in the rail
    desk = page.locator(".tgrid").bounding_box()
    assert stale.bounding_box()["y"] >= desk["y"] + desk["height"]           # under the desk and its rail
    stale.locator("summary").click()
    for row in stale.locator("li").all():
        assert row.get_by_role("button").all_inner_texts() == ["Mark done", "Still open"]
    assert stale.get_attribute("aria-label") is None                         # its words are on screen
    stale.get_by_role("button", name="Mark all 2 done", exact=True).click()
    assert page.locator("#today-stale").count() == 0
    marks = page.evaluate("() => Object.values(threadStates).map(value => value.keys.length)", isolated_context=False)
    assert marks == [1, 1], marks                                            # two marks, never one linked thread
    page.locator("#done-notice").get_by_role("button", name="Undo", exact=True).click()
    assert page.locator("#today-stale summary").inner_text() == "2 have gone quiet for a long time · Look"


def test_today_no_longer_asks_what_to_remember_without_a_reason(today):
    page, _, _ = today
    page.evaluate(LIVE, isolated_context=False)
    assert page.locator(".recall").count() == 0
    assert "What should you remember" not in page.locator("#main").inner_text()


def test_a_held_reply_leaves_the_count_the_badge_and_the_waiting_rows_together(today):
    page, _, _ = today
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("() => { REM.drafts[0].status = 'held'; threadEntries.cached = null; render(); }", isolated_context=False)
    badge = int(page.locator("#nav .n.waiting").inner_text())
    assert int(page.locator(".night-card .count").inner_text()) == badge
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    band = page.locator(".task-band").filter(has=page.get_by_role("heading", name="Waiting on you")).first
    band.wait_for()
    assert band.locator("ul.threads > li").count() == badge
