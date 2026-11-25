"""Exercise the fullscreen writer from a live Today card with intercepted send requests."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_reply_compose_browser import _card, today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _open(page, width=1440):
    card = _card(page, width)
    page.evaluate("""() => {
      const draft = REM.drafts[0];
      setPrivacy("cover", {save: false, redraw: false});
      const message = (sender, excerpt) => ({sender, subject: 'Q3 receipts', excerpt, level: 'personal'});
      draft.writer_mail = {
        original: message('ines@example.test', 'Please send the receipts by Friday.'),
        examples: [message(draft.from, 'Last quarter I attached the invoices.')]
      };
      REM.source_context['outlook:other'] = message(draft.from, 'Unrelated private reply.');
      render();
    }""", isolated_context=False)
    card.locator(".mail-write").click()
    return page.locator("dialog.writer[open]")


def test_archived_request_and_example_stay_outside_the_sent_letter(today):
    page, calls, answers = today
    dialog = _open(page)
    original, body = dialog.locator(".writer-original"), dialog.get_by_role("textbox", name="Reply body")
    examples = dialog.locator(".writer-side .writer-examples")
    assert "Please send the receipts by Friday." in original.inner_text()
    assert original.locator(".writer-msg-text").evaluate(
        "n => parseFloat(getComputedStyle(n).fontSize) >= 14 && "
        "getComputedStyle(n).color === getComputedStyle(n.closest('dialog')).color")
    assert dialog.locator(".writer-context").get_attribute("open") is None
    assert "Last quarter I attached the invoices." in examples.inner_text()
    assert "Unrelated private reply." not in dialog.inner_text()
    assert original.bounding_box()["y"] < body.bounding_box()["y"]
    assert body.bounding_box()["x"] + body.bounding_box()["width"] <= examples.bounding_box()["x"]
    chip = body.get_by_role("button")
    chip.focus()
    page.keyboard.press("Enter")
    assert page.evaluate("!!document.activeElement.closest('.writer-choices')", isolated_context=False)
    dialog.get_by_role("button", name="共享文件夹", exact=True).click()
    body.focus()
    body.evaluate("n => getSelection().collapse(n, n.childNodes.length)")
    page.keyboard.type(" (updated)")
    assert not [p for p, _ in calls if p in ("/rem/approve", "/rem/draft")]
    answers["/rem/approve"] = lambda payload: (200, {"results": [{"id": i, "status": "sent"} for i in payload["ids"]]})
    dialog.get_by_role("button", name="Send", exact=True).click()
    dialog.wait_for(state="detached")
    assert calls[-1][1]["bodies"]["reply:ines"] == "Hi Ines,\n\nThe Q3 receipts are attached. 共享文件夹\n\nAvery (updated)"


def test_phone_can_read_source_and_empty_editor_cannot_send_original(today):
    page, calls, _ = today
    dialog = _open(page, 390)
    original = dialog.locator(".writer-original")
    assert original.get_attribute("open") is None
    original.locator("summary").click()
    assert original.get_by_text("Please send the receipts by Friday.").is_visible()
    body = dialog.get_by_role("textbox", name="Reply body")
    body.fill("")
    dialog.get_by_role("button", name="Send", exact=True).click()
    assert "Write a reply before sending" in dialog.get_by_role("status").inner_text()
    assert not [p for p, _ in calls if p in ("/rem/approve", "/rem/draft")]


def test_calendar_choice_updates_only_the_letter_until_send(today):
    page, calls, answers = today
    card = _card(page, body="Could we meet 【需要你：meeting time — date not agreed】?")
    page.clock.set_fixed_time("2026-11-23T08:00:00Z")
    page.evaluate("""() => {
      const at = '2026-11-23T08:00:00Z';
      REM.calendar = {saved_at: at, errors: [], read: [{at, calendars: 1}],
        window: {start: '2026-11-23T00:00:00Z', end: '2026-11-24T00:00:00Z', timezone: 'UTC'},
        events: [{start: '2026-11-23T09:00:00Z', end: '2026-11-23T10:00:00Z'}]};
    }""", isolated_context=False)
    card.locator(".mail-write").click()
    dialog = page.locator("dialog.writer[open]")
    choice = dialog.locator(".writer-choices button").first
    label = choice.inner_text()
    assert "10:00" in label and "UTC" in label
    choice.click()
    assert dialog.locator(".writer-body").inner_text() == f"Could we meet {label}?"
    assert not [p for p, _ in calls if p in ("/rem/approve", "/rem/draft")]
    answers["/rem/approve"] = lambda payload: (200, {"results": [{"id": i, "status": "sent"} for i in payload["ids"]]})
    dialog.get_by_role("button", name="Send", exact=True).click()
    dialog.wait_for(state="detached")
    assert calls[-1][1]["bodies"]["reply:ines"] == f"Could we meet {label}?"


def test_missing_calendar_leaves_time_as_an_editable_question(today):
    page, calls, _ = today
    card = _card(page, body="Could we meet 【需要你：meeting time — date not agreed】?")
    page.evaluate("() => { REM.calendar = null; }", isolated_context=False)
    card.locator(".mail-write").click()
    dialog = page.locator("dialog.writer[open]")
    choices = dialog.locator(".writer-choices")
    assert choices.get_by_role("button").count() == 0
    dialog.get_by_role("button", name="Send", exact=True).click()
    field = choices.get_by_role("textbox")
    assert field.evaluate("n => n === document.activeElement")
    field.fill("after the presentation")
    assert dialog.locator(".writer-body").inner_text() == "Could we meet after the presentation?"
    assert not [p for p, _ in calls if p in ("/rem/approve", "/rem/draft")]


@pytest.mark.parametrize("fresh", [True, False])
def test_mixed_demo_question_keeps_location_open_until_owner_fills_it(today, fresh):
    page, calls, answers = today
    question = "确认是否接受11月23日周一14:00的演示时间，并填写具体见面地点；如不合适，给出替代时间"
    card = _card(page, body="我的回复：【需要你：" + question + "】")
    page.clock.set_fixed_time("2026-11-23T08:00:00Z")
    page.evaluate("""fresh => {
      const at = fresh ? '2026-11-23T08:00:00Z' : '2026-11-21T08:00:00Z';
      REM.calendar = {saved_at: at, errors: [], read: [{at, calendars: 1}], events: [],
        window: {start: '2026-11-21T00:00:00Z', end: '2026-11-27T00:00:00Z', timezone: 'UTC'}};
    }""", fresh, isolated_context=False)
    card.locator(".mail-write").click()
    dialog = page.locator("dialog.writer[open]")
    fields = dialog.locator(".writer-choices")
    time = fields.get_by_role("textbox", name="Meeting time or alternatives")
    location = fields.get_by_role("textbox", name="Meeting location (required)")
    send = dialog.get_by_role("button", name="Send", exact=True)
    if fresh:
        first, second = fields.get_by_role("button").all()[:2]
        first.click()
        send.click()
        assert location.evaluate("n => n === document.activeElement")
        assert not [p for p, _ in calls if p in ("/rem/approve", "/rem/draft")]
        second.click()
        assert time.input_value() == first.inner_text() + " / " + second.inner_text()
        first.click()
        assert time.input_value() == second.inner_text()
        assert second.get_attribute("aria-pressed") == "true"
    else:
        assert fields.get_by_role("button").count() == 0
        assert "No verified calendar times. Enter a time manually." in fields.inner_text()
    time.fill("周三下午两点或周四上午十点")
    send.click()
    assert dialog.is_visible() and not location.input_value()
    assert not [p for p, _ in calls if p in ("/rem/approve", "/rem/draft")]
    location.fill("西楼前台")
    expected = "我的回复：周三下午两点或周四上午十点 · 西楼前台"
    assert dialog.locator(".writer-body").inner_text() == expected
    location.fill("")
    send.click()
    assert not [p for p, _ in calls if p in ("/rem/approve", "/rem/draft")]
    location.fill("西楼前台")
    answers["/rem/approve"] = lambda payload: (200, {"results": [{"id": i, "status": "sent"} for i in payload["ids"]]})
    send.click()
    dialog.wait_for(state="detached")
    assert calls[-1][1]["bodies"]["reply:ines"] == expected


@pytest.mark.parametrize("language,question,expected", [
    ("en", "meeting time and place", "26 November 2026 · 14:00–14:30 (Australia/Sydney)"),
    ("zh", "meeting time / location", "2026年11月26日 · 14:00–14:30 (Australia/Sydney)"),
])
def test_sydney_time_and_place_on_card_and_in_writer(today, tmp_path, language, question, expected):
    page, calls, _ = today
    card = _card(page, body="Demo: 【需要你：" + question + "】")
    page.clock.set_fixed_time("2026-11-26T02:59:00Z")
    page.evaluate("""language => {
      const at = '2026-11-26T02:59:00Z';
      REM.calendar = {saved_at: at, errors: [], read: [{at, calendars: 1}], events: [],
        window: {start: '2026-11-26T00:00:00+11:00', end: '2026-11-27T00:00:00+11:00', timezone: 'Australia/Sydney'}};
      setInterfaceLanguage(language);
    }""", language, isolated_context=False)
    choices = card.locator(".owner-slot.choose")
    choice = choices.get_by_role("button", name=expected, exact=True)
    assert choice.is_visible() and choice.inner_text() == expected
    assert choices.get_by_role("button").count() == 1
    card.locator(".mail-write").click()
    dialog = page.locator("dialog.writer[open]")
    choices = dialog.locator(".writer-choices")
    choice = choices.get_by_role("button", name=expected, exact=True)
    assert choice.inner_text() == expected
    choice.click()
    send = dialog.get_by_role("button", name="Send" if language == "en" else "发送", exact=True)
    send.click()
    location = choices.get_by_role("textbox").nth(1)
    assert location.evaluate("n => n === document.activeElement")
    assert not [p for p, _ in calls if p in ("/rem/approve", "/rem/draft")]
    location.fill("Room 4")
    assert dialog.locator(".writer-body").inner_text() == f"Demo: {expected} · Room 4"
    choices.screenshot(path=tmp_path / f"sydney-{language}.png")


@pytest.mark.parametrize("location_on_card", ["", "North & South"])
def test_card_answers_remain_editable_and_send_as_literal_text(today, location_on_card):
    page, calls, answers = today
    card = _card(page, body="Meet: 【需要你：meeting time and location】\n"
                            "Bring: 【需要你：materials】\nFormat: 【需要你：PDF / Email】")
    page.clock.set_fixed_time("2026-11-23T08:00:00Z")
    page.evaluate("""() => {
      const at = '2026-11-23T08:00:00Z';
      REM.calendar = {saved_at: at, errors: [], read: [{at, calendars: 1}], events: [],
        window: {start: '2026-11-23T00:00:00Z', end: '2026-11-26T00:00:00Z', timezone: 'UTC'}};
      render();
    }""", isolated_context=False)
    rows = card.locator(".mail-choices .owner-slot")
    first, second = rows.nth(0).get_by_role("button").all()[:2]
    first.click()
    second.click()
    time_name = "Meeting time or alternatives"
    place_name = "Meeting location (required)"
    times = rows.nth(0).get_by_role("textbox", name=time_name).input_value()
    assert " / " in times
    rows.nth(0).get_by_role("textbox", name=place_name).fill(location_on_card)
    materials = 'R&D <spec> "A" &amp; B'
    rows.nth(1).get_by_role("textbox").fill(materials)
    rows.nth(2).get_by_role("button", name="PDF", exact=True).click()
    card.locator(".mail-write").click()
    dialog = page.locator("dialog.writer[open]")
    fields = dialog.locator(".writer-choices")
    assert fields.get_by_role("textbox", name=time_name).input_value() == times
    assert fields.locator('button[aria-pressed="true"]').count() == 3
    assert fields.get_by_role("textbox", name="materials").input_value() == materials
    place = fields.get_by_role("textbox", name=place_name)
    assert place.input_value() == location_on_card
    # Dismissing the inherited state needs no discard confirmation. Reopening
    # still offers every control, even when all of the card answers were complete.
    prompts = []
    page.on("dialog", lambda prompt: (prompts.append(prompt.message), prompt.dismiss()))
    dialog.get_by_role("button", name="Close", exact=True).click()
    dialog.wait_for(state="detached")
    assert not prompts
    card.locator(".mail-write").click()
    send = dialog.get_by_role("button", name="Send", exact=True)
    if not location_on_card:
        send.click()
        assert place.evaluate("n => n === document.activeElement")
    place.fill("Room <B> & east")
    fields.get_by_role("button", name="Email", exact=True).click()
    expected = f"Meet: {times} · Room <B> & east\nBring: {materials}\nFormat: Email"
    assert dialog.locator(".writer-body").inner_text() == expected
    assert not [p for p, _ in calls if p in ("/rem/approve", "/rem/draft")]
    answers["/rem/approve"] = lambda payload: (200, {"results": [{"id": i, "status": "sent"} for i in payload["ids"]]})
    send.click()
    dialog.wait_for(state="detached")
    assert [body["bodies"] for path, body in calls if path == "/rem/approve"] == [{"reply:ines": expected}]


def test_public_display_removes_archive_headers_and_bodies(today):
    page, _, _ = today
    dialog = _open(page)
    assert dialog.locator('.writer-msg').count() == 2
    page.evaluate('setPrivacy("public", {save: false})', isolated_context=False)
    assert dialog.locator('.writer-msg').count() == 0
    dialog.get_by_role('button', name='Close', exact=True).click()
    page.locator('.qcard.open .mail-write').click()
    assert page.locator('dialog.writer .writer-msg').count() == 0
