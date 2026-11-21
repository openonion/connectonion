"""Today's deck in a real browser (opt in): the cards that show under the raised one deal the next.

The deck drew two card edges under the raised card, which look like more cards to pull; a click or a tap on them
did nothing. The head's Next card shows only while a pointer is over the card on a desktop, so the edges were
the one visible sign of the next card and the one thing that could not deal it.
"""
import os

import pytest

from tests.e2e.cli.test_rem_reader_design_browser import reader  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

RAISED = 'document.querySelector("#main .qcard.focal")?.dataset.path || null'
FACES = 'faces => faces.map(face => face.dataset.path)'


def _who(page, path):
    return page.evaluate("path => threadWho(byPath(path))", path, isolated_context=False)


def test_the_cards_under_the_raised_one_deal_the_next(reader):
    page, _ = reader
    faces = page.locator(".deal").evaluate_all(FACES)
    assert len(faces) >= 2
    start = page.evaluate(RAISED, isolated_context=False)
    after = faces[(faces.index(start) + 1) % len(faces)]
    edges = page.locator("#main .deck-next")
    # The edges stay where they were drawn, under the raised card: what shows of them is what a pointer reaches.
    card, box = page.locator("#main .qcard.focal").bounding_box(), edges.bounding_box()
    assert box["y"] + box["height"] > card["y"] + card["height"] and box["height"] <= 30
    assert page.evaluate("([x, y]) => !!document.elementFromPoint(x, y)?.closest('.deck-next')",
                         [box["x"] + box["width"] / 2, box["y"] + box["height"] - 4], isolated_context=False)
    assert edges.get_attribute("aria-label") == f"Next: {_who(page, after)}"
    edges.click()
    assert page.evaluate(RAISED, isolated_context=False) == after
    assert page.locator(".deal.on").get_attribute("data-path") == after
    # They name the card they deal next, and J still deals the same one.
    following = faces[(faces.index(after) + 1) % len(faces)]
    assert edges.get_attribute("aria-label") == f"Next: {_who(page, following)}"
    page.keyboard.press("j")
    assert page.evaluate(RAISED, isolated_context=False) == following
    # No new tab stop: the keyboard has J and K.
    assert edges.get_attribute("tabindex") == "-1"


def test_one_card_has_no_edges_under_it(reader):
    page, _ = reader
    page.evaluate("""() => { const keep = document.querySelector('#main .qcard.focal').dataset.path;
      const ok = new Set(threadEntries().filter(entry => entry.r.path === keep).map(doneKey));
      REM.today_queue = REM.today_queue.filter(row => ok.has(row.key)); threadEntries.cached = null; render(); }""", isolated_context=False)
    page.locator("#main .qcard.focal").wait_for()
    assert page.locator("#main .today-brief .qcard").count() == 1
    assert page.locator("#main .deck-next").count() == 0


def test_the_edges_stay_under_the_cards_above_the_line_that_counts_them(reader):
    """With fewer cards than items the deck ends in a line ("These cards are the most pressing …"); the edges sit
    between the raised card and that line, and cover none of its words."""
    page, _ = reader
    page.evaluate("""() => { const real = todayGroups;
      window.todayGroups = entries => real(entries).slice(0, 2).map(group => ({...group, entries: group.entries.slice(0, 1)})); render(); }""",
                  isolated_context=False)
    card = page.locator("#main .qcard.focal").bounding_box()
    edges, rest = page.locator("#main .deck-next").bounding_box(), page.locator("#main .deck-rest").bounding_box()
    assert card["y"] + card["height"] - 4 <= edges["y"] + edges["height"] <= rest["y"], (card, edges, rest)


def test_a_tap_on_the_edges_deals_the_next_on_a_phone(reader):
    page, uri = reader
    phone = page.context.browser.new_context(viewport={"width": 390, "height": 844}, locale="en-US", has_touch=True, is_mobile=True).new_page()
    phone.route("http*://**/*", lambda route: route.abort())
    phone.goto(uri)
    phone.locator(".night-card .count").wait_for()
    faces = phone.locator(".deal").evaluate_all(FACES)
    start = phone.evaluate(RAISED, isolated_context=False)
    phone.locator("#main .deck-next").tap()
    assert phone.evaluate(RAISED, isolated_context=False) == faces[(faces.index(start) + 1) % len(faces)]
    assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)
