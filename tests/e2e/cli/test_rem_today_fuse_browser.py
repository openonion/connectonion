"""Today as N3's card desk (D-123; the fuse of D-108 lives on as the ring on each face), with 交给 Codex / 交给 Claude on every pending row (opt in).

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
        page.locator(".night-card .count").wait_for()
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


FACES = "faces => faces.map(face => face.dataset.path)"


def _hand(strip, name):
    """On a Today card the agents that are not the row's lead fold under its worded More (sprint 14)."""
    button = strip.get_by_role("button", name=name)
    if not button.is_visible():
        strip.locator(".strip-more > summary").click()
    button.click()


def _burn(page, path):
    """How much of a face's fuse ring is burnt, as a share of the circle (dasharray's first number / 314.16)."""
    burn = page.locator(f'.deal[data-path="{path}"] .ring .burn')
    return float(burn.get_attribute("stroke-dasharray").split()[0]) / 314.16 if burn.count() else 0


def test_faces_are_the_waiting_people_and_the_ring_burns_with_the_days_overdue(today):
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    faces = page.locator(".deal")
    headline = page.locator(".night-card .count").inner_text()
    people = page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")
    assert faces.evaluate_all(FACES) == people  # no draft: one order
    # The large number is the badge's; the people are its subset, said in words (sprint 14 #4).
    assert int(headline) == page.evaluate("threadCounts().mine", isolated_context=False)
    assert len(people) == faces.count()
    assert page.locator(".night-card .count-of").inner_text() == f"Start with these {len(people)} people"
    assert page.locator(".deal.on").get_attribute("data-path") == people[0]
    # One raised card: only the dealt card is shown; the others wait behind their faces.
    assert page.locator(".today-brief .qcard:visible").count() == 1
    assert abs(_burn(page, "people/ines-halvorsen.md") / _burn(page, "people/mara-ostrowski.md") - 5 / 2) < 0.05
    assert page.locator('.deal[data-path="people/ines-halvorsen.md"] .dd').inner_text() == "5 d"
    undated = page.locator('.deal[data-path="projects/harbour.md"]')
    assert _burn(page, "projects/harbour.md") == 0 and "late" not in undated.locator(".dd").get_attribute("class")
    # One number says one thing (TOP10 #9): the items total is the sidebar's, not said again here.
    assert "items waiting on you" not in page.locator(".night-card").inner_text()
    assert page.locator(".others .waiting-more").inner_text().endswith("waiting on others →")


def test_a_face_deals_its_card_and_skip_deals_the_next(today):
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    order = page.locator(".deal").evaluate_all(FACES)
    page.locator(f'.deal[data-path="{order[2]}"]').click()
    assert page.locator(".qcard.focal").get_attribute("data-path") == order[2]
    assert page.locator(".deal.on").get_attribute("data-path") == order[2]
    page.keyboard.press("s")
    assert page.locator(".qcard.focal").get_attribute("data-path") == order[3 % len(order)]
    page.keyboard.press("k")
    assert page.locator(".qcard.focal").get_attribute("data-path") == order[2]


def test_the_card_with_a_ready_reply_leads_while_the_faces_keep_their_order(today):
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate("""() => { REM.live = true;
      REM.drafts = [{id: 'mara', version: 'v1', provider: 'outlook', thread: 'mail:fixture:harbour-renewal', status: 'prepared',
        to: 'Mara Ostrowski <mara@example.test>', from: 'avery@example.test', subject: 'Re: Addendum', body: 'Signed today.'}];
      render(); }""", isolated_context=False)
    faces = page.locator(".deal").evaluate_all(FACES)
    cards = page.locator(".today-brief .qcard").evaluate_all("cards => cards.map(card => card.dataset.path)")
    assert cards[0] == "people/mara-ostrowski.md" and faces[0] == "people/ines-halvorsen.md"
    assert sorted(faces) == sorted(cards)
    assert page.locator(".deal.on").get_attribute("data-path") == cards[0]
    assert page.locator(".qcard.open.focal").get_attribute("data-path") == cards[0]


def test_every_pending_row_offers_codex_and_claude_quietly(today):
    page, _, _ = today
    page.evaluate("() => { REM.live = true; render(); }", isolated_context=False)
    rows = page.locator(".today-brief .qitem")
    assert rows.count() >= 4
    for i in range(rows.count()):
        # On Today the three closes come first, then the two hand-offs, still visible words (D-100; sprint 14).
        names = rows.nth(i).locator(".handoff-line > button").all_text_contents()
        assert names == ["Mark done", "Not now", "Ignore", "Hand to Codex", "Hand to Claude"]
    page.goto(BASE + "#view=open")
    mine = page.locator(".task-band").first.locator(".thread")
    assert mine.count() >= 1
    for i in range(mine.count()):
        assert mine.nth(i).locator(".handoff-line > button").all_text_contents() == ["Hand to Codex", "Hand to Claude", "Mark done", "Not now", "Ignore"]
        assert " ".join(mine.nth(i).locator(".talk-menu > summary").inner_text().split()) == "Talk it over ▾"
    page.locator(".task-band .thread .handoff button").first.wait_for()
    fills = page.locator(".handoff button").evaluate_all("nodes => nodes.map(node => getComputedStyle(node).backgroundColor)")
    assert not set(fills) & set(GREEN)


# Every control on a card that says Mark done, wherever it sits and whether or not it shows before the row is
# hovered: the head's tick (its label), the row's own tick, the strip's button, the green step button.
MARKS = """() => [...document.querySelectorAll('.today-brief .qcard')].map(card => {
  const says = node => /^Mark (all )?done/.test(node.getAttribute('aria-label') || node.textContent.trim());
  return {path: card.dataset.path,
    head: [...card.querySelectorAll('.qhead button')].filter(says).length,
    step: [...card.querySelectorAll('button')].filter(node => says(node) && !node.closest('.qhead, .qitem')).length,
    rows: [...card.querySelectorAll('.qitem')].map(row => ({ticks: row.querySelectorAll('.qdone').length,
      own: [...row.querySelectorAll('button')].filter(says).map(node => node.className)}))};
})"""


def test_a_today_row_has_one_mark_done_and_the_strips_button_closes_just_that_row(today):
    """Review of #2955: the strip put a second Mark done on every Today row, beside the tick it already had,
    and the two closed the row in different ways. The strip's is now the one, and it leaves like any other."""
    page, calls, answers = today
    answers["/rem/thread"] = lambda body: (200, {"state": body["state"], "at": "2026-10-08T12:00:00+00:00", "device": body["device"], "keys": body["keys"]})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate("() => { REM.live = true; render(); }", isolated_context=False)
    cards = page.evaluate(MARKS, isolated_context=False)
    assert len(cards) >= 3 and max(len(card["rows"]) for card in cards) > 1
    for card in cards:
        assert [row["ticks"] for row in card["rows"]] == [0] * len(card["rows"]), card
        assert all(row["own"] in (["btn-quiet strip-done"], ["btn-quiet strip-done strip-lead"]) for row in card["rows"]), card  # the strip's, on every row
        assert card["step"] == 0 or len(card["rows"]) > 1, card                  # a green Mark done only closes several
        assert card["head"] == (1 if len(card["rows"]) > 1 else 0), card           # the tick only where it closes several
    mara = page.locator('.today-brief .qcard[data-path="people/mara-ostrowski.md"]')
    assert mara.locator(".qitem").count() == 2
    page.locator('.deal[data-path="people/mara-ostrowski.md"]').click()
    row = mara.locator(".qitem").filter(has_text="budget forecast")
    done = row.locator(".handoff-line").get_by_role("button", name="Mark done", exact=True)
    page.mouse.move(0, 0)
    assert done.is_visible()                           # sprint 13: the strip's words show without a hover (owner, 2026-11-12)
    done.click()
    row.wait_for(state="detached")
    assert mara.locator(".qitem").count() == 1 and mara.locator(".qhead").get_by_role("button", name="Mark done · E").count() == 0
    posts = [body for path, body in calls if path == "/rem/thread" and body]
    assert [post["state"] for post in posts] == ["done"] and len(posts[0]["keys"]) == 1 and "budget forecast" in posts[0]["key"]
    page.get_by_text("Saved in notebook", exact=True).wait_for()
    assert mara.locator(".qitem").count() == 1          # the Host's answer keeps it closed
    page.locator("#done-notice").get_by_role("button", name="Undo", exact=True).click()
    row.wait_for()
    assert mara.locator(".qitem").count() == 2 and mara.locator(".qhead").get_by_role("button", name="Mark all done · E").count() == 1


# The night decided Inès's mail needs no reply: REM thinks the row is handled, and the card's step is Mark done.
NO_REPLY = r'''() => {
  REM.live = true;
  REM.source_context['outlook:3d5f7b9e1a0c'] = {...REM.source_context['outlook:3d5f7b9e1a0c'], source: 'outlook', thread: 'mail:fixture:ines'};
  REM.drafts = [{id: 'ines-none', version: 'v1', provider: 'outlook', thread: 'mail:fixture:ines', status: 'no_reply',
    to: 'Ines Halvorsen <ines@example.test>', subject: 'Re: Q3 receipts', gist: 'She confirmed she has the receipts.'}];
  render();
}'''


def test_a_handled_rows_mark_done_and_reason_show_without_a_hover(today):
    """Re-review of #2955: the card's green Mark done gave way to the row's own, but that one sat in the part of
    the row a hover reveals, so the card showed nothing to close it with. A handled row shows its strip at once."""
    page, _, _ = today
    page.evaluate(NO_REPLY, isolated_context=False)
    card = page.locator('.today-brief .qcard[data-path="people/ines-halvorsen.md"]')
    assert card.get_attribute("data-step") == "done"
    page.mouse.move(0, 0)
    assert card.locator(".card-acts").get_by_role("button", name="Mark done", exact=True).count() == 0   # never two
    assert card.locator(".handoff-line").get_by_role("button", name="Mark done", exact=True).is_visible()
    assert card.get_by_text("No reply needed: She confirmed she has the receipts.").is_visible()
    page.set_viewport_size({"width": 390, "height": 900})
    assert card.locator(".handoff-line").get_by_role("button", name="Mark done", exact=True).is_visible()
    # A card whose rows are all handled leads with its one green Mark done; each row still shows its own (sprint 13).
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate("() => { REM.live = true; window.looksDone = entry => entry.r.path === 'people/mara-ostrowski.md'; render();"
                  " dealCard('people/mara-ostrowski.md'); }", isolated_context=False)
    page.mouse.move(0, 0)
    mara = page.locator('.today-brief .qcard[data-path="people/mara-ostrowski.md"]')
    assert mara.locator(".qitem").count() == 2 and mara.get_attribute("data-step") == "done"
    assert mara.locator(".card-acts").get_by_role("button", name="Mark done", exact=True).is_visible()
    assert mara.locator(".handoff-line").get_by_role("button", name="Mark done", exact=True).first.is_visible()


def test_a_hand_off_posts_the_item_key_and_agent_then_shows_progress_and_plain_errors(today):
    page, calls, answers = today
    page.evaluate("() => { REM.live = true; setInterfaceLanguage('zh'); render(); }", isolated_context=False)
    card = page.locator(".today-brief .qcard").first
    key = page.evaluate("obligationKey(todayGroups(threadEntries().filter(e => !isDone(e)))[0].entries[0])", isolated_context=False)
    answers["/rem/task"] = [(200, {"id": "a1b2", "result": "starting", "agent": "claude", "by": "owner"})]
    card.locator(".qitem").first.hover()  # the row's actions are its second level (D-120)
    _hand(card.locator(".handoff").first, "交给 Claude")
    card.get_by_text("Claude 正在做").wait_for()
    assert calls[-1] == ("/rem/task", {"action": "run", "key": key, "agent": "claude"})
    assert card.get_by_role("button", name="停止").is_visible()
    answers["/rem/task"] = [(400, {"error": "Expected the item key and agent codex or claude"})]
    other = page.locator(".deal").evaluate_all(FACES)[1]
    page.locator(f'.deal[data-path="{other}"]').click()
    second = page.locator(".today-brief .qcard.focal")
    second.locator(".qitem").first.hover()
    _hand(second.locator(".handoff").first, "交给 Codex")
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
    page.locator(".settings-open").click()
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
    """D-10: To, Subject and Send all readable at once; on a phone the Send bar covers neither."""
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
    paths = page.locator(".deal").evaluate_all(FACES)
    assert owner not in paths and "people/tomas-reyes.md" in paths
    assert page.locator(f'.qcard[data-path="{owner}"]').count() == 0
    assert int(page.locator(".night-card .count").inner_text()) == len(paths)
    assert "Your page" not in page.locator(".night-card").inner_text()
    page.locator(".closed .link-btn").click()  # 看: what REM did overnight, every name
    assert page.locator('#night-sheet .night-done li[data-kind="could_not_prepare"] b').inner_text() == "Could not draft for 1 person"


def test_the_ready_reply_is_the_raised_card_and_its_face_is_marked(today):
    """N3: the card with a ready reply is dealt first; its face is the selected one, the most overdue still burns reddest."""
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate("""() => { REM.live = true; setInterfaceLanguage('zh');
      REM.drafts = [{id: 'mara', version: 'v1', provider: 'outlook', thread: 'mail:fixture:harbour-renewal', status: 'prepared',
        to: 'Mara Ostrowski <mara@example.test>', from: 'avery@example.test', subject: 'Re: Addendum', body: 'Signed today.'}];
      render(); }""", isolated_context=False)
    assert page.locator(".qcard.focal").get_attribute("data-path") == "people/mara-ostrowski.md"
    assert page.locator(".deal.on").get_attribute("data-path") == "people/mara-ostrowski.md"
    assert page.locator('.deal[data-path="people/ines-halvorsen.md"] .dd').inner_text() == "5 天"
    assert _burn(page, "people/ines-halvorsen.md") > _burn(page, "people/mara-ostrowski.md")


def test_counts_name_their_unit(today):
    page, _, _ = today
    page.evaluate("""() => { REM.live = true; setInterfaceLanguage('zh');
      REM.approval_outcomes = [{id: 'a', kind: 'handled', title: 'Mara'}, {id: 'b', kind: 'task', title: 'Mara'}]; render(); }""",
                  isolated_context=False)
    assert page.locator("#approve-all").inner_text() == "一键批准这 2 件"
    assert "件等你处理" not in page.locator(".night-card").inner_text()  # the sidebar's 等你处理 says it
    assert page.locator(".others .waiting-more").inner_text().startswith("看 ") and page.locator(".others .waiting-more").inner_text().endswith(" 件在等谁 →")


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
    card.locator(".qitem").first.hover()
    _hand(card.locator(".handoff").first, "交给 Codex")
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
    # Mara's draft needs nothing from the owner, so it is on top (deckOrder) and goes first; Ines's opens next.
    card = page.locator(".qcard.open")
    card.get_by_role("button", name="Send", exact=True).click()
    note = page.locator(".qsent")
    note.get_by_role("button", name="Undo", exact=True).wait_for()
    # The next ready reply is open; its Send stays in the draft's flow (sprint 13: a pinned bar covered the draft),
    # and a notice never lands on it while it is in view.
    bar = page.locator(".qcard.open .mail-actions")
    assert bar.evaluate("node => getComputedStyle(node).position") == "static"
    page.evaluate("() => setDone(threadEntries().find(e => e.r.path === 'orgs/fernhill-labs.md'), true)", isolated_context=False)
    tabs = page.locator("#tabbar").bounding_box()
    # Send in the middle, and Send just above the tab bar (where a thumb reaches it): the notice covers neither.
    for place in ("center", "bottom"):
        bar.evaluate("""(node, place) => { node.scrollIntoView({block: 'center'});
          if (place === 'bottom') scrollBy(0, node.getBoundingClientRect().bottom - (innerHeight - 96)); }""", place)
        notice, box = page.locator("#done-notice").bounding_box(), bar.bounding_box()
        assert notice["y"] + notice["height"] <= box["y"] or box["y"] + box["height"] <= notice["y"], (place, notice, box)
        assert notice["y"] + notice["height"] <= tabs["y"]
    page.wait_for_timeout(3000)
    assert note.get_by_role("button", name="Undo", exact=True).count() == 0


@pytest.mark.parametrize("width", [1440, 390])
def test_send_holds_the_reply_collapses_the_row_ticks_the_count_and_offers_undo(today, width):
    page, calls, answers = today
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    before = int(page.locator(".night-card .count").inner_text())
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
    assert int(page.locator(".night-card .count").inner_text()) == before - 1
    assert page.locator('.deal[data-path="people/ines-halvorsen.md"]').count() == 0
    assert page.locator('.qcard[data-path="people/ines-halvorsen.md"]').count() == 0
    note = page.locator(".qsent")
    assert "Sent to Inès Halvorsen." in note.inner_text() and "undo" in note.inner_text()
    assert page.locator("#approval-undo").count() == 0  # one undo, beside the row it belongs to
    note.get_by_role("button", name="Undo", exact=True).click()
    page.locator('.qcard[data-path="people/ines-halvorsen.md"]').wait_for()
    assert calls[-1][1] == {"action": "undo", "ids": ["reply:ines"]}
    assert int(page.locator(".night-card .count").inner_text()) == before
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)


def test_the_overnight_rail_says_who_rem_replied_to_only_when_it_did(today):
    page, _, _ = today
    rail = page.locator("#night-sheet .night-done")
    page.evaluate("""() => { REM.sent_by_rem = [{title: 'Ines Halvorsen'}, {title: 'Tomás Reyes'}, {title: 'Ines Halvorsen'}];
      REM.night_outcomes = [{key: 'x', record: 'people/mara-ostrowski.md', title: 'Mara Ostrowski', kind: 'prepared'}]; render(); }""",
                  isolated_context=False)
    assert page.locator(".closed").inner_text().startswith("REM handled 3 things overnight")
    page.locator(".closed .link-btn").click()
    assert rail.locator('li[data-kind="sent"] b').inner_text() == "Replied to 2 people for you"
    page.keyboard.press("Escape")
    page.evaluate("() => { setInterfaceLanguage('zh'); }", isolated_context=False)
    page.locator(".closed .link-btn").click()
    assert rail.locator('li[data-kind="sent"] b').inner_text() == "替你回了 2 个人"
    page.keyboard.press("Escape")
    page.evaluate("() => { REM.sent_by_rem = []; render(); }", isolated_context=False)
    page.locator(".closed .link-btn").click()
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


def test_the_phone_tab_bar_opens_more_above_today_and_send_stays_in_reach(today):
    """N3 (D-123): on a phone the rail and the ⌘K bar give way to a floating tab bar (今天 · 等你 · 人物 · 搜索 · 更多);
    Send sits in the draft above it, and 更多 opens every other place as a sheet."""
    page, _, _ = today
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("scrollTo(0, 0)", isolated_context=False)
    assert page.locator("select").count() == 0
    tabs = page.locator("#tabbar")
    assert [t.split()[-1] for t in tabs.locator(".tab").all_inner_texts()][:3] == ["Today", "Waiting", "People"]  # after the badge
    toggle = page.locator(".nav-toggle")
    assert toggle.inner_text().split()[-1] == "More" and toggle.get_attribute("aria-expanded") == "false"
    send = page.locator(".qcard.open .mail-actions").get_by_role("button", name="Send", exact=True)
    assert _box_inside(page, toggle, 0)
    # Send is in the draft's flow (sprint 13): brought into view, it sits clear above the tab bar.
    send.scroll_into_view_if_needed()
    send.evaluate("node => node.scrollIntoView({block: 'center'})")
    assert send.bounding_box()["y"] + send.bounding_box()["height"] <= tabs.bounding_box()["y"]
    assert toggle.bounding_box()["height"] >= 44
    assert not page.locator(".search").is_visible()
    tabs.locator(".tab-search").click()
    assert page.locator("#q").is_visible() and page.evaluate("document.activeElement.id", isolated_context=False) == "q"
    page.locator("#q").blur()
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    links = page.locator("#nav a")
    assert links.first.is_visible() and page.locator('#nav a[href="#view=changes"]').is_visible()
    # Each row of the sheet writes its place's full name beside its picture; the rail's short word is not shown twice.
    rows = page.locator("#nav > a")
    assert rows.evaluate_all("rows => rows.map(row => getComputedStyle(row, '::after').content)") == [
        '"Today"', '"Waiting on you"', '"People"', '"Organisations"', '"Projects"', '"Skills"', '"All records"']
    assert rows.locator(".w").evaluate_all("words => words.every(word => !word.getClientRects().length)")
    # The open sheet sits above the tab bar: every link it shows answers its own centre.
    assert page.evaluate("""() => [...document.querySelectorAll('#nav a')].every(link => {
      const box = link.getBoundingClientRect();
      if (box.bottom <= 0 || box.top >= innerHeight || !box.width) return true;
      const y = Math.min(Math.max(box.top + box.height / 2, 0), innerHeight - 1);
      return link.contains(document.elementFromPoint(box.left + box.width / 2, y));
    })""", isolated_context=False)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)
    page.locator("#nav").get_by_role("link", name="People", exact=True).click()
    assert page.evaluate("location.hash", isolated_context=False) == "#c=people"
    assert toggle.get_attribute("aria-expanded") == "false" and not links.first.is_visible()
    page.goto(BASE)
    page.locator(".night-card .count").wait_for()
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("scrollTo(0, 0)", isolated_context=False)
    assert _box_inside(page, send, 16)


def test_updates_waiting_never_loses_a_typed_slot_or_the_talk_box(today):
    """Clicking 有更新 redraws Today and puts typed words back: the reply slot, the talk box, caret and focus."""
    page, _, answers = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(r"""() => { REM.live = true;
      REM.source_context['outlook:3d5f7b9e1a0c'] = {...REM.source_context['outlook:3d5f7b9e1a0c'], source: 'outlook', thread: 'mail:fixture:ines'};
      REM.drafts = [{id: 'ines-receipts', version: 'v1', provider: 'outlook', thread: 'mail:fixture:ines', status: 'prepared',
        to: 'Ines Halvorsen <ines@example.test>', from: 'avery@example.test', subject: 'Re: Q3 receipts',
        body: 'Hi Ines,\n\nI can send the receipts 【需要你：the day you can send them — by Friday】.\n\nAvery'}];
      render(); }""", isolated_context=False)
    answers["/rem/talk"] = [(200, {"id": "a" * 32, "agent": "codex", "state": "idle", "about": {"key": "people/ines-halvorsen.md"}, "turns": []})] * 3
    card = page.locator(".today-brief .qcard.open")
    slot = card.locator(".owner-slot input")
    slot.fill("Thursday afternoon")
    row = card.locator(".qitem").first
    row.hover()
    row.locator(".strip-more > summary").click()
    row.locator(".strip-more .talk-menu > summary").click()
    row.locator('[data-talk="codex"]').click()
    talk = page.get_by_role("textbox", name="Your message")
    talk.fill("Draft it short")
    talk.evaluate("node => node.setSelectionRange(6, 8)")
    page.evaluate("() => { document.querySelector('.today-brief').dataset.before = '1'; redraw(); }", isolated_context=False)
    mark = page.get_by_role("button", name="Updates waiting")
    assert page.locator(".today-brief[data-before]").count() == 1      # held back while words are typed
    mark.click()
    mark.wait_for(state="detached")
    assert page.locator(".today-brief[data-before]").count() == 0      # Today was drawn again
    assert page.locator(".today-brief .qcard.open .owner-slot input").input_value() == "Thursday afternoon"
    assert page.locator(".today-brief .qcard.open .mail-actions .btn-act").is_enabled()   # the slot's answer is in the reply
    talk = page.get_by_role("textbox", name="Your message")
    assert talk.input_value() == "Draft it short"
    assert talk.evaluate("node => [node === document.activeElement, node.selectionStart, node.selectionEnd]") == [True, 6, 8]
    if os.environ.get("CO_REM_SHOTS"):
        page.locator(".today-brief .qcard.open").screenshot(path=str(Path(os.environ["CO_REM_SHOTS"]) / "updates-kept-words.png"))


# Two owed items on one card, the draft answering the second: a long English item first, then REM's long Chinese
# summary of the draft, and a letter long enough to scroll with a question slot under it (owner, 2026-11-10: the
# letter was half covered by the slot row and the summary's second line ran into the row below).
TWO_ITEMS = r'''async lang => {
  REM.live = true;
  const r = byPath('people/ines-halvorsen.md');
  r.original = undefined;
  r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi, '$1- You owe Inès a reply on the Quinn Alder introduction: "Could you reply to her directly with a time that works for both of you next week"; due 2026-09-30 [2].\n')
    .replace(/(files the return by [^\[\n]*)\[1\]/, '$1, and asks whether you will join the 11 November workshop or the 12 November year-end review, one answer for both [1]')
    .replace(/(^## Sources[^\n]*\n)/mi, '$1- [2] outlook:7c1e9b3a5d20 — intro to Quinn; confidence high; observed 2026-09-25.\n');
  REM.source_context['outlook:3d5f7b9e1a0c'] = {...REM.source_context['outlook:3d5f7b9e1a0c'], source: 'outlook', thread: 'mail:fixture:ines'};
  REM.drafts = [{id: 'ines-receipts', version: 'v1', provider: 'outlook', thread: 'mail:fixture:ines', status: 'prepared',
    to: 'Ines Halvorsen <ines@example.test>', from: 'avery@example.test', subject: 'Re: Q3 receipts and the two autumn workshops',
    body: 'Inès,\n\nThanks for the note about the receipts and the two workshops. I would rather keep our conversation on what your clients need from the forecast, and on who looks after the books once the return is filed, since that is where I can help most.\n\n【需要你：确认是否参加 11/11 工作坊、11/12 年终复盘，或都不参加】\n\nAvery',
    gist: '建议把交流重点放在她客户对预测的需求、报税之后谁来维护账目这两件事上。是否同行参加哪一场工作坊，需要你确认后再回。',
    why: 'She files the return soon.'}];
  KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); setInterfaceLanguage(lang); render(); scrollTo(0, 0);
}'''

# The lines of `text` that `clip`'s box cuts through: part shown, part hidden. A line is read whole or not at all.
CUT_LINES = r'''([text, clip]) => {
  const range = document.createRange(); range.selectNodeContents(text);
  const box = clip.getBoundingClientRect();
  return [...range.getClientRects()].filter(line => line.width > 0 && line.height > 0)
    .filter(line => line.top < box.bottom - 0.5 && line.bottom > box.top + 0.5 && (line.top < box.top - 0.5 || line.bottom > box.bottom + 0.5))
    .map(line => [text.className, Math.round(line.top), Math.round(line.bottom), Math.round(box.top), Math.round(box.bottom)]);
}'''


def _apart(a, b):
    return a["y"] + a["height"] <= b["y"] + 0.5 or b["y"] + b["height"] <= a["y"] + 0.5


def _cut(page, text, clip):
    return page.evaluate(CUT_LINES, [text.element_handle(), clip.element_handle()], isolated_context=False)


@pytest.mark.parametrize("size", [(1440, 1000), (390, 844)])
@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_letter_scrolls_in_its_own_window_and_the_slot_row_never_covers_it(today, size, lang):
    page, _, _ = today
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(TWO_ITEMS, lang, isolated_context=False)
    card = page.locator(".today-brief .qcard.open")
    body, letter, slot = card.locator(".mail-body"), card.locator(".mail-text"), card.locator(".mail-choices .owner-slot")
    if os.environ.get("CO_REM_SHOTS"):
        page.screenshot(path=str(Path(os.environ["CO_REM_SHOTS"]) / f"today-overlaps-{lang}-{size[0]}.png"))
    assert slot.is_visible() and card.locator(".mail-actions .btn-act").first.is_visible()
    assert _apart(body.bounding_box(), slot.bounding_box()), (body.bounding_box(), slot.bounding_box())
    columns = [letter] + ([card.locator(".mail-gist")] if card.locator(".mail-gist").is_visible() else [])
    assert [cut for column in columns for cut in _cut(page, column, body)] == []
    # The letter is read by scrolling inside its window, to its last line.
    assert body.evaluate("node => node.scrollHeight > node.clientHeight")
    body.evaluate("node => { node.scrollTop = node.scrollHeight; }")
    last = page.evaluate("""node => { const r = document.createRange(); r.selectNodeContents(node);
      const lines = [...r.getClientRects()].filter(l => l.height > 0); return lines.at(-1).bottom; }""",
                         letter.element_handle(), isolated_context=False)
    assert last <= body.bounding_box()["y"] + body.bounding_box()["height"] + 0.5


@pytest.mark.parametrize("size", [(1440, 1000), (390, 844)])
@pytest.mark.parametrize("lang", ["zh", "en"])
def test_a_long_row_is_clamped_whole_and_never_runs_into_the_line_below(today, size, lang):
    page, _, _ = today
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(TWO_ITEMS, lang, isolated_context=False)
    items = page.locator(".today-brief .qcard.open .qitem")
    assert items.count() == 2
    for i in range(2):
        if items.nth(i).is_visible():
            items.nth(i).hover()  # the kind line under a row is its second level (D-120)
        words, below = items.nth(i).locator(".words"), items.nth(i).locator(".qkind")
        if not words.is_visible():
            continue
        assert _cut(page, words, words) == [], (i, words.inner_text())
        assert _apart(words.bounding_box(), below.bounding_box()), (i, words.bounding_box(), below.bounding_box())


# Who is raised, read five ways: the open card, the card showing a green action, the pressed face, the lit face,
# and the face ringed in the night chart.
RAISED = """() => {
  const shows = node => node.getClientRects().length > 0;
  const green = [...document.querySelectorAll('.today-brief .qcard')].filter(card => [...card.querySelectorAll('.btn-act, .strip-lead')].some(shows));
  // Faces that rose close together share one ring: its initials are the raised person's, its title names them all.
  const waiting = [...document.querySelectorAll('.today-brief .qcard')].map(card => byPath(card.dataset.path));
  const ringed = [...document.querySelectorAll('.night-card .fc.sel')].flatMap(ring => waiting.filter(r =>
    ring.querySelector('title').textContent.includes(threadWho(r)) && ring.querySelector('text').textContent === face(threadWho(r)).textContent));
  return [[...document.querySelectorAll('.today-brief .qcard.focal.open')], green, [...document.querySelectorAll('.deal[aria-pressed="true"]')],
    [...document.querySelectorAll('.deal.on')]].map(nodes => nodes.map(node => node.dataset.path).join()).concat(ringed.map(r => r.path).join());
}"""


def _raised_everywhere(page):
    shown = page.locator(".today-brief .qcard.focal :is(.btn-act, .strip-lead)").evaluate_all("nodes => nodes.filter(node => node.getClientRects().length).length")
    assert shown == 1, "the raised card shows exactly one primary: green, or the row's lead in bold"
    return page.evaluate(RAISED, isolated_context=False)


def test_dealing_another_card_keeps_the_words_typed_in_the_raised_one(today):
    """Review of #2929: dealing redrew Today and dropped a half-answered question. Every card is already in the
    page, so a deal only moves which one is raised; what was typed in any of them stays."""
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(r"""() => { REM.live = true;
      REM.source_context['outlook:3d5f7b9e1a0c'] = {...REM.source_context['outlook:3d5f7b9e1a0c'], source: 'outlook', thread: 'mail:fixture:ines'};
      REM.drafts = [{id: 'ines-receipts', version: 'v1', provider: 'outlook', thread: 'mail:fixture:ines', status: 'prepared',
        to: 'Ines Halvorsen <ines@example.test>', from: 'avery@example.test', subject: 'Re: Q3 receipts',
        body: 'Hi Ines,\n\nI can send the receipts 【需要你：the day you can send them — by Friday】.\n\nAvery'}];
      // Each person waiting has a rise of their own in the night chart, two hours apart, so each has a face there.
      REM.night_outcomes = todayGroups(threadEntries().filter(e => !isDone(e))).map(({ r }, i) => ({key: r.path, record: r.path, title: r.title,
        kind: 'prepared', prepared_at: new Date(Date.parse('2026-10-08T02:00:00Z') + i * 7200000).toISOString()}));
      // Two runs in the three nights, so the chart is drawn in full rather than folded to a line (nightSparse).
      REM.logs = [...REM.logs, {phase: 'sync', started_at: '2026-10-07T03:00:00Z', finished_at: '2026-10-07T03:14:00Z', items: 9},
        {phase: 'daily-update', started_at: '2026-10-08T03:00:00Z', finished_at: '2026-10-08T03:20:00Z', items: 0}];
      render(); }""", isolated_context=False)
    card = page.locator(".today-brief .qcard.focal")
    start = card.get_attribute("data-path")
    card.locator(".owner-slot input").fill("Thursday afternoon")
    faces = page.locator(".deal").evaluate_all(FACES)
    other = next(path for path in faces if path != start)
    assert _raised_everywhere(page) == [start] * 5
    page.locator(f'.deal[data-path="{other}"]').click()
    assert _raised_everywhere(page) == [other] * 5
    assert page.locator(f'.deal[data-path="{start}"]').get_attribute("aria-pressed") == "false"
    page.locator("body").press("s")  # S deals the next card; the words stay where they were typed
    assert _raised_everywhere(page) == [faces[(faces.index(other) + 1) % len(faces)]] * 5
    page.locator(f'.deal[data-path="{start}"]').click()
    assert _raised_everywhere(page) == [start] * 5
    assert page.locator(".today-brief .qcard.focal .owner-slot input").input_value() == "Thursday afternoon"
    # The raised card carries the page's one primary action; a card waiting behind its face does not.
    assert page.locator(".today-brief .qcard:not(.focal) .card-acts .btn-act").count() == 0


def test_a_click_in_a_dealt_card_never_folds_its_draft_and_send_away(today):
    """Review of #2929: a card raised by a deal folded on a click anywhere plain in it, and its draft and Send
    went with it. The click read how the card was first drawn, not whether it is the raised one now."""
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("""() => { REM.drafts.push({...REM.drafts[0], id: 'mara', thread: 'mail:fixture:harbour-renewal', to: 'Mara <mara@example.test>',
      body: 'Signed today.'}); REM.approval_outcomes.push({...REM.approval_outcomes[0], id: 'reply:mara', draft_id: 'mara', blocked: false}); render(); }""",
                  isolated_context=False)
    # Mara's draft needs nothing from the owner, so it is on top (deckOrder); the deal raises Ines's.
    assert page.locator(".today-brief .qcard.focal").get_attribute("data-path") == "people/mara-ostrowski.md"
    page.locator('.deal[data-path="people/ines-halvorsen.md"]').click()
    card = page.locator('.today-brief .qcard[data-path="people/ines-halvorsen.md"]')
    draft, send = card.locator(".qdraft"), card.locator(".mail-actions").get_by_role("button", name="Send", exact=True)
    assert draft.is_visible() and send.is_visible()
    for plain in (".qhead .qage", ".qitem .words"):  # the head's age, then a row's words, whose click reaches the card
        card.locator(plain).first.click()
        assert draft.is_visible() and send.is_visible(), plain
        assert {"focal", "open"} <= set(card.get_attribute("class").split()), plain


@pytest.mark.parametrize("live", [True, False])
def test_with_nothing_open_today_says_so_instead_of_an_empty_widget(today, live):
    """Review of #2929: an empty "Waiting on others" card showed when nothing was open either way. Live and
    snapshot say the same sentence; with only your own items open, the link is not filed under others."""
    page, _, _ = today
    page.evaluate("""live => { REM.live = live; REM.approval_outcomes = []; REM.approval_pending = []; REM.today_queue = [];
      for (const r of REM.records) r.text = r.text.replace(/## Open threads[\\s\\S]*?(?=\\n## |$)/, '## Open threads\\nUnknown\\n');
      KNOWN.clear(); FACTS.clear(); OWING = null; threadEntries.cached = null; render(); }""", live, isolated_context=False)
    assert page.evaluate("JSON.stringify([threadCounts().mine, threadCounts().theirs])", isolated_context=False) == "[0,0]"
    assert page.locator(".others").count() == 0
    assert page.locator(".side .nothing-open").inner_text() == "Nothing is open between you and anyone right now."
    page.evaluate("""async () => { const r = byPath('people/mara-ostrowski.md'); r.original = undefined;
      r.text = r.text.replace(/## Open threads[^\\n]*\\n[^\\n]*/, '## Open threads\\n- You owe Mara a review of the budget forecast; due 2026-10-06 [4].');
      KNOWN.clear(); FACTS.clear(); OWING = null; await refreshTodayQueue(); render(); }""", isolated_context=False)
    assert page.evaluate("threadCounts().mine", isolated_context=False) >= 1
    widget = page.locator(".others")
    assert widget.count() == 1 and "Waiting on others" not in widget.inner_text()
    assert widget.locator(".waiting-more").get_attribute("href") == "#view=open"


def test_undoing_a_held_approval_shows_the_approve_button_again(today):
    """Review of #2929: with nothing open, Today shows one sentence and no approve button, so an Undo that brought
    a held reply back had no button to show it in until the page was drawn again."""
    page, calls, answers = today
    held = {"id": "reply:ines", "kind": "reply", "status": "held", "release_at": "2099-01-01T00:10:00Z",
            "to": "ines@example.test", "subject": "Re: Q3 receipts", "body": "The Q3 receipts are attached."}
    page.evaluate("""held => { REM.live = true; REM.approval_outcomes = []; REM.approval_pending = [held]; REM.today_queue = [];
      for (const r of REM.records) r.text = r.text.replace(/## Open threads[\\s\\S]*?(?=\\n## |$)/, '## Open threads\\nUnknown\\n');
      KNOWN.clear(); FACTS.clear(); OWING = null; threadEntries.cached = null; render(); }""", held, isolated_context=False)
    assert page.locator(".side .nothing-open").count() == 1 and page.locator("#approve-all").count() == 0
    answers["/rem/approve"] = lambda body: (200, {"results": [{"id": i, "status": "cancelled"} for i in body["ids"]]})
    page.locator("#approval-undo").get_by_role("button", name="Undo", exact=True).click()
    page.locator("#approve-all").wait_for()
    assert calls[-1] == ("/rem/approve", {"action": "undo", "ids": ["reply:ines"]})
    assert page.locator("#approve-all").inner_text() == "Approve all 1" and page.locator("#approve-all").is_enabled()
    assert page.locator(".side .nothing-open").count() == 0
    assert "Cancelled" in page.locator("#approval-undo").inner_text()


IN_RAISED = '!!document.activeElement.closest("#main .qcard.focal")'


def _press_e_on_the_raised_card(page):
    path = page.locator("#main .qcard.focal").get_attribute("data-path")
    page.keyboard.press("e")
    page.locator(f'.qcard[data-path="{path}"]').wait_for(state="detached")
    page.evaluate("threadWrite", isolated_context=False)  # the Host has answered and Today is drawn again
    return path


def test_e_pressed_again_closes_the_next_card_and_enter_still_undoes(today):
    """Review of #2929: after E closed a card the focus sat on Undo, so the next E did nothing. While the notice
    shows, E closes the next card and Enter undoes; when the notice goes, the raised card has the focus again,
    and a redraw (the Host confirming the save) leaves it there."""
    page, calls, answers = today
    # The Host answers a save with the decision it kept (threads.set_state).
    answers["/rem/thread"] = lambda body: (200, {"state": body["state"], "at": "2026-10-08T12:00:00+00:00", "device": body["device"], "keys": body["keys"]})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate("() => { REM.live = true; render(); }", isolated_context=False)
    cards = page.locator(".today-brief .qcard")
    count = cards.count()
    assert count >= 3
    page.locator("#main .qcard.focal").focus()
    first = _press_e_on_the_raised_card(page)
    second = _press_e_on_the_raised_card(page)
    assert second != first and cards.count() == count - 2
    page.keyboard.press("Enter")  # Undo holds the focus: the card just closed comes back
    page.locator(f'.qcard[data-path="{second}"]').wait_for()
    page.evaluate("threadWrite", isolated_context=False)
    assert [body["state"] for path, body in calls if path == "/rem/thread"] == ["done", "done", "open"]
    assert cards.count() == count - 1 and page.locator("#done-notice").count() == 0
    assert page.evaluate(IN_RAISED, isolated_context=False)
    _press_e_on_the_raised_card(page)
    page.locator("#done-notice").wait_for(state="detached", timeout=8000)  # the notice leaves after five seconds
    assert page.evaluate(IN_RAISED, isolated_context=False)
    _press_e_on_the_raised_card(page)
    assert cards.count() == count - 3


def test_in_chinese_the_card_unfolds_and_the_tab_bar_says_more(today):
    """Review of #2929: one key named both the card's unfold button and the tab bar's More, so the card said 更多;
    and the tab bar's own name was English in every language."""
    page, _, _ = today
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    words = """() => [document.querySelector('.qcard.focal .qfull').textContent, document.querySelector('#tabbar .nav-toggle').textContent,
      document.getElementById('tabbar').getAttribute('aria-label')]"""
    assert page.evaluate(words, isolated_context=False) == ["More", "More", "Tabs"]
    page.evaluate("setInterfaceLanguage('zh')", isolated_context=False)
    assert page.evaluate(words, isolated_context=False) == ["展开", "更多", "标签栏"]
