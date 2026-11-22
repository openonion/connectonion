"""Full screen keeps the channel defect the card shows, and a reply REM rewrote says so (#3348) (opt in).

Live on rc11: the card showed a Lark draft's defect, but 全屏写 on the same draft read "回复 … · Lark" with a filled
发送 and no warning. Card and full screen now read one answer (replyChannel). Every /rem/* call is stubbed.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import DRAFT, OVERDUE, today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

DEFECT = """() => { Object.assign(REM.drafts[0], {channel: 'lark', channels: ['mail'], channel_defect: true,
  body: 'Hi Ines, the receipts are in the shared folder.'}); REM.approval_outcomes = []; render(); }"""
REWRITTEN = """() => { Object.assign(REM.drafts[0], {channel: 'mail', channels: ['mail'], channel_defect: false,
  redrafted_from: 'lark', body: 'Hi Ines, the receipts are in the shared folder.'}); REM.approval_outcomes = []; render(); }"""


def _open(page, state, width):
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate(state, isolated_context=False)
    page.evaluate("scrollTo(0, 0)", isolated_context=False)
    return page.locator(".qcard.open")


@pytest.mark.parametrize("width", [1440, 390])
def test_full_screen_shows_the_defect_and_holds_send(today, width):
    page, calls, _ = today
    card = _open(page, DEFECT, width)
    card.locator(".mail-write").click()
    dialog = page.locator("dialog.writer[open]")
    dialog.wait_for()
    band = dialog.locator(".writer-defect")
    assert band.is_visible() and "can't be reached there" in band.inner_text()
    send = dialog.locator(".writer-send-top" if width < 720 else ".writer-actions .btn-act")
    send.click()
    page.wait_for_timeout(300)
    assert "can't be reached there" in dialog.locator(".writer-notice").inner_text()
    assert not [path for path, _ in calls if path in ("/rem/approve", "/rem/draft")]
    assert dialog.is_visible()  # held, not sent and not closed


def test_full_screen_fix_rewrites_it_as_an_email(today):
    page, calls, _ = today
    card = _open(page, DEFECT, 1440)
    card.locator(".mail-write").click()
    dialog = page.locator("dialog.writer[open]")
    dialog.wait_for()
    dialog.locator(".writer-defect").get_by_role("button", name="Rewrite it as an email").click()
    for _ in range(50):
        if any(path == "/rem/draft" for path, _ in calls):
            break
        page.wait_for_timeout(100)
    assert ("/rem/draft", {"id": "ines-receipts", "action": "redraft", "channel": "mail"}) in calls
    assert page.locator("dialog.writer[open]").count() == 0


def test_a_reply_rem_rewrote_says_so_on_the_card_and_in_full_screen(today):
    page, calls, _ = today
    card = _open(page, REWRITTEN, 1440)
    note = card.locator(".mail-redrafted")
    assert note.is_visible() and "earlier draft was written for Lark" in note.inner_text()
    assert card.locator(".mail-defect").count() == 0
    card.locator(".mail-write").click()
    dialog = page.locator("dialog.writer[open]")
    dialog.wait_for()
    assert "earlier draft was written for Lark" in dialog.locator(".writer-defect").inner_text()
