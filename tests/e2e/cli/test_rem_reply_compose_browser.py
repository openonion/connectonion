"""The full-screen reply writer and the reply card's channels (#3303, #3302) (opt in).

Owner, 2026-11-22, on a Today reply opened full screen: no close where he looked, nothing showed it was a
dialog, REM's question sat in the letter with nowhere to answer it, and Send seemed to do nothing. On an
email reply the card offered Lark and WhatsApp for someone he has never chatted with. Served like
test_rem_today_fuse_browser.py, from the invented notebook in tests/fixtures; every /rem/* call is stubbed,
so nothing is ever sent.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import DRAFT, OVERDUE, today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _card(page, width=1440, channels=None, body=None):
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    if channels is not None or body is not None:
        page.evaluate("""([channels, body]) => {
          if (channels) REM.drafts[0].channels = channels;
          if (body) { REM.drafts[0].body = body; REM.approval_outcomes[0].body = body; }
          render();
        }""", [channels, body], isolated_context=False)
    page.evaluate("scrollTo(0, 0)", isolated_context=False)
    return page.locator(".qcard.open")


def _writer(page, width=1440, **kw):
    _card(page, width, **kw).locator(".mail-write").click()
    dialog = page.locator("dialog.writer[open]")
    dialog.wait_for()
    return dialog


def test_the_writer_has_a_title_bar_with_close_at_the_top_right_and_esc_closes(today):
    page, _, _ = today
    dialog = _writer(page, 1440)
    title = dialog.locator(".writer-title")
    assert "Ines Halvorsen" in title.inner_text() and "Outlook" in title.inner_text()
    close = title.get_by_role("button", name="Close", exact=True)
    box, frame = close.bounding_box(), dialog.bounding_box()
    # The close sits in the dialog's top-right corner, where every dialog keeps it.
    assert box["x"] + box["width"] > frame["x"] + frame["width"] - 64 and box["y"] < frame["y"] + 64
    page.keyboard.press("Escape")
    assert page.locator("dialog.writer").count() == 0


def test_on_a_phone_the_writer_is_a_sheet_with_cancel_left_and_send_right(today):
    page, _, _ = today
    dialog = _writer(page, 390)
    title = dialog.locator(".writer-title")
    cancel, send = title.get_by_role("button", name="Cancel", exact=True), title.get_by_role("button", name="Send", exact=True)
    assert cancel.is_visible() and send.is_visible()
    assert cancel.bounding_box()["x"] < 80 and send.bounding_box()["x"] > 390 - 140
    cancel.click()
    assert page.locator("dialog.writer").count() == 0


def test_the_page_behind_is_dimmed(today):
    page, _, _ = today
    _writer(page)
    backdrop = page.evaluate("getComputedStyle(document.querySelector('dialog.writer'), '::backdrop').backgroundColor", isolated_context=False)
    assert backdrop.startswith("rgba(18, 21, 18")


def test_a_click_outside_closes_an_unchanged_letter(today):
    page, _, _ = today
    _writer(page, 1440)
    page.mouse.click(8, 8)
    assert page.locator("dialog.writer").count() == 0


def test_a_changed_letter_asks_once_before_esc_closes_it(today):
    page, _, _ = today
    dialog = _writer(page)
    dialog.locator(".writer-body").press("End")
    dialog.locator(".writer-body").type(" Thanks!")
    asked = []
    page.once("dialog", lambda d: (asked.append(d.message), d.dismiss()))
    page.keyboard.press("Escape")
    assert asked and page.locator("dialog.writer[open]").count() == 1
    page.once("dialog", lambda d: d.accept())
    dialog.get_by_role("button", name="Close", exact=True).click()
    assert page.locator("dialog.writer").count() == 0


def test_rems_question_is_answered_on_the_right_and_lands_in_the_letter(today):
    page, calls, _ = today
    dialog = _writer(page)
    side = dialog.locator(".writer-side .writer-choices")
    assert side.is_visible()
    assert dialog.locator(".writer-did").inner_text().startswith("REM ")
    # Send before answering: the writer says what is missing and takes the focus to it; nothing is sent.
    dialog.get_by_role("button", name="Send", exact=True).click()
    assert "邮件附件 / 共享文件夹" in dialog.locator(".writer-notice").inner_text()
    assert page.evaluate("!!document.activeElement.closest('.writer-choices')", isolated_context=False)
    assert not [path for path, _ in calls if path in ("/rem/approve", "/rem/draft")]
    side.get_by_role("button", name="共享文件夹").click()
    text = dialog.locator(".writer-body").input_value()
    assert "共享文件夹" in text and "【" not in text


def test_a_typed_answer_on_the_right_takes_the_keyboard(today):
    page, _, _ = today
    body = "Hi Ines,\n\nCould we meet 【需要你：another time — date not agreed】 instead?\n\nAvery"
    dialog = _writer(page, body=body)
    field = dialog.locator(".writer-choices input")
    field.type("Tuesday 2pm")
    assert "Tuesday 2pm" in dialog.locator(".writer-body").input_value()
    # Every visible field in the writer takes the keyboard.
    for box in dialog.locator("input:visible, textarea:visible").all():
        assert box.is_editable()


def test_send_answers_at_once_and_a_refusal_keeps_the_letter_with_retry(today):
    page, _, answers = today
    dialog = _writer(page)
    dialog.locator(".writer-choices").get_by_role("button", name="共享文件夹").click()
    answers["/rem/approve"] = [(409, {"error": "This outcome is no longer current; reload Today"})]
    # The button's own words change in the same tick as the click, before any answer arrives.
    first = page.evaluate("""() => { const b = [...document.querySelectorAll('dialog.writer .writer-actions button')].find(b => b.textContent === 'Send');
      b.click(); return b.textContent; }""", isolated_context=False)
    assert first == "Sending…"
    dialog.locator(".writer-notice").filter(has_text="reload Today").wait_for()
    assert dialog.get_by_role("button", name="Retry", exact=True).is_enabled()
    assert page.locator("dialog.writer[open]").count() == 1


def test_a_sent_reply_says_so_and_the_writer_goes(today):
    page, calls, answers = today
    dialog = _writer(page)
    dialog.locator(".writer-choices").get_by_role("button", name="共享文件夹").click()
    answers["/rem/approve"] = lambda body: (200, {"results": [{"id": i, "status": "sent"} for i in body["ids"]]})
    dialog.get_by_role("button", name="Send", exact=True).click()
    page.locator("dialog.writer").wait_for(state="detached")
    assert calls[-1][0] == "/rem/approve"


def test_the_card_send_button_says_sending_at_once(today):
    page, _, _ = today
    card = _card(page)
    card.locator(".owner-slot").get_by_role("button", name="共享文件夹").click()
    first = page.evaluate("""() => { const b = [...document.querySelectorAll('.qcard.open .mail-actions button')].find(b => b.textContent === 'Send');
      b.click(); return b.textContent; }""", isolated_context=False)
    assert first == "Sending…"


def test_an_email_only_person_is_offered_no_chat_channel(today):
    page, _, _ = today
    card = _card(page, channels=["mail"])
    assert not card.locator(".mail-channels").is_visible()
    assert card.get_by_role("button", name="Lark").count() == 0


def test_a_person_on_whatsapp_too_is_offered_both_and_told_what_switching_does(today):
    page, _, _ = today
    card = _card(page, channels=["mail", "whatsapp"])
    pills = card.locator(".mail-channels button")
    assert pills.all_inner_texts() == ["Mail", "Switch to WhatsApp"]
    assert "chat message" in pills.nth(1).get_attribute("title")
    assert card.locator(".mail-channels").get_by_text("Lark").count() == 0


def test_the_card_shows_its_place_in_the_deck_and_steps_both_ways(today):
    page, _, _ = today
    card = _card(page)
    count = card.locator(".qcount")
    assert count.is_visible() and count.inner_text().startswith("1 / ")
    nav = card.locator(".qnav")
    assert nav.evaluate("n => getComputedStyle(n.closest('.qhead-acts')).opacity") == "1"
    nav.get_by_role("button", name="Next card · J").click()
    raised = page.locator(".qcard.focal .qcount")
    assert raised.inner_text().startswith("2 / ")
    page.locator(".qcard.focal .qnav").get_by_role("button", name="Previous card · K").click()
    assert page.locator(".qcard.focal .qcount").inner_text().startswith("1 / ")


def test_send_is_the_cards_one_filled_button_and_triage_waits_in_more(today):
    page, _, _ = today
    card = _card(page)
    filled = card.locator(".qdraft .btn-act:visible")
    assert filled.count() == 1 and filled.inner_text() == "Send"
    # Send never looks disabled, even with a question open.
    assert filled.get_attribute("aria-disabled") is None
    card.locator(".qdraft .more-menu summary").click()
    menu = card.locator(".qdraft .more-menu .menu")
    for word in ("Mark done", "Not now", "Ignore"):
        assert menu.get_by_role("button", name=word, exact=True).is_visible()
    # The row's own strip is not drawn a second time above the letter.
    assert card.locator(".qitem .handoff-line:visible").count() == 0


def test_the_letter_is_read_whole_and_rem_says_what_it_did(today):
    page, _, _ = today
    card = _card(page)
    letter = card.locator(".mail-body")
    assert letter.evaluate("n => n.scrollHeight <= n.clientHeight + 4")
    assert "Avery" in card.locator(".mail-text").inner_text()
    assert card.locator(".mail-did").inner_text().startswith("REM ")


def test_a_long_letter_fades_and_opens_whole(today):
    page, _, _ = today
    body = "Hi Ines,\n\n" + "\n".join(f"Line {n} of a long reply." for n in range(1, 31)) + "\n\nAvery"
    card = _card(page, body=body)
    unfold = card.get_by_role("button", name="Show the whole letter")
    unfold.wait_for()
    unfold.click()
    assert card.locator(".mail-body").evaluate("n => n.scrollHeight <= n.clientHeight + 4")


def test_a_reply_written_for_a_chat_the_person_is_not_on_is_shown_as_a_defect_and_not_sent(today):
    page, calls, _ = today
    page.set_viewport_size({"width": 1440, "height": 900})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("""() => { Object.assign(REM.drafts[0], {channel: 'lark', channels: ['mail'], channel_defect: true,
      body: 'Hi Ines, the receipts are in the shared folder.'}); REM.approval_outcomes = []; render(); }""", isolated_context=False)
    card = page.locator(".qcard.open")
    defect = card.locator(".mail-defect")
    assert "can't be reached there" in defect.inner_text()
    card.locator(".mail-actions").get_by_role("button", name="Send", exact=True).click()
    assert "can't be reached there" in card.locator(".mail-status").inner_text()
    assert not [path for path, _ in calls if path in ("/rem/approve", "/rem/draft")]
    defect.get_by_role("button", name="Rewrite it as an email").click()
    for _ in range(50):
        if any(path == "/rem/draft" for path, _ in calls):
            break
        page.wait_for_timeout(100)
    assert ("/rem/draft", {"id": "ines-receipts", "action": "redraft", "channel": "mail"}) in calls


def test_on_a_phone_send_sits_above_the_tab_bar(today):
    page, _, _ = today
    card = _card(page, 390)
    send = card.locator(".mail-actions").get_by_role("button", name="Send", exact=True)
    send.scroll_into_view_if_needed()
    page.evaluate("scrollBy(0, -200)", isolated_context=False)
    bar = page.locator(".tabbar").bounding_box()
    box = send.bounding_box()
    assert box["y"] + box["height"] <= bar["y"]
