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
      const message = (from, to, excerpt) => ({source: 'outlook', participants: {from, to: [to]},
        subject: 'Q3 receipts', thread: draft.thread, excerpt});
      draft.sources = ['outlook:inbound'];
      Object.assign(REM.source_context, {
        'outlook:inbound': message('ines@example.test', draft.from, 'Please send the receipts by Friday.'),
        'outlook:sample': message(draft.from, 'ines@example.test', 'Last quarter I attached the invoices.'),
        'outlook:other': {...message(draft.from, 'other@example.test', 'Unrelated private reply.'), thread: 'other'}
      });
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
