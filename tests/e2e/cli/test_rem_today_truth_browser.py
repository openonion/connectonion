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


def _open_stale(page):
    """Sprint 14: the stale promises are one folded line under the desk; it opens in place."""
    summary = page.locator("#today-stale > summary")
    if page.locator("#today-stale").get_attribute("open") is None:
        summary.click()


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
    assert page.locator("#today-stale > summary").inner_text() == "1 has gone quiet for a long time · Look"
    _open_stale(page)
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
    _open_stale(page)
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
    # Its count is the side line's, so the two read as one story.
    side = page.locator(".side .closed").inner_text()
    n = side.split("handled ")[1].split()[0] if "handled " in side else ""
    assert card.locator(".night-sum").inner_text() == ("Last 3 days: no mail read and no page rewritten"
                                                         + (f"; REM handled {n} things in Today" if n else ""))
    assert card.bounding_box()["height"] < tall - 30
    assert page.locator(".deal").count() == int(card.locator(".count").inner_text())


@pytest.mark.parametrize("size", [(1440, 900), (390, 844)])
def test_every_row_says_its_three_ways_to_close_in_words_without_a_hover(today, size):
    """Owner, 2026-11-12: «为什么没有标记为做完的按钮呢？», «你要有个文字按钮», «忽略和标记完成很重要，有的任务就是线下说了，
    或者现在不需要处理，或者广告要忽略». Each row of the open card says 标为完成 · 暂不处理 · 忽略 on screen, read as text
    on the untouched page; one tap acts, and the notice says the new state in words with Undo."""
    page, calls, answers = today
    answers["/rem/thread"] = lambda body: (200, {"state": body["state"], "at": "2026-10-08T12:00:00+00:00", "device": body["device"], "keys": body["keys"]})
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate("() => { REM.live = true; render(); dealCard('people/mara-ostrowski.md'); scrollTo(0, 0); }", isolated_context=False)
    page.mouse.move(0, 0)
    rows = page.locator(".today-brief .qcard.open .qitem:visible")
    assert rows.count() >= 1
    # Found the way the owner finds them: buttons by their visible words, nothing by class.
    words = lambda names: [rows.nth(i).get_by_role("button", name=name, exact=True) for i in range(rows.count()) for name in names]
    assert all(b.count() == 1 and b.is_visible() for b in words(["Mark done", "Not now", "Ignore"]))
    page.evaluate("() => { setInterfaceLanguage('zh'); }", isolated_context=False)
    page.mouse.move(0, 0)
    assert all(b.count() == 1 and b.is_visible() for b in words(["标为完成", "暂不处理", "忽略"]))
    row = rows.first
    states = lambda: [body["state"] for path, body in calls if path == "/rem/thread" and body]
    row.get_by_role("button", name="忽略", exact=True).click()
    # Ignore is its own state, so the notice and every later line say 已忽略, never 已完成.
    assert page.locator("#done-notice").inner_text().startswith("已忽略 · 这一条不会再回来 · 撤销") and states()[-1] == "ignored"
    page.locator("#done-notice").get_by_role("button", name="撤销").click()
    row = page.locator(".today-brief .qcard.open .qitem:visible").first
    row.get_by_role("button", name="暂不处理", exact=True).click()
    assert page.locator("#done-notice").inner_text().startswith("暂不处理 · 有新邮件会回来 · 撤销") and states()[-1] == "skipped"
    page.locator("#done-notice").get_by_role("button", name="撤销").click()
    page.locator(".today-brief .qcard.open .qitem:visible").first.get_by_role("button", name="忽略", exact=True).click()
    page.evaluate("() => { location.hash = '#view=open'; }", isolated_context=False)
    closed = page.locator("#done-today summary")
    closed.wait_for()
    assert closed.inner_text().startswith("已忽略") and "已完成" not in closed.inner_text()


def test_all_three_closes_leave_the_way_mark_done_does(today):
    """Not now and Ignore called setDone directly, so their row jumped away while Mark done's slid out."""
    page, _, answers = today
    answers["/rem/thread"] = lambda body: (200, {"state": body["state"], "at": "2026-10-08T12:00:00+00:00", "device": body["device"], "keys": body["keys"]})
    page.emulate_media(reduced_motion="no-preference")
    page.evaluate(OVERDUE, isolated_context=False)
    for name in ("Mark done", "Not now", "Ignore"):
        page.evaluate("() => { REM.live = true; render(); dealCard('people/mara-ostrowski.md'); scrollTo(0, 0); }", isolated_context=False)
        row = page.locator(".today-brief .qcard.open .qitem:visible").first
        row.get_by_role("button", name=name, exact=True).click()
        assert page.locator(".today-brief .leaving").count() == 1, name
        page.locator("#done-notice").get_by_role("button", name="Undo").click()


def test_the_stale_widgets_more_link_opens_gone_quiet_and_shows_it(today):
    """The link said "in Open threads" and opened Waiting with the promises folded away in Gone quiet."""
    page, _, _ = today
    page.evaluate(r"""async () => {
      const r = byPath('people/tomas-reyes.md');
      r.original = undefined;
      const lines = [1, 2, 3, 4, 5].map(n => `- You owe Tomás signed form ${n} for the van; requested 2026-04-1${n}, due 2026-04-2${n}.`).join('\n');
      r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1' + lines + '\n');
      KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
    }""", isolated_context=False)
    _open_stale(page)
    more = page.get_by_role("link", name="2 more in Gone quiet →")
    more.click()
    quiet = page.locator("#gone-quiet")
    page.wait_for_function("() => document.getElementById('gone-quiet')?.open")
    box = quiet.bounding_box()
    assert 0 <= box["y"] < page.viewport_size["height"]
    assert quiet.get_by_text("signed form 5 for the van").first.is_visible()


# Asked 3 July, due 23 July (70 days late on 1 October), and Tomás wrote on the thread last week ([9], 28 September).
RECENT_WORD = r'''async () => {
  const r = byPath('people/tomas-reyes.md');
  r.original = undefined;
  REM.source_context['gmail:fixture-van'] = {source: 'gmail', time: '2026-09-28T09:00:00Z', excerpt: 'About the van.'};
  r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1- You owe Tomás the signed van agreement; requested 2026-07-03, due 2026-07-23 [9].\n')
    .replace(/(^## Sources[^\n]*\n)/mi, '$1- [9] gmail:fixture-van — the van; confidence high; observed 2026-09-28.\n');
  KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
}'''


def test_a_late_promise_with_a_message_last_week_stays_live_on_today_and_projects(today):
    """Review of 132fc6b20: Projects read the request day, Today the thread's last message, so one promise was red
    on Today and "may be over" on Projects. Both read the last cited message now."""
    page, _, _ = today
    page.evaluate(RECENT_WORD, isolated_context=False)
    assert page.evaluate("threadEntries().find(e => /van agreement/.test(e.t.text)).t.since", isolated_context=False) == "2026-09-28"
    assert "70 d" in _faces(page) and page.locator(f'#today-stale li[data-path="{TOMAS}"]').count() == 0
    page.evaluate("""() => {
      const r = REM.records.find(r => r.category === 'projects');
      r.open = [{kind: 'owed', due: '2026-07-23', since: '2026-07-03', who: 'people/tomas-reyes.md', text: 'The user owes Tomás the van agreement',
        sources: [{source: 'gmail:fixture-van'}], promised: []}];
      location.hash = '#c=projects';
    }""", isolated_context=False)
    lede = page.locator(".pd-lede")
    lede.wait_for()
    assert "is 70 days late" in lede.locator(".red").inner_text() and lede.locator(".pd-asked").count() == 0


def test_a_promise_with_no_dated_message_stays_live(today):
    page, _, _ = today
    page.evaluate(r'''async () => {
      const r = byPath('people/tomas-reyes.md');
      r.original = undefined;
      r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1- You owe Tomás the signed van agreement; due 2026-04-14.\n');
      KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
    }''', isolated_context=False)
    assert page.evaluate("threadEntries().find(e => /van agreement/.test(e.t.text)).t.since", isolated_context=False) == ""
    assert page.locator("#today-stale").count() == 0 and "170 d" in _faces(page)


def test_still_open_holds_for_sixty_days_then_today_asks_again(today):
    page, _, _ = today
    page.evaluate(ANCIENT, isolated_context=False)
    _open_stale(page)
    page.locator(f'#today-stale li[data-path="{TOMAS}"]').get_by_role("button", name="Still open", exact=True).click()
    assert page.locator("#today-stale").count() == 0
    kept = page.evaluate("JSON.parse(localStorage.getItem(keptOpenStorageKey()))", isolated_context=False)
    assert list(kept.values()) == ["2026-10-01"]
    page.evaluate("() => { REM.as_of = '2026-12-05T12:00:00Z'; threadEntries.cached = null; render(); }", isolated_context=False)
    assert page.locator(f'#today-stale li[data-path="{TOMAS}"]').count() == 1


def test_a_stale_promise_is_never_red_or_waiting_one_click_away(today):
    page, _, _ = today
    before = page.evaluate("threadCounts().mine", isolated_context=False)
    page.evaluate(ANCIENT, isolated_context=False)
    assert page.evaluate("threadCounts().mine", isolated_context=False) == before
    assert page.evaluate("waitingOn(byPath('people/tomas-reyes.md')).every(e => !/loan agreement/.test(e.t.text))", isolated_context=False)
    page.locator("#today-stale a.stale-more, #today-stale").first.wait_for()
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    page.locator(".task-band").first.wait_for()
    assert page.locator(".task-band li").filter(has_text="loan agreement").count() == 0
    page.locator("#gone-quiet summary").click()
    row = page.locator("#gone-quiet li").filter(has_text="loan agreement")
    assert row.count() == 1 and row.locator(".when.overdue").count() == 0
