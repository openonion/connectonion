"""Today's reply card never answers a click with silence (opt in).

The owner, 2026-11-18: on Today he opened the reply to one person, clicked Send, and nothing happened: no
request, no word. The letter had one part still to fill, so Send was a disabled button and the only hint was
a caption beside it. He also could not find full-screen writing (it had moved behind the card's ⋯), and the
Talk it over buttons in an item's Show more sheet sat as a column of grey words indented under the heading.
Served like test_rem_today_fuse_browser.py, from the invented notebook in tests/fixtures.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import DRAFT, GREEN, OVERDUE, today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

INK = ("rgb(18, 21, 18)", "rgb(236, 238, 235)")


def _open(page, width):
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("scrollTo(0, 0)", isolated_context=False)
    return page.locator(".qcard.open")


@pytest.mark.parametrize("width", [1440, 390])
def test_send_with_a_part_left_to_fill_says_so_and_takes_the_focus_there(today, width):
    page, calls, _ = today
    card = _open(page, width)
    send = card.locator(".mail-actions").get_by_role("button", name="Send", exact=True)
    # It looks unready and is not green, but it is not a dead button: the click is answered.
    assert send.get_attribute("aria-disabled") == "true" and send.get_attribute("disabled") is None
    assert send.evaluate("n => getComputedStyle(n).backgroundColor") not in GREEN
    send.click(force=True)  # what a person's click does; Playwright would otherwise wait for "enabled"
    assert card.locator(".mail-status").inner_text() == "Fill the marked part first"
    assert page.evaluate("!!document.activeElement.closest('.qcard.open .owner-slot')", isolated_context=False)
    assert not [path for path, _ in calls if path in ("/rem/approve", "/rem/draft")]
    card.locator(".owner-slot").get_by_role("button", name="共享文件夹").click()
    assert send.get_attribute("aria-disabled") is None and card.locator(".mail-status").inner_text() == ""


@pytest.mark.parametrize("width", [1440, 390])
def test_a_held_send_says_when_it_goes_out_and_keeps_undo_beside_it(today, width):
    page, calls, answers = today
    card = _open(page, width)
    release = page.evaluate("new Date(Date.now() + 10 * 60 * 1000).toISOString()")
    answers["/rem/approve"] = lambda body: (200, {"release_at": release, "results": [
        {"id": i, "status": "held", "release_at": release} for i in body["ids"]]})
    when = page.evaluate("iso => fmtTime(iso)", release, isolated_context=False)
    card.locator(".owner-slot").get_by_role("button", name="共享文件夹").click()
    card.get_by_role("button", name="Send", exact=True).click()
    # The card says the same for the moment before Today deals the next one (at once with motion stilled); the line
    # Today keeps after it is what stays, with the one Undo.
    note = page.locator(".qsent")
    note.wait_for()
    assert note.locator(".lede").inner_text() == f"Sending to Inès Halvorsen at {when}."
    assert note.get_by_role("button", name="Undo", exact=True).is_visible()
    assert _in_view(page, note)
    assert calls[-1][0] == "/rem/approve"


@pytest.mark.parametrize("width", [1440, 390])
def test_a_refused_send_shows_the_hosts_words_on_the_card(today, width):
    page, _, answers = today
    card = _open(page, width)
    answers["/rem/approve"] = [(409, {"error": "This outcome is no longer current; reload Today"})]
    card.locator(".owner-slot").get_by_role("button", name="共享文件夹").click()
    card.get_by_role("button", name="Send", exact=True).click()
    card.locator(".mail-status").filter(has_text="reload Today").wait_for()
    assert card.get_by_role("button", name="Send", exact=True).is_enabled()


@pytest.mark.parametrize("lang", ["en", "zh"])
@pytest.mark.parametrize("width", [1440, 390])
def test_write_full_screen_is_in_sight_beside_send_and_opens_the_writer(today, width, lang):
    page, _, _ = today
    card = _open(page, width)
    page.evaluate(f"() => {{ setInterfaceLanguage('{lang}'); render(); scrollTo(0, 0); }}", isolated_context=False)
    card = page.locator(".qcard.open")
    name, send_name = ("全屏写", "发送") if lang == "zh" else ("Write full screen", "Send")
    write = card.locator(".mail-actions").get_by_role("button", name=name, exact=True)
    assert write.is_visible()  # no ⋯ to open first
    assert card.locator(".more-menu .menu").get_by_role("button", name=name).count() == 0
    send = card.locator(".mail-actions").get_by_role("button", name=send_name, exact=True)
    if os.environ.get("CO_REM_SHOTS"):
        page.screenshot(path=str(Path(os.environ["CO_REM_SHOTS"]) / f"today-write-visible-{lang}-{width}.png"))
    assert abs(write.bounding_box()["y"] - send.bounding_box()["y"]) < 8  # one row with Send
    write.click()
    page.locator("dialog.writer").wait_for()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_the_show_more_sheet_offers_talk_as_one_row_of_ink_buttons(today, width):
    page, _, _ = today
    card = _open(page, width)
    if width < 400:
        card.locator(".qfull").click()  # on a phone a card with a reply keeps Show more behind More of this card
    card.locator(".strip-more").first.click()
    sheet = page.locator("#item-context")
    talk = sheet.locator("[data-talk]")
    talk.first.wait_for()
    boxes = [talk.nth(i).bounding_box() for i in range(talk.count())]
    assert len(boxes) == 2 and abs(boxes[0]["y"] - boxes[1]["y"]) < 1, boxes  # side by side
    assert all(box["height"] >= 44 for box in boxes), boxes
    assert all(talk.nth(i).evaluate("n => getComputedStyle(n).color") in INK for i in range(2))
    heading = sheet.locator(".context-part h3").last.bounding_box()
    assert abs(boxes[0]["x"] - heading["x"]) < 1, (boxes[0], heading)  # flush with the sheet's text
    sheet_box = sheet.bounding_box()
    assert boxes[1]["x"] + boxes[1]["width"] <= sheet_box["x"] + sheet_box["width"]
    if os.environ.get("CO_REM_SHOTS"):
        page.screenshot(path=str(Path(os.environ["CO_REM_SHOTS"]) / f"today-more-sheet-{width}.png"))


def _in_view(page, locator):
    box, view = locator.bounding_box(), page.viewport_size
    return box["y"] >= 0 and box["y"] + box["height"] <= view["height"]


def test_the_writer_of_a_lark_reply_says_it_leaves_through_lark(today):
    """Seen on the owner's copy: the full-screen writer of a Lark reply said it would send from his Outlook mailbox."""
    page, _, _ = today
    _open(page, 1440)
    page.evaluate("() => { REM.drafts[0].channel = 'lark'; render(); scrollTo(0, 0); }", isolated_context=False)
    page.locator(".qcard.open .mail-write").click()
    note = page.locator("dialog.writer .mail-note").inner_text()
    assert "lark-cli" in note and "Outlook" not in note


@pytest.mark.parametrize("width", [1440, 390])
def test_after_a_reload_the_held_reply_bar_is_one_line_not_a_sheet_over_today(today, width):
    """The Host rebuilds the page after a Send, so the open page reloads and Today's own line is gone; the held reply's
    Undo bar is then the feedback. On a phone its two edges (top 12px, and the base rule's bottom) stretched it over
    the whole screen."""
    page, _, _ = today
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    release = page.evaluate("new Date(Date.now() + 10 * 60 * 1000).toISOString()")
    held = {"id": "reply:ines", "kind": "reply", "status": "held", "release_at": release, "to": "ines@example.test"}
    page.evaluate("held => { REM.live = true; REM.approval_pending = [held]; render(); }", held, isolated_context=False)
    bar = page.locator("#approval-undo")
    box = bar.bounding_box()
    assert box["height"] <= 72, box
    assert bar.get_by_role("button", name="Undo", exact=True).is_visible()
