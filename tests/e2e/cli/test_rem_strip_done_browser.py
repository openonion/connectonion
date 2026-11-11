"""标为完成 in the hand-off strip of every unfinished row, before and after a hand-off (opt in).

Owner, 2026-11-11: «界面里面有好几个功能，Codex、看结果、撤销、聊一聊之类的，为什么不能标记已完成呢？标记完成不在那个里面啊».
The strip's Mark done is the row's own setDone, so it posts the same /rem/thread decision; taking a task
back from the agent has its own words, so it never reads like undoing the item. Same live Host fixture as
test_rem_hand_any_row_browser.py: real rem_http, recorded fake agents, an invented notebook.
"""

import json
import os

import pytest

from tests.e2e.cli.test_rem_hand_any_row_browser import _row, live  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _posts(page, path):
    sent = []
    page.on("request", lambda request: sent.append(json.loads(request.post_data or "{}"))
            if request.method == "POST" and request.url.split("#")[0].endswith(path) else None)
    return sent


def test_every_waiting_row_has_one_mark_done_in_its_strip(live):
    page, _ = live
    rows = page.locator(".task-band ul.threads > li")
    assert rows.count() >= 2
    for i in range(rows.count()):
        row = rows.nth(i)
        assert row.get_by_role("button", name="Mark done", exact=True).count() == 1          # one per row
        assert row.locator(".handoff-line").get_by_role("button", name="Mark done", exact=True).count() == 1


def test_mark_done_from_the_strip_is_the_rows_own_decision(live):
    page, root = live
    from connectonion.rem import threads
    posts = _posts(page, "/rem/thread")
    row = _row(page, "Fernhill Labs contract draft")
    row.locator(".handoff-line").get_by_role("button", name="Mark done", exact=True).click()
    page.get_by_text("Saved in notebook", exact=True).wait_for()
    assert [post["state"] for post in posts] == ["done"]
    assert [value["state"] for value in threads.listing(root).values()] == ["done"]
    open_row = page.locator(".task-band ul.threads > li").filter(has_text="Fernhill Labs contract draft")
    assert open_row.count() == 0                                                     # it leaves the open list
    page.locator("#done-notice").get_by_role("button", name="Undo", exact=True).click()
    open_row.wait_for()


def test_after_a_hand_off_the_strip_still_marks_done_and_take_back_is_not_undo(live):
    page, root = live
    posts = _posts(page, "/rem/thread")
    row = _row(page, "Fernhill Labs contract draft")
    row.get_by_role("button", name="Hand to Codex").click()
    line = row.locator(".handoff-line")
    line.get_by_text("Codex is working").wait_for(timeout=10000)
    assert line.get_by_role("button").all_inner_texts() == ["Stop", "Take back from Codex", "Mark done"]
    line.get_by_text("Codex finished").wait_for(timeout=30000)
    labels = line.get_by_role("button").all_inner_texts()
    assert labels == ["See result", "Take back from Codex", "Mark done"] and "Undo" not in labels
    line.get_by_role("button", name="Mark done", exact=True).click()
    page.get_by_text("Saved in notebook", exact=True).wait_for()
    assert [post["state"] for post in posts] == ["done"]
