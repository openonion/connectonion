"""Today tells the truth in one glance (sprint 13, opt in).

Seen on the owner's own notebook at 1.9.6rc6: a promise months past its date led the people waiting in red and the
Projects headline repeated it; the side counted what REM handled overnight while the Overnight section below
spoke only of reworded pages; on a phone the pinned Send bar sat over the draft's first lines; "Choose above
before sending" did not say what to choose; and a night chart with two dots across three days took the top row.
The notebook is the invented one in tests/fixtures/rem_reader_notebook.py, served as in
test_rem_today_fuse_browser.py.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import DRAFT, OVERDUE, today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

TOMAS = "people/tomas-reyes.md"

# The snapshot is 2026-10-01: a promise due 14 April is 170 days late, and nobody has written since 10 April.
ANCIENT = r'''async () => {
  const r = byPath('people/tomas-reyes.md');
  r.original = undefined;
  r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1- You owe Tomás the signed loan agreement for the van; requested 2026-04-10, due 2026-04-14.\n');
  KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
}'''


def _faces(page):
    return page.locator(".deal .dd").all_inner_texts()


def test_a_promise_170_days_old_is_not_counted_and_asks_done_or_still_open(today):
    page, _, _ = today
    before = int(page.locator(".night-card .count").inner_text())
    page.evaluate(ANCIENT, isolated_context=False)
    # Not one more person waiting, and no red 170 days anywhere on the first screen.
    assert int(page.locator(".night-card .count").inner_text()) == before
    assert "170 d" not in _faces(page)
    asked = page.locator(f'#today-stale li[data-path="{TOMAS}"]')
    assert page.locator("#today-stale .wt").inner_text() == "Maybe over · still open?"
    assert asked.locator(".stale-when").inner_text() == "Due Apr 14; no new message for 174 days"
    assert asked.get_by_role("button").all_inner_texts() == ["Mark done", "Still open"]
    assert asked.evaluate("li => getComputedStyle(li).color") != "rgb(192, 42, 23)"
    # Still open: the owner says it is live, so it counts and burns again.
    asked.get_by_role("button", name="Still open", exact=True).click()
    assert page.locator("#today-stale").count() == 0
    assert "170 d" in _faces(page)


def test_mark_done_on_a_stale_promise_closes_it_through_the_usual_path(today):
    page, _, _ = today
    page.evaluate(ANCIENT, isolated_context=False)
    before = int(page.locator(".night-card .count").inner_text())
    page.locator(f'#today-stale li[data-path="{TOMAS}"]').get_by_role("button", name="Mark done", exact=True).click()
    assert page.locator("#today-stale").count() == 0
    assert int(page.locator(".night-card .count").inner_text()) == before
    assert page.evaluate("""() => threadEntries().filter(entry => entry.r.path === 'people/tomas-reyes.md' && /loan agreement/.test(entry.t.text))
      .every(isDone)""", isolated_context=False)


def test_the_projects_headline_shouts_only_about_a_live_late_promise(today):
    page, _, _ = today
    page.evaluate("""() => {
      const r = REM.records.find(r => r.category === 'projects');
      r.open = [{kind: 'owed', due: '2026-04-14', since: '2026-04-10', who: 'people/tomas-reyes.md', text: 'The user owes Tomás the van agreement', promised: []}];
      location.hash = '#c=projects';
    }""", isolated_context=False)
    lede = page.locator(".pd-lede")
    lede.wait_for()
    assert lede.locator(".red").count() == 0
    assert lede.locator(".pd-asked").inner_text() == "1 promise is more than 60 days past its date with no word since; it may be over."
    page.evaluate("() => { REM.records.find(r => r.category === 'projects').open[0] = {...REM.records.find(r => r.category === 'projects').open[0], due: '2026-09-01', since: '2026-08-30'}; render(); }",
                  isolated_context=False)
    assert "is 30 days late" in lede.locator(".red").inner_text() and lede.locator(".pd-asked").count() == 0


def test_the_side_line_the_sheet_and_the_overnight_section_tell_the_same_number(today):
    page, _, _ = today
    page.evaluate("""() => {
      const o = (kind, path, n) => ({key: path + n, record: path, title: byPath(path).title, kind});
      REM.night_outcomes = [o('prepared', 'people/mara-ostrowski.md', 1), o('prepared', 'people/mara-ostrowski.md', 2),
        o('prepared', 'people/ines-halvorsen.md', 3), o('task', 'people/tomas-reyes.md', 4), o('no_reply', 'people/tomas-reyes.md', 5),
        o('no_reply', 'people/ines-halvorsen.md', 6), o('could_not_prepare', 'people/quinn-alder.md', 7)];
      render();
    }""", isolated_context=False)
    assert page.locator(".side .closed").inner_text().startswith("REM handled 6 things overnight")
    assert page.locator(".overnight .night-tally").inner_text() == (
        "REM handled 6 things overnight: 3 things have a reply drafted; prepared 1 task; 2 things need no reply.")
    page.locator(".side .closed .link-btn").click()
    lines = page.locator('#night-sheet .night-done li:not([data-kind="could_not_prepare"]) b').all_inner_texts()
    assert sum(int(line.split()[1] if line.startswith("Prepared") else line.split()[0]) for line in lines) == 6, lines
    page.keyboard.press("Escape")
    # The pages' half speaks of pages, never "nothing changed" under a count of things done.
    assert "Nothing about your people or projects changed" not in page.locator(".overnight").inner_text()


def test_maintenance_reads_as_one_spaced_line(today):
    page, _, _ = today
    summary = page.locator(".desk-more .maint > summary")
    assert summary.evaluate("node => getComputedStyle(node, '::after').content") in ("none", "normal")
    h2, state = summary.locator("h2").bounding_box(), summary.locator(".n").bounding_box()
    assert abs(h2["y"] - state["y"]) < 4 and state["x"] >= h2["x"] + h2["width"] - 0.5  # one line, label first
    assert summary.locator(".n").evaluate("node => getComputedStyle(node, '::before').content") == '" · "'


def _overlap(a, b):
    return not (a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"]
                or a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"])


def test_on_a_phone_send_never_covers_the_card_at_any_scroll(today):
    page, _, _ = today
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate(OVERDUE, isolated_context=False)
    # A long ask above the draft, as on real data: the draft starts low on the first screen.
    page.evaluate("""async () => {
      const r = byPath('people/ines-halvorsen.md');
      r.original = undefined;
      r.text = r.text.replace(/(^## Open threads[^\\n]*\\n)- [^\\n]*/mi, '$1- ' + 'Inès asked you to confirm the Q3 receipts, the two invoices from the August workshop and whether the van lease counts as a business expense this year, '.repeat(3) + 'due 2026-10-03 [1].');
      KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
    }""", isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    card = page.locator(".qcard.open")
    bar = card.locator(".mail-actions")
    parts = [card.locator(".mail-head"), card.locator(".mail-body"), card.locator(".mail-choices"), card.locator(".qitem .words").first]
    end = page.evaluate("document.documentElement.scrollHeight - innerHeight", isolated_context=False)
    for y in range(0, end + 1, 60):
        page.evaluate(f"scrollTo(0, {y})", isolated_context=False)
        b = bar.bounding_box()
        for part in parts:
            box = part.bounding_box()
            if box and box["height"]:
                assert not _overlap(b, box), (y, part, box, b)
    # It follows the draft: under REM's question, inside the card.
    choices, letter = card.locator(".mail-choices").bounding_box(), card.locator(".mail-card, .mailcard").first.bounding_box()
    b = bar.bounding_box()
    assert b["y"] >= choices["y"] + choices["height"] - 0.5 and b["y"] + b["height"] <= letter["y"] + letter["height"] + 0.5


def test_the_hint_names_the_choice_left_and_a_tap_goes_to_it(today):
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    card = page.locator(".qcard.open")
    hint, send = card.locator(".choose-hint"), card.locator(".mail-actions").get_by_role("button", name="Send", exact=True)
    assert hint.inner_text() == "1 choice left: 邮件附件 / 共享文件夹" and send.is_disabled()
    # The letter's own label names the slot when it has one.
    page.evaluate("""() => { REM.drafts[0].body = 'Hi Ines,\\n\\nFormat: 【需要你：PDF / CSV】\\n\\nAvery'; REM.approval_outcomes[0].body = REM.drafts[0].body; render(); }""",
                  isolated_context=False)
    assert hint.inner_text() == "1 choice left: Format"
    hint.get_by_role("link", name="Format", exact=True).click()
    assert page.evaluate("!!document.activeElement.closest('.owner-slot')", isolated_context=False)
    card.locator(".owner-slot").get_by_role("button", name="CSV").click()
    assert hint.is_hidden() and send.is_enabled()


def test_a_sparse_three_nights_give_the_row_back_and_a_busy_one_keeps_the_chart(today):
    page, _, _ = today
    assert page.locator(".night-card .hyp-wrap").is_visible()  # the fixture's nights hold several runs
    tall = page.locator(".night-card").bounding_box()["height"]
    page.evaluate("""() => { REM.logs = REM.logs.filter(run => Date.parse(REM.as_of) - Date.parse(run.started_at) > 3 * DAY_MS); REM.brief_logs = REM.logs; render(); }""",
                  isolated_context=False)
    card = page.locator(".night-card")
    assert "sparse" in card.get_attribute("class") and card.locator(".hyp-wrap").count() == 0
    assert card.locator(".night-sum").inner_text().startswith("Last 3 days: 0 runs of reading or rewriting")
    assert card.bounding_box()["height"] < tall - 30
    assert page.locator(".deal").count() == int(card.locator(".count").inner_text())
