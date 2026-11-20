"""Today leads with what can be acted on, and every action moves on to the next card (opt in; #3072, #3085).

Owner, 2026-11-17, on his real notebook: Today opened with a schedule «I don't know what to do with»; after
Mark done the page «goes back to that thing»; after Hand to Codex the card sat there saying «handing to Codex»;
he could not tell where a finished item went or when a "not now" would come back. The notebook is the invented
one in tests/fixtures/rem_reader_notebook.py; the calendar events and to-dos below are invented too.
"""

import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
FROZEN = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
EVENTS = [{"id": "e1", "title": "Harbour permit call", "start": "2026-10-01T09:30:00+00:00", "end": "2026-10-01T10:00:00+00:00",
           "location": "Pier 4 office", "people": [], "link": ""},
          {"id": "e2", "title": "Lantern workshop", "start": "2026-10-01T15:00:00+00:00", "end": "2026-10-01T16:30:00+00:00",
           "location": "12 Quay Street", "people": [], "link": ""},
          {"id": "e3", "title": "Glass delivery", "start": "2026-10-02T08:00:00+00:00", "end": "2026-10-02T08:30:00+00:00",
           "location": "", "people": [], "link": ""}]
TODOS = {"tasks": [{"id": "t1", "title": "Renew the harbour permit", "list": "Tasks", "due": "2026-10-03"},
                   {"id": "t2", "title": "Order lantern glass", "list": "Workshop", "due": ""}],
         "read_at": "2026-10-01T02:30:00Z", "google": None, "error": None}

# Mara owes a review two days from now as well, so two people have something due and the deck has cards to deal.
SCENE = r'''async scene => {
  REM.live = true;
  window.clockNow = () => Date.parse(REM.as_of);
  const r = byPath('people/mara-ostrowski.md');
  r.original = undefined;
  r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1- You owe Mara a review of the budget forecast; due 2026-10-02 [4].\n');
  KNOWN.clear(); FACTS.clear(); await refreshTodayQueue();
  REM.day_plan = await planDay(REM.today_queue);
  REM.todos = scene.todos;
  render(); scrollTo(0, 0);
}'''


@contextmanager
def open_today(folder, size=(1440, 900), language="en"):
    """The fixture notebook's live reader at http://rem.test/; every /rem/* request is answered from `answers`."""
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import day_plan, reader as rem_reader, service
    from connectonion.rem.today import queue
    saved = rem_reader.snapshot, service.mail_available
    service.mail_available = lambda kind: False

    def fixed_snapshot(root, local=False, today=False):
        data = saved[0](root, local, today=today)
        data["as_of"] = FROZEN.isoformat()
        data["today_queue"] = queue(root, records=data["records"], contexts=data["source_context"], states=data["threads"], as_of=FROZEN.date())
        return data

    rem_reader.snapshot = fixed_snapshot
    try:
        html = rem_reader.render(build(folder / "rem", FROZEN), local=True)
    finally:
        rem_reader.snapshot, service.mail_available = saved
    calls, answers, errors = [], {}, []

    def serve(route):
        request = route.request
        path = request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/"):
            body = json.loads(request.post_data or "{}") if request.method == "POST" else None
            calls.append((path, body))
            answer = answers.get(path, lambda body: (200, {}))
            status, reply = answer(body)
            return route.fulfill(status=status, body=json.dumps(reply), content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=html, content_type="text/html")
        return route.abort()

    def plan(items):
        return day_plan.build({"read": [{"name": "Outlook", "at": "2026-10-01T02:30:00Z"}], "events": EVENTS, "errors": []},
                              items, {"schedule": {"timezone": "UTC"}}, FROZEN)

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": size[0], "height": size[1]}, locale="en-US", timezone_id="UTC", reduced_motion="reduce")
        page = context.new_page()
        page.expose_function("projectToday", lambda payload: queue(Path(payload["root"]), records=payload["records"],
                             contexts=payload["source_context"], states=payload.get("threads", {}),
                             as_of=datetime.fromisoformat(payload["as_of"]).date()))
        page.expose_function("planDay", plan)
        page.add_init_script("""window.refreshTodayQueue = async () => {
          REM.today_queue = await projectToday({root: REM.root, as_of: REM.as_of, threads: REM.threads,
            records: REM.records.map(r => ({...r, text: r.shown ? r.original ?? r.text : r.text})), source_context: REM.source_context});
          threadEntries.cached = null;
        };""")
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE)
        page.locator(".night-card .count").wait_for()
        page.evaluate(SCENE, {"todos": TODOS}, isolated_context=False)
        if language != "en":
            page.evaluate("language => { setInterfaceLanguage(language); render(); scrollTo(0, 0); }", language, isolated_context=False)
        yield page, calls, answers
        browser.close()
    assert not errors, errors


@pytest.fixture(params=[(1440, 900), (390, 844)], ids=["desktop", "phone"])
def today(tmp_path, request):
    with open_today(tmp_path, request.param) as opened:
        yield opened


@pytest.fixture
def desk(tmp_path):
    with open_today(tmp_path) as opened:
        yield opened


def _top(page, selector):
    return page.locator(selector).first.evaluate("node => node.getBoundingClientRect().top + scrollY")


def _focal(page):
    return page.locator(".today-brief .qcard.focal").get_attribute("data-path")


def _numbers(page):
    """Every count Today prints about what waits on you: the header's, the rail badge's and the phone tab's."""
    return page.evaluate("""() => ({header: document.querySelector('.night-card .count')?.textContent,
      badges: [...document.querySelectorAll('#rail .n, #tabbar .n, nav .n')].filter(node => node.getClientRects().length).map(node => node.textContent)})""",
                         isolated_context=False)


def test_today_opens_on_the_cards_and_the_schedule_comes_after_them(today):
    """#3072: what he can act on comes first. #3152: then the calendar, a component of Today, then the to-dos."""
    page, _, _ = today
    deck, calendar, todos = _top(page, ".today-brief"), _top(page, "#today-calendar"), _top(page, ".day-plan.todos")
    assert deck < calendar < todos, (deck, calendar, todos)
    assert page.locator(".day-plan-proposal").count() == 0  # the day plan is suggested blocks now, not a list
    card = page.locator(".today-brief .qcard.focal")
    assert card.bounding_box()["y"] < page.viewport_size["height"], "the first card is on the first screen"
    assert card.locator(".strip-done").first.is_visible()


def _saved(page):
    page.wait_for_function("() => document.getElementById('thread-save-status')?.textContent.includes('Saved in notebook')")


def _answer_marks(answers):
    """The Host's /rem/thread: it keeps what it was sent and answers with it, as threads.set_state does."""
    answers["/rem/thread"] = lambda body: (200, {} if body is None else {"state": body["state"], "at": "2026-10-01T12:00:05+00:00",
                                                 "keys": body.get("keys") or [body["key"]], **({"until": body["until"]} if body.get("until") else {})})


def test_mark_done_moves_on_to_the_next_card_and_never_back_to_the_first(today):
    """«它又回到那个东西»: he skipped the first card, finished the second, and the deck dealt the first one again."""
    page, calls, answers = today
    _answer_marks(answers)
    order = page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")
    assert order[0] == "people/mara-ostrowski.md" and order[1] == "people/ines-halvorsen.md" and len(order) >= 3
    page.evaluate("path => dealCard(path)", order[1], isolated_context=False)
    page.evaluate("scrollTo(0, 120)", isolated_context=False)
    before, scroll = _numbers(page), page.evaluate("scrollY", isolated_context=False)
    proposals = page.locator("#today-calendar .cal-suggest").count()  # the day plan's suggested blocks (#3152)
    page.locator(".qcard.focal .strip-done").first.click()
    page.locator("#done-notice").wait_for()
    assert _focal(page) == order[2], "the card that followed it is in front"
    assert order[1] not in page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")
    assert page.locator("#today-calendar .cal-suggest").count() == proposals - 1, "its proposed half hour left with it"
    after = _numbers(page)
    assert int(after["header"]) == int(before["header"]) - 1
    assert after["badges"] and set(after["badges"]) == {after["header"]}, after
    _saved(page)
    assert _focal(page) == order[2] and page.evaluate("scrollY", isolated_context=False) == scroll, "the save does not move the page"
    assert [body["state"] for path, body in calls if path == "/rem/thread" and body] == ["done"]


HOLD_TASK = r'''() => {
  const real = window.fetch;
  window.fetch = (url, options) => String(url).endsWith('/rem/task') && JSON.parse(options.body).action === 'run'
    ? new Promise(resolve => { window.releaseTask = () => resolve(real(url, options)); }) : real(url, options);
}'''


def test_hand_to_codex_moves_on_at_once_and_the_work_shows_in_one_place(today):
    """«点了交给 Codex 就显示正在交给 Codex，也不跳到下一张»: the card leaves when he clicks, not when the Host answers."""
    page, calls, answers = today
    answers["/rem/task"] = lambda body: (200, {"id": "task-ines", "result": "running", "agent": "codex", "started_at": "2026-10-01T11:58:00+00:00"}
                                         if body.get("action") in ("run", None, "status") else {"id": "task-ines", "result": "stopped"})
    order = page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")
    page.evaluate("path => dealCard(path)", order[1], isolated_context=False)
    page.evaluate(HOLD_TASK, isolated_context=False)
    page.locator(".qcard.focal [data-agent=codex]").first.click()
    strip = page.locator("#work-strip")
    strip.wait_for()
    assert _focal(page) == order[2], "the next card is in front while the Host has not answered yet"
    assert "Codex is working on 1 thing" in strip.inner_text()
    page.evaluate("releaseTask()", isolated_context=False)
    page.wait_for_function("() => document.getElementById('work-strip')?.textContent.includes('Codex is working on 1 thing')")
    assert "2:00" in strip.inner_text()
    assert _focal(page) == order[2] and page.locator('.qcard[data-path="people/ines-halvorsen.md"]').count() == 0
    if not strip.evaluate("node => node.open"):
        strip.locator("summary").click()
    row = strip.locator(".work-row")
    assert row.count() == 1 and "Q3 receipts" in row.inner_text()
    row.get_by_role("button", name="Take back from Codex").click()
    page.locator('.qcard[data-path="people/ines-halvorsen.md"]').wait_for(state="attached")
    assert page.locator("#work-strip").count() == 0


def test_a_hand_off_the_host_refuses_puts_the_card_back_and_says_why(today):
    page, calls, answers = today
    answers["/rem/task"] = lambda body: (500, {})
    order = page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")
    page.evaluate("path => dealCard(path)", order[1], isolated_context=False)
    page.locator(".qcard.focal [data-agent=codex]").first.click()
    page.wait_for_function("() => document.querySelector('.qcard.focal .hand-failed')")
    assert _focal(page) == order[1], "the card he handed over is back in front"
    words = page.locator(".qcard.focal .hand-failed").inner_text()
    assert "Codex did not take this" in words and "REM is not answering right now" in words
    assert page.locator("#work-strip").count() == 0


def _cards(page):
    return page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")


def test_a_finished_item_says_where_it_went_and_can_be_brought_back(today):
    """«我想把它标成没完成怎么办»: the notice names the list, the list is on Today, and each row comes back."""
    page, calls, answers = today
    _answer_marks(answers)
    order, count = _cards(page), int(_numbers(page)["header"])
    page.evaluate("path => dealCard(path)", order[1], isolated_context=False)
    page.locator(".qcard.focal .strip-done").first.click()
    notice = page.locator("#done-notice")
    notice.wait_for()
    assert notice.inner_text().startswith("Marked done · Undo")
    _saved(page)
    assert notice.inner_text().endswith("Saved in notebook · Finished today: 1")
    notice.get_by_role("button", name="Finished today: 1").click()
    fold = page.locator("#finished-today")
    assert fold.evaluate("node => node.open") and fold.locator("summary").inner_text() == "Finished today: 1"
    row = fold.locator(".closed-row")
    assert "Q3 receipts" in row.inner_text() and "Marked done · " in row.inner_text()
    assert "empties at midnight" in fold.inner_text()
    row.get_by_role("button", name="Bring back", exact=True).click()
    page.locator('.qcard[data-path="people/ines-halvorsen.md"]').wait_for(state="attached")
    assert _focal(page) == order[1], "what he brought back is in front"
    assert page.locator("#finished-today").count() == 0 and int(_numbers(page)["header"]) == count
    assert [body["state"] for path, body in calls if path == "/rem/thread" and body] == ["done", "open"]


def test_the_notice_undo_brings_the_same_card_back_in_front(desk):
    page, calls, answers = desk
    _answer_marks(answers)
    order = _cards(page)
    page.evaluate("path => dealCard(path)", order[1], isolated_context=False)
    page.locator(".qcard.focal .strip-done").first.click()
    page.locator("#done-notice").get_by_role("button", name="Undo", exact=True).click()
    assert _focal(page) == order[1] and page.locator("#finished-today").count() == 0


def test_not_now_asks_when_and_says_when_it_comes_back(today):
    """«暂不处理，我不知道下次怎么给我»: four choices in words, the day it returns, a list of what was put off."""
    page, calls, answers = today
    _answer_marks(answers)
    order = _cards(page)
    page.evaluate("path => dealCard(path)", order[1], isolated_context=False)
    card = page.locator(".qcard.focal")
    card.locator(".strip-later").first.click()
    assert card.locator(".later-choice").all_inner_texts() == ["Tonight", "Tomorrow", "In 3 days", "Next week"]
    assert page.locator("#done-notice").count() == 0 and not [1 for path, body in calls if path == "/rem/thread" and body]
    card.locator(".later-cancel").click()
    assert card.locator(".strip-done").first.is_visible() and card.locator(".later-choice").count() == 0
    card.locator(".strip-later").first.click()
    card.get_by_role("button", name="In 3 days").click()
    notice = page.locator("#done-notice")
    notice.wait_for()
    assert notice.inner_text().startswith("Put off · back on Sun, Oct 4 · Undo")
    assert _focal(page) == order[2] and order[1] not in _cards(page)
    _saved(page)
    sent = [body for path, body in calls if path == "/rem/thread" and body][-1]
    assert sent["state"] == "skipped" and sent["until"] == "2026-10-04T00:00:00.000Z"
    fold = page.locator("#put-off")
    assert fold.locator("summary").inner_text() == "Put off: 1" and page.locator("#finished-today").count() == 0
    fold.locator("summary").click()
    assert "Back on Sun, Oct 4" in fold.locator(".closed-row").inner_text()
    # The day arrives: the card is back by itself and says it was put off, and on what day.
    page.evaluate("() => { window.clockNow = () => Date.parse('2026-10-04T08:00:00Z'); render(); }", isolated_context=False)
    back = page.locator('.qcard[data-path="people/ines-halvorsen.md"]')
    assert back.count() == 1 and page.locator("#put-off").count() == 0
    assert "You put this off on Oct 1; it is back as you asked." in back.locator(".put-off-note").text_content()


def test_a_put_off_item_can_be_brought_back_now(desk):
    page, calls, answers = desk
    _answer_marks(answers)
    order = _cards(page)
    page.evaluate("path => dealCard(path)", order[1], isolated_context=False)
    page.locator(".qcard.focal .strip-later").first.click()
    page.locator(".qcard.focal").get_by_role("button", name="Tonight").click()
    assert page.locator("#done-notice").inner_text().startswith("Put off · back tonight at 06:00 PM · Undo")
    page.locator("#put-off summary").click()
    page.locator("#put-off").get_by_role("button", name="Bring back now").click()
    assert _focal(page) == order[1] and page.locator("#put-off").count() == 0


def test_show_more_opens_the_items_context_and_closing_returns_to_the_same_card(today):
    """#3072, context as a second level: a panel at the side on a wide page, a sheet from the foot of a phone."""
    page, _, _ = today
    order = _cards(page)
    card = page.locator(".qcard.focal")
    strip = card.locator(".handoff-line").first.locator(":scope > button").all_inner_texts()
    assert strip == ["Mark done", "Not now", "Ignore", "Hand to Codex", "Hand to Claude", "Show more"], strip
    card.locator(".strip-more").first.click()
    sheet = page.locator("#item-context")
    assert sheet.evaluate("node => node.open")
    words = sheet.inner_text()
    for heading in ("Why it is here", "The message", "Related", "Talk it over"):
        assert heading in words, heading
    assert "Mara has waited since" in words and "Mara Ostrowski · Person" in words and "Fernhill Labs · Organisation" in words
    assert sheet.locator(".context-excerpt").count() >= 1 and sheet.locator("[data-talk]").count() == 2
    box, view = sheet.bounding_box(), page.viewport_size
    if view["width"] > 640:
        assert box["x"] + box["width"] == view["width"] and box["height"] == view["height"] and box["width"] <= 460
    else:
        assert box["width"] == view["width"] and round(box["y"] + box["height"]) == view["height"]
    sheet.get_by_role("button", name="Close").click()
    assert page.locator("#item-context").count() == 0 and _focal(page) == order[0]
    assert page.evaluate("document.activeElement.classList.contains('strip-more')", isolated_context=False)


ZH_PAGE = r"""() => {
  const r = byPath('people/ines-halvorsen.md');
  r.translations = {zh: r.text.replace(/(^## Open threads[^\n]*\n)- [^\n]*/mi, '$1- 她在等你发第三季度的收据；从 2026-09-19 起你一直欠着，她要在 2026-10-03 前报税 [4]。')};
  setInterfaceLanguage('zh'); render(); scrollTo(0, 0);
}"""


def test_in_chinese_the_item_and_its_proposal_use_the_translated_page(desk):
    """#3072: with the reader in 中文 the rows stayed English although the page's translation held the line."""
    page, _, _ = desk
    page.evaluate(ZH_PAGE, isolated_context=False)
    page.evaluate("dealCard('people/ines-halvorsen.md')", isolated_context=False)
    card = page.locator(".qcard.focal")
    assert "她在等你发第三季度的收据" in card.locator(".words").first.inner_text()
    assert card.locator(".words .lang-status").count() == 0, "a translated row is not marked 原文"
    proposals = page.locator("#today-calendar .cal-suggest .cal-ev-title").all_inner_texts()
    assert any("她在等你发第三季度的收据" in text for text in proposals), proposals
    # A page with no translation shows its own words, marked 原文: nothing is made up.
    page.evaluate("dealCard('people/mara-ostrowski.md')", isolated_context=False)
    assert page.locator(".qcard.focal .words .lang-status").first.inner_text() == "原文"


LATIN = r"""() => [...document.querySelectorAll('#main :is(button, summary, h1, h2, h3, .day-plan-when, .count-words, .quiet-line, .kind-badge, .qage), #done-notice, #work-strip > summary')]
  .filter(node => node.getClientRects().length).map(node => [...node.childNodes].filter(child => child.nodeType === 3).map(child => child.textContent).join('').trim())
  .filter(text => /[A-Za-z]{3,}/.test(text.replace(/Codex|Claude|REM|Gmail|Outlook|Microsoft To Do|UTC|co rem/g, '')))"""


def test_in_chinese_every_word_the_reader_writes_on_today_is_chinese(today):
    page, _, answers = today
    _answer_marks(answers)
    answers["/rem/task"] = lambda body: (200, {"id": "task-1", "result": "running", "agent": "codex", "started_at": "2026-10-01T11:58:00+00:00"})
    page.evaluate("() => { setInterfaceLanguage('zh'); render(); scrollTo(0, 0); }", isolated_context=False)
    assert page.evaluate(LATIN, isolated_context=False) == []
    page.locator(".qcard.focal .strip-later").first.click()
    assert page.evaluate(LATIN, isolated_context=False) == []
    page.locator(".qcard.focal .later-choice").nth(1).click()
    page.locator("#done-notice").wait_for()
    page.locator(".qcard.focal [data-agent=codex]").first.click()
    page.locator("#work-strip").wait_for()
    for fold in page.locator("#today-closed summary, #work-strip summary").all():
        fold.click()
    assert page.evaluate(LATIN, isolated_context=False) == []
    assert page.locator("#put-off summary").inner_text() == "已推后：1"


def test_the_numbers_on_today_are_one_number_or_say_what_they_count(today):
    """#3071, #3085: the header, the rail badge and Waiting on you's own heading are the same count, before and after a close."""
    page, _, answers = today
    _answer_marks(answers)

    def waiting():
        return page.evaluate("""() => { const all = threadEntries().filter(entry => !isDone(entry)); return all.filter(waitingOnYou).length; }""", isolated_context=False)

    for step in range(2):
        numbers = _numbers(page)
        assert set(numbers["badges"]) == {numbers["header"]} and int(numbers["header"]) == waiting(), numbers
        if not step:
            page.locator(".qcard.focal .strip-done").first.click()
            page.locator("#done-notice").wait_for()
    # Fewer cards than items: the deck says so in words, with the same total.
    page.evaluate("""() => { const real = todayGroups; window.todayGroups = entries => real(entries).slice(0, 1).map(group => ({...group, entries: group.entries.slice(0, 1)})); render(); }""", isolated_context=False)
    total = _numbers(page)["header"]
    assert page.locator(".deck-rest").inner_text() == f"This card is the most pressing 1 of the {total} waiting on you. See all {total} →"


def test_a_page_that_has_lost_its_host_says_how_to_act(desk):
    """The click cannot start anything: the card comes back and says the Host is gone, never «handing» or «busy» (#3139)."""
    page, _, _ = desk
    page.evaluate("() => { window.fetch = () => Promise.reject(new TypeError('Failed to fetch')); }", isolated_context=False)
    page.locator(".qcard.focal [data-agent=codex]").first.click()
    page.wait_for_function("() => document.querySelector('.qcard.focal .hand-failed')")
    words = page.locator(".qcard.focal .hand-failed").first.inner_text()
    assert "nothing was handed over" in words and "lost touch with REM" in words
    assert page.locator("#host-lost").get_by_role("button", name="Reconnect").is_visible()


def test_a_snapshot_says_in_words_that_it_cannot_act_and_never_appears_to_start(desk):
    """D-60 keeps commands off the page, so the words are "open REM", with the live reader's link when there is one."""
    page, calls, _ = desk
    page.evaluate("() => { REM.live = false; REM.live_link = 'http://127.0.0.1:8000/rem'; render(); }", isolated_context=False)
    card = page.locator(".qcard.focal")
    assert card.locator("[data-agent=codex]").first.is_disabled() and card.locator(".strip-done").first.is_disabled()
    assert card.locator(".close-why").inner_text() == "This is an offline snapshot; open REM to mark it. Open the live reader"
    assert "handing work to an agent happen in the live reader" in page.locator(".snapshot-line").inner_text()
    card.locator("[data-agent=codex]").first.click(force=True)
    assert page.locator("#work-strip, #today-closed").count() == 0 and not [1 for path, _ in calls if path == "/rem/task"]


def _open_list(page):
    page.evaluate("location.hash = '#view=open'", isolated_context=False)
    page.locator(".open-chips").wait_for()


def _chips(page):
    return [" ".join(text.split()) for text in page.locator(".open-chips .chip").all_inner_texts()]


def test_the_open_list_filters_by_a_chip_and_closes_everything_it_shows_at_once(today):
    """«未完成的事为什么不把标签放上面让我筛选…一键全选标完成»: chips in words with counts, one bulk action, one Undo."""
    page, calls, answers = today
    _answer_marks(answers)
    _open_list(page)
    assert _chips(page) == ["All", "I still owe a reply or an action 5", "Fernhill Labs 4", "Harbour 2"]
    rows = page.locator(".task-band ul.threads > li")
    everything = rows.count()
    assert page.locator(".bulk-bar").count() == 0, "no bulk action without a filter"
    page.locator(".open-chips .chip", has_text="Fernhill Labs").click()
    assert rows.count() == 4 and page.locator(".open-chips .chip.on").inner_text().split() == ["Fernhill", "Labs", "4"]
    heads = page.locator(".task-band h2 .n").all_inner_texts()
    assert sum(map(int, heads)) == 4, "each heading counts the rows under it"
    if page.viewport_size["width"] < 640:
        chips = page.locator(".open-chips")
        tops = {round(chip.bounding_box()["y"]) for chip in chips.locator(".chip").all()}
        assert len(tops) == 1 and page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False), "one row, scrolled sideways"
    page.get_by_role("button", name="Mark all 4 done").click()
    notice = page.locator("#done-notice")
    notice.wait_for()
    assert notice.inner_text().startswith("4 marked done · Undo")
    page.wait_for_function("() => document.getElementById('done-notice')?.textContent.includes('Saved in notebook')")
    assert [body["state"] for path, body in calls if path == "/rem/thread" and body] == ["done"] * 4
    assert "Nothing open under this filter" in page.locator("#main").inner_text()
    notice.get_by_role("button", name="Undo", exact=True).click()
    page.locator(".task-band ul.threads > li").first.wait_for()
    assert rows.count() == 4
    page.locator(".open-chips .chip.on").click()  # a second tap clears
    page.wait_for_function("n => document.querySelectorAll('.task-band ul.threads > li').length === n", arg=everything, timeout=5000)
    assert rows.count() == everything and "tag=" not in page.url


def test_a_filtered_list_can_be_put_off_to_one_day(desk):
    page, calls, answers = desk
    _answer_marks(answers)
    _open_list(page)
    page.locator(".open-chips .chip", has_text="Harbour").click()
    page.get_by_role("button", name="Put all 2 off until…").click()
    page.locator(".bulk-bar").get_by_role("button", name="Next week").click()
    assert page.locator("#done-notice").inner_text().startswith("2 put off · back on Mon, Oct 5 · Undo")
    page.wait_for_function("() => document.getElementById('done-notice')?.textContent.includes('Saved in notebook')")
    sent = [body for path, body in calls if path == "/rem/thread" and body]
    assert [body["state"] for body in sent] == ["skipped"] * 2 and {body["until"] for body in sent} == {"2026-10-05T00:00:00.000Z"}


def test_threads_he_already_answered_are_a_filter_of_their_own(desk):
    """His second example is a state: «我都回复了，等他们» is not «还等我回»."""
    page, _, _ = desk
    page.evaluate("""() => { const row = REM.today_queue.find(row => row.record === 'people/ines-halvorsen.md');
      row.reply = {...row.reply, state: 'replied', last_word_yours: true}; row.due = ''; threadEntries.cached = null; }""", isolated_context=False)
    _open_list(page)
    chips = _chips(page)
    assert "I replied, waiting on them 1" in chips and "I still owe a reply or an action 4" in chips, chips
    page.locator(".open-chips .chip", has_text="I replied").click()
    rows = page.locator(".task-band ul.threads > li")
    assert rows.count() == 1 and "Q3 receipts" in rows.first.inner_text()


def test_a_hand_off_shows_what_the_agent_is_doing_and_can_be_watched_then_continued(today):
    """#3138 (owner, 2026-11-19): see the progress, and pick the session up in Terminal or the agent itself."""
    page, calls, answers = today
    state = {"done": False}

    def task(body):
        if state["done"]:
            return 200, {"id": "task-ines", "result": "completed", "agent": "codex", "finished_at": "2026-10-01T12:06:00+00:00",
                         "session_id": "01a1bda7-ca66-7640-88ca-79eb9b66e649", "deliverable": "/tmp/x.md", "last_message": "/tmp/last.md"}
        return 200, {"id": "task-ines", "result": "running", "agent": "codex", "started_at": "2026-10-01T11:58:00+00:00",
                     "tmux": "rem-task-ines", "steps": 3, "step": {"at": "2026-10-01T12:00:00+00:00", "status": "running",
                                                                    "summary": "Running the requested tests"}}
    answers["/rem/task"] = task
    order = page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")
    page.evaluate("path => dealCard(path)", order[1], isolated_context=False)
    page.locator(".qcard.focal [data-agent=codex]").first.click()
    strip = page.locator("#work-strip")
    page.wait_for_function("() => document.getElementById('work-strip')?.textContent.includes('Codex is working on 1 thing')")
    if not strip.evaluate("node => node.open"):
        strip.locator("summary").click()
    row = strip.locator(".work-row")
    row.get_by_text("Running the requested tests").wait_for()  # the step, in words, while it runs
    shots = os.environ.get("CO_REM_PR_SHOTS")
    if shots:
        page.screenshot(path=os.path.join(shots, f"handoff-running-{page.viewport_size['width']}.png"))
    row.get_by_role("button", name="Watch in Terminal").click()
    page.wait_for_function("() => true")
    assert ("/rem/task", {"id": "task-ines", "action": "watch"}) in calls
    state["done"] = True
    page.wait_for_function("() => document.getElementById('work-strip')?.textContent.includes('Codex finished')", timeout=15000)
    strip = page.locator("#work-strip")
    if not strip.evaluate("node => node.open"):
        strip.locator("summary").click()
    strip.locator(".work-row").get_by_role("button", name="Continue in Codex").click()
    page.wait_for_function("() => true")
    assert ("/rem/task", {"id": "task-ines", "action": "resume"}) in calls
    if shots:
        page.screenshot(path=os.path.join(shots, f"handoff-finished-{page.viewport_size['width']}.png"))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
