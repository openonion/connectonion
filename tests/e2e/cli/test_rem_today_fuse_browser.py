"""Today drawn as a fuse, with 交给 Codex / 交给 Claude on every pending row (opt in).

Owner, 2026-11-09: «我还是现在倾向于导火索这个方向» (D-108), and «所有待处理的事项，我觉得都应该增加
一个按钮，就是发送给 Codex 去解决，或者发送给 Claude 去解决». The page is served over http from a
Playwright route so the reader's own fetch() reaches a stub; the stub lives here, never in the reader.
The notebook is the invented one in tests/fixtures/rem_reader_notebook.py.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
GREEN = ("rgb(34, 210, 122)", "rgb(59, 227, 143)")

# Ines is overdue five days (due 3 Oct), Mara two (a review due 6 Oct); Fernhill Labs and Harbour carry no due date.
OVERDUE = r'''async () => {
  REM.as_of = '2026-10-08T12:00:00Z';
  const r = byPath('people/mara-ostrowski.md');
  r.original = undefined;
  r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1- You owe Mara a review of the budget forecast; due 2026-10-06 [4].\n');
  KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
}'''

# A prepared reply for the first card, and the approval outcome the Host would list for it.
DRAFT = r'''live => {
  REM.live = live;
  REM.source_context['outlook:3d5f7b9e1a0c'] = {...REM.source_context['outlook:3d5f7b9e1a0c'], source: 'outlook', thread: 'mail:fixture:ines'};
  REM.drafts = [{id: 'ines-receipts', version: 'v1', provider: 'outlook', thread: 'mail:fixture:ines', status: 'prepared',
    to: 'Ines Halvorsen <ines@example.test>', from: 'avery@example.test', subject: 'Re: Q3 receipts',
    body: 'Hi Ines,\n\nThe Q3 receipts are attached. 【需要你：邮件附件 / 共享文件夹 — date not agreed】\n\nAvery',
    gist: '把第三季度的收据发给她。', why: 'She files the return soon.'}];
  REM.approval_outcomes = [{id: 'reply:ines', kind: 'reply', draft_id: 'ines-receipts', version: 'v1',
    to: 'ines@example.test', subject: 'Re: Q3 receipts', body: REM.drafts[0].body, keys: [], title: 'Ines Halvorsen', blocked: true}];
  render();
}'''


@pytest.fixture
def today(tmp_path, monkeypatch):
    """The fixture notebook's reader at http://rem.test/, with every /rem/* request answered by `answers`."""
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    from connectonion.rem.today import queue
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        data = snapshot(root, local, today=today)
        data["as_of"] = frozen.isoformat()
        data["today_queue"] = queue(root, records=data["records"], contexts=data["source_context"], states=data["threads"], as_of=frozen.date())
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    html = rem_reader.render(build(tmp_path / "rem", frozen), local=True)
    calls, answers, errors = [], {}, []

    def serve(route):
        request = route.request
        path = request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/"):
            body = json.loads(request.post_data or "{}") if request.method == "POST" else None
            calls.append((path, body))
            status, reply = answers.get(path, [(200, {})])[0] if not callable(answers.get(path)) else answers[path](body)
            if isinstance(answers.get(path), list) and len(answers[path]) > 1:
                answers[path].pop(0)
            return route.fulfill(status=status, body=json.dumps(reply), content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=html, content_type="text/html")
        return route.abort()

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        page.expose_function("projectToday", lambda payload: queue(Path(payload["root"]), records=payload["records"],
                             contexts=payload["source_context"], states=payload.get("threads", {}),
                             as_of=datetime.fromisoformat(payload["as_of"]).date()))
        page.add_init_script("""window.refreshTodayQueue = async () => {
          REM.today_queue = await projectToday({root: REM.root, as_of: REM.as_of, threads: REM.threads,
            records: REM.records.map(r => ({...r, text: r.shown ? r.original ?? r.text : r.text})), source_context: REM.source_context});
          threadEntries.cached = null;
        };""")
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE)
        page.locator(".brief-header h1").wait_for()
        yield page, calls, answers
        browser.close()
    assert not errors, errors


def _box_inside(page, locator, margin):
    box, view = locator.bounding_box(), page.viewport_size
    return (box["x"] >= margin and box["y"] >= margin and box["x"] + box["width"] <= view["width"] - margin
            and box["y"] + box["height"] <= view["height"] - margin)


def _greens(page):
    return page.evaluate("""green => [...document.querySelectorAll('#main *')].filter(node => {
      const box = node.getBoundingClientRect();
      return box.width > 0 && box.height > 0 && green.includes(getComputedStyle(node).backgroundColor);
    }).map(node => node.textContent.trim())""", list(GREEN), isolated_context=False)


@pytest.mark.parametrize("size", [(1440, 900), (390, 844)])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_send_is_the_only_green_and_sits_well_inside_the_first_screen(today, size, theme):
    page, _, _ = today
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.emulate_media(color_scheme=theme)
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("scrollTo(0, 0)", isolated_context=False)
    send = page.locator(".qcard.open .mail-actions").get_by_role("button", name="Send", exact=True)
    assert send.is_visible()
    assert _box_inside(page, send, 16), (send.bounding_box(), size)
    # The fill-in box is a row of choices above Send, outside the letter's scroll window, built from the slot's
    # own words; until it is answered Send waits, with a plain hint (build 3b re-review).
    choose = page.locator(".qcard.open .mail-choices .owner-slot")
    assert choose.get_attribute("role") == "group" and _box_inside(page, choose, 0)
    assert choose.get_by_role("button").all_inner_texts() == ["邮件附件", "共享文件夹"]
    assert send.is_disabled() and page.locator(".qcard.open .choose-hint").is_visible()
    assert _greens(page) == []
    choose.get_by_role("button", name="邮件附件").click()
    assert send.is_enabled() and not page.locator(".qcard.open .choose-hint").is_visible()
    assert "邮件附件" in page.locator(".qcard.open .mail-text .slot-ref").inner_text()
    assert _greens(page) == ["Send"]
    assert page.locator(".qcard.open .mail-row").filter(has_text="CC").count() == 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)


def test_fuse_lanes_are_the_waiting_people_and_red_follows_the_days_overdue(today):
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    lanes = page.locator(".fuse .lane")
    headline = page.locator(".brief-header h1 .count").inner_text()
    people = page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")
    assert lanes.evaluate_all("lanes => lanes.map(lane => lane.dataset.path)") == people  # no draft: one order
    assert int(headline) == len(people) == lanes.count()
    assert page.locator(".fuse .lane.current").get_attribute("data-path") == people[0]
    ines, mara = (page.locator(f'.fuse .lane[data-path="people/{name}.md"] .burn') for name in ("ines-halvorsen", "mara-ostrowski"))
    assert abs(ines.bounding_box()["width"] / mara.bounding_box()["width"] - 5 / 2) < 0.05
    assert page.locator('.fuse .lane[data-path="people/ines-halvorsen.md"] .late').inner_text() == "5 days overdue"
    undated = page.locator('.fuse .lane[data-path="projects/harbour.md"]')
    assert undated.locator(".burn").count() == 0 and undated.locator(".late").inner_text() == "No due date"
    # One number says one thing (TOP10 #9): the other count names its unit.
    assert "items waiting on you" in page.locator(".brief-header .waiting-more").inner_text()


def test_the_card_with_a_ready_reply_leads_while_the_lanes_keep_their_order(today):
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate("""() => { REM.live = true;
      REM.drafts = [{id: 'mara', version: 'v1', provider: 'outlook', thread: 'mail:fixture:harbour-renewal', status: 'prepared',
        to: 'Mara Ostrowski <mara@example.test>', from: 'avery@example.test', subject: 'Re: Addendum', body: 'Signed today.'}];
      render(); }""", isolated_context=False)
    lanes = page.locator(".fuse .lane").evaluate_all("lanes => lanes.map(lane => lane.dataset.path)")
    cards = page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")
    assert cards[0] == "people/mara-ostrowski.md" and lanes[0] == "people/ines-halvorsen.md"
    assert sorted(lanes) == sorted(cards) and cards[1:] == [path for path in lanes if path != cards[0]]
    assert page.locator(".fuse .lane.current").get_attribute("data-path") == cards[0]
    assert page.locator(".qcard.open").get_attribute("data-path") == cards[0]


def test_every_pending_row_offers_codex_and_claude_quietly(today):
    page, _, _ = today
    page.evaluate("() => { REM.live = true; render(); }", isolated_context=False)
    rows = page.locator(".today-brief .qitem")
    assert rows.count() >= 4
    for i in range(rows.count()):
        names = rows.nth(i).locator(".handoff-line > button").all_text_contents()
        assert names == ["Hand to Codex", "Hand to Claude"]
    page.goto(BASE + "#view=open")
    mine = page.locator(".task-band").first.locator(".thread")
    assert mine.count() >= 1
    for i in range(mine.count()):
        assert mine.nth(i).locator(".handoff-line > button").all_text_contents() == ["Hand to Codex", "Hand to Claude"]
        assert " ".join(mine.nth(i).locator(".talk-menu > summary").inner_text().split()) == "Talk it over ▾"
    page.locator(".task-band .thread .handoff button").first.wait_for()
    fills = page.locator(".handoff button").evaluate_all("nodes => nodes.map(node => getComputedStyle(node).backgroundColor)")
    assert not set(fills) & set(GREEN)


def test_a_hand_off_posts_the_item_key_and_agent_then_shows_progress_and_plain_errors(today):
    page, calls, answers = today
    page.evaluate("() => { REM.live = true; setInterfaceLanguage('zh'); render(); }", isolated_context=False)
    card = page.locator(".today-brief .qcard").first
    key = page.evaluate("obligationKey(todayGroups(threadEntries().filter(e => !isDone(e)))[0].entries[0])", isolated_context=False)
    answers["/rem/task"] = [(200, {"id": "a1b2", "result": "starting", "agent": "claude", "by": "owner"})]
    card.locator(".handoff").get_by_role("button", name="交给 Claude").click()
    card.get_by_text("Claude 正在做").wait_for()
    assert calls[-1] == ("/rem/task", {"action": "run", "key": key, "agent": "claude"})
    assert card.get_by_role("button", name="停止").is_visible()
    answers["/rem/task"] = [(400, {"error": "Expected the item key and agent codex or claude"})]
    second = page.locator(".today-brief .qcard").nth(1)
    second.click()
    second.locator(".handoff").get_by_role("button", name="交给 Codex").click()
    second.get_by_text("REM 认不出这件事。请刷新页面再试。").wait_for()
    assert calls[-1][1]["agent"] == "codex"
    assert "Expected the item key" not in second.inner_text()


SNAPSHOT_LINE = "This is a snapshot: sending and handing work to an agent happen in the live reader."
NO_COMMAND = r"""() => {
  const text = document.body.innerText;
  // "co rem" alone is the product's name in the sidebar; a command is the name followed by flags or a verb.
  const found = text.match(/\bco (?:rem|ai)(?: --?[a-z][\w-]*(?: \S+)?)* (?:open|start|list|investigate|backfill|config|task|run)\b/g) || [];
  return {cmd: document.querySelectorAll('.cmd, code').length, words: found};
}"""


@pytest.mark.parametrize("route", ["", "#view=open"])
def test_a_snapshot_offers_no_command_anywhere_and_says_why_once(today, route):
    """D-60: never ask the owner to copy a command. A snapshot shows the work, disabled, with one plain line."""
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, False, isolated_context=False)
    page.evaluate("""() => { REM.status.schedule_failure = {code: 'blocked', evidence: 'mailbox locked'};
      REM.records.find(r => r.category === 'people').private_project = true; render(); }""", isolated_context=False)
    if route:
        page.goto(BASE + route)
    page.locator(".handoff").first.wait_for(state="attached")
    page.locator(".reader-settings > summary").click()
    assert page.evaluate(NO_COMMAND, isolated_context=False) == {"cmd": 0, "words": []}
    assert page.get_by_text(SNAPSHOT_LINE, exact=True).count() == 1
    assert page.locator(".handoff button:not(:disabled)").count() == 0
    assert page.locator(".handoff-status").evaluate_all("nodes => nodes.map(n => n.textContent).join('')") == ""
    if not route:
        send = page.locator(".qcard.open .mail-actions").get_by_role("button", name="Send", exact=True)
        assert send.is_disabled()
        assert not set(_greens(page)) & {"Send"}
    html = page.content()
    assert "does not run" not in html and "暂不自动" not in html


@pytest.mark.parametrize("size", [(1440, 900), (390, 844)])
def test_send_never_covers_the_draft_head_or_the_choice_row(today, size):
    """D-10: To, Subject and Send all readable at once; on a phone the pinned Send bar covers neither."""
    page, _, _ = today
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("scrollTo(0, 0)", isolated_context=False)
    card = page.locator(".qcard.open")
    send = card.locator(".mail-actions").get_by_role("button", name="Send", exact=True)
    bar = card.locator(".mail-actions")
    rows = [card.locator(".mail-row").filter(has_text=name).first for name in ("To", "Subject")]
    overlap = lambda a, b: not (a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])
    # Measured without scrolling: the first screen holds To, Subject, REM's question and Send, none covered.
    assert page.evaluate("scrollY", isolated_context=False) == 0
    assert _box_inside(page, send, 40 if size[0] > 400 else 16), send.bounding_box()
    for target in [*rows, card.locator(".mail-choices .owner-slot")]:
        assert _box_inside(page, target, 0) and not overlap(target.bounding_box(), bar.bounding_box()), target


def test_the_owner_is_never_a_person_waiting(today):
    """Build 3b review: a row on your own page belongs to the person it names, or to nobody."""
    page, _, _ = today
    page.evaluate(r"""async () => {
      const owner = byPath(REM.owner);
      owner.original = undefined;
      const rows = '- Tomás Reyes asked the user for a review of the pilot notes; due 2026-10-02 [1].\n- Water the office plants; due 2026-10-02 [1].\n';
      owner.text = /^## Open threads/mi.test(owner.text) ? owner.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1' + rows)
        : owner.text + '\n\n## Open threads\n' + rows;
      REM.night_outcomes = [{key: 'o', record: REM.owner, title: owner.title, kind: 'could_not_prepare'},
        {key: 'm', record: 'people/mara-ostrowski.md', title: 'Mara Ostrowski', kind: 'could_not_prepare'}];
      KNOWN.clear(); FACTS.clear(); OWING = null; await refreshTodayQueue(); render();
    }""", isolated_context=False)
    owner = page.evaluate("REM.owner", isolated_context=False)
    paths = page.locator(".fuse .lane").evaluate_all("lanes => lanes.map(lane => lane.dataset.path)")
    assert owner not in paths and "people/tomas-reyes.md" in paths
    assert page.locator(f'.qcard[data-path="{owner}"]').count() == 0
    assert int(page.locator(".brief-header h1 .count").inner_text()) == len(paths)
    assert "Your page" not in page.locator(".fuse").inner_text()
    assert page.locator('.night-done li[data-kind="could_not_prepare"] b').inner_text() == "Could not draft for 1 person"


def test_the_ready_reply_says_why_it_leads(today):
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate("""() => { REM.live = true; setInterfaceLanguage('zh');
      REM.drafts = [{id: 'mara', version: 'v1', provider: 'outlook', thread: 'mail:fixture:harbour-renewal', status: 'prepared',
        to: 'Mara Ostrowski <mara@example.test>', from: 'avery@example.test', subject: 'Re: Addendum', body: 'Signed today.'}];
      render(); }""", isolated_context=False)
    assert "最急的是 Inès Halvorsen" in page.locator(".brief-header .lede").inner_text()
    why = page.locator(".today-brief .lead-why")
    assert why.inner_text() == "先回 Mara Ostrowski：回信已写好"
    assert why.bounding_box()["y"] < page.locator(".qcard.open").bounding_box()["y"]


def test_counts_name_their_unit(today):
    page, _, _ = today
    page.evaluate("""() => { REM.live = true; setInterfaceLanguage('zh');
      REM.approval_outcomes = [{id: 'a', kind: 'handled', title: 'Mara'}, {id: 'b', kind: 'task', title: 'Mara'}]; render(); }""",
                  isolated_context=False)
    assert page.locator("#approve-all").inner_text() == "2 件可一键批准"
    assert "件等你处理" in page.locator(".brief-header .waiting-more").inner_text()


@pytest.mark.parametrize("status, words", [(409, "这件事已经变了，刷新后再试。"), (401, "登录过期，刷新页面。"),
                                           (500, "REM 暂时没回应，过会儿再试。"), (None, "REM 暂时没回应，过会儿再试。")])
def test_hand_off_failures_are_plain_words(today, status, words):
    page, _, answers = today
    page.evaluate("() => { REM.live = true; setInterfaceLanguage('zh'); render(); }", isolated_context=False)
    if status is None:
        page.context.route(BASE + "rem/task", lambda route: route.abort())
    else:
        answers["/rem/task"] = [(status, {"error": "Traceback: KeyError 'key' in tasks.dispatch"})]
    card = page.locator(".today-brief .qcard").first
    card.locator(".handoff").get_by_role("button", name="交给 Codex").click()
    card.get_by_text(words).wait_for()
    assert "Traceback" not in card.inner_text() and "KeyError" not in card.inner_text()


def test_the_undo_leaves_when_the_hold_ends_and_the_phone_bar_stays_clear(today):
    page, _, answers = today
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("""() => { REM.drafts.push({...REM.drafts[0], id: 'mara', thread: 'mail:fixture:harbour-renewal', to: 'Mara <mara@example.test>',
      body: 'Signed today.'}); REM.approval_outcomes.push({...REM.approval_outcomes[0], id: 'reply:mara', draft_id: 'mara', blocked: false}); render(); }""",
                  isolated_context=False)
    soon = lambda: (datetime.now(timezone.utc) + timedelta(seconds=2.5)).isoformat()
    answers["/rem/approve"] = lambda body: (200, {"release_at": soon(), "results": [
        {"id": i, "status": "held", "release_at": soon()} for i in body["ids"]]})
    card = page.locator(".qcard.open")
    card.locator(".owner-slot").get_by_role("button", name="共享文件夹").click()
    card.get_by_role("button", name="Send", exact=True).click()
    note = page.locator(".qsent")
    note.get_by_role("button", name="Undo", exact=True).wait_for()
    # The next ready reply is open; its Send bar is still pinned though the sent line now leads the list.
    bar = page.locator(".qcard.open .mail-actions")
    assert bar.evaluate("node => getComputedStyle(node).position") == "fixed"
    page.evaluate("() => setDone(threadEntries().find(e => e.r.path === 'orgs/fernhill-labs.md'), true)", isolated_context=False)
    notice = page.locator("#done-notice").bounding_box()
    assert notice["y"] + notice["height"] <= bar.bounding_box()["y"]
    page.wait_for_timeout(3000)
    assert note.get_by_role("button", name="Undo", exact=True).count() == 0


@pytest.mark.parametrize("width", [1440, 390])
def test_send_holds_the_reply_collapses_the_row_ticks_the_count_and_offers_undo(today, width):
    page, calls, answers = today
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    before = int(page.locator(".brief-header h1 .count").inner_text())
    release = "2099-01-01T00:10:00Z"
    answers["/rem/approve"] = lambda body: (200, {"release_at": release, "results": [
        {"id": i, "status": "cancelled" if body.get("action") == "undo" else "held", "release_at": release} for i in body["ids"]]})
    card = page.locator(".qcard.open")
    card.locator(".owner-slot").get_by_role("button", name="共享文件夹").click()
    card.get_by_role("button", name="Send", exact=True).click()
    page.locator(".qsent").wait_for()
    path, body = calls[-1]
    assert path == "/rem/approve" and body["ids"] == ["reply:ines"]
    assert "共享文件夹" in body["bodies"]["reply:ines"] and "【" not in body["bodies"]["reply:ines"]
    assert int(page.locator(".brief-header h1 .count").inner_text()) == before - 1
    assert page.locator('.fuse .lane[data-path="people/ines-halvorsen.md"]').count() == 0
    assert page.locator('.qcard[data-path="people/ines-halvorsen.md"]').count() == 0
    note = page.locator(".qsent")
    assert "Sent to Inès Halvorsen." in note.inner_text() and "undo" in note.inner_text()
    assert page.locator("#approval-undo").count() == 0  # one undo, beside the row it belongs to
    note.get_by_role("button", name="Undo", exact=True).click()
    page.locator('.qcard[data-path="people/ines-halvorsen.md"]').wait_for()
    assert calls[-1][1] == {"action": "undo", "ids": ["reply:ines"]}
    assert int(page.locator(".brief-header h1 .count").inner_text()) == before
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)


def test_the_overnight_rail_says_who_rem_replied_to_only_when_it_did(today):
    page, _, _ = today
    rail = page.locator(".night-done")
    page.evaluate("""() => { REM.sent_by_rem = [{title: 'Ines Halvorsen'}, {title: 'Tomás Reyes'}, {title: 'Ines Halvorsen'}];
      REM.night_outcomes = [{key: 'x', record: 'people/mara-ostrowski.md', title: 'Mara Ostrowski', kind: 'prepared'}]; render(); }""",
                  isolated_context=False)
    assert rail.locator('li[data-kind="sent"] b').inner_text() == "Replied to 2 people for you"
    page.evaluate("() => { setInterfaceLanguage('zh'); }", isolated_context=False)
    assert rail.locator('li[data-kind="sent"] b').inner_text() == "替你回了 2 个人"
    page.evaluate("() => { REM.sent_by_rem = []; render(); }", isolated_context=False)
    assert rail.locator('li[data-kind="sent"]').count() == 0


def test_questions_leave_the_sidebar_and_keep_their_route_and_one_quiet_door(today):
    page, _, _ = today
    page.evaluate("""() => { REM.reviews = [{id: 'r1', status: 'pending', kind: 'link', question: 'Is Mara at Fernhill Labs?',
      basis: 'Two cited mails.', subjects: ['people/mara-ostrowski.md']}]; render(); }""", isolated_context=False)
    assert page.locator('#nav a[href="#reviews=1"]').count() == 0
    assert "Questions & connections" not in page.locator("#nav").inner_text()
    page.goto(BASE + "#view=changes")
    door = page.locator('#main a[href="#reviews=1"]')
    assert door.count() == 1 and door.evaluate("a => !!a.closest('#main')")
    door.click()
    page.get_by_role("heading", name="Questions & connections", exact=True).wait_for()
