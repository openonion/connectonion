"""Who a reply goes to decides how it is sent (#3121), from the reader (opt in).

The owner, 2026-11-19: «回邮件如果是给我合伙人回，那就直接发就好了…每一个人背后都有他自己的一套审批». A reply card's ⋯ and
a person's ⋯ say in words what one click will change for that person, and a reply REM is sending itself says to
whom and when, with Undo. Served like test_rem_today_fuse_browser.py, from the invented notebook in tests/fixtures.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import DRAFT, OVERDUE, today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _card(page, width):
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    return page.locator(".qcard.open")


@pytest.mark.parametrize("width", [1440, 390])
def test_the_reply_cards_menu_sends_to_this_person_directly_from_now_on(today, width):
    page, calls, answers = today
    card = _card(page, width)
    answers["/rem/direct-send"] = lambda body: (200, {"page": body["page"], "direct_send": body["tier"]})
    card.locator(".more-menu > summary").click()
    item = card.locator(".more-menu .direct-send")
    assert item.inner_text().splitlines() == ["Send to them directly from now on", "REM replies to them without asking; 10 minutes to undo"]
    assert item.bounding_box()["height"] >= 44 or width > 400
    item.click()
    path, body = calls[-1]
    assert path == "/rem/direct-send" and body["tier"] == "partner" and body["page"].startswith("people/")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)
    assert item.inner_text() == "Saved: REM sends to them directly"  # the click is answered in place
    # The same person's next menu offers the way back.
    page.evaluate("render()", isolated_context=False)
    card = page.locator(".qcard.open")
    card.locator(".more-menu > summary").click()
    assert card.locator(".more-menu .direct-send").inner_text().startswith("Show me first from now on")


@pytest.mark.parametrize("width", [1440, 390])
def test_a_reply_rem_is_sending_itself_says_to_whom_and_when_with_undo(today, width):
    page, calls, answers = today
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    release = page.evaluate("new Date(Date.now() + 8 * 60 * 1000).toISOString()")
    page.evaluate("""release => { REM.live = true; REM.approval_pending = [{id: 'reply:mara', kind: 'reply', by: 'rem', status: 'held',
      title: 'Mara Quill', release_at: release}]; approvalUndoBar(false); }""", release, isolated_context=False)
    bar = page.locator("#approval-undo")
    bar.wait_for()
    when = page.evaluate("iso => new Date(iso).toLocaleTimeString('en', {hour: '2-digit', minute: '2-digit'})", release, isolated_context=False)
    assert bar.inner_text().startswith(f"Sending to Mara Quill at {when} · ")
    answers["/rem/approve"] = lambda body: (200, {"results": [{"id": i, "status": "cancelled"} for i in body["ids"]]})
    bar.get_by_role("button", name="Undo").click()
    assert calls[-1] == ("/rem/approve", {"action": "undo", "ids": ["reply:mara"]})
