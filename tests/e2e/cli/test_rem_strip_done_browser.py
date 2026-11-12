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


# The row the owner already answered, with a reply the night prepared for the same mail thread: the state in
# which the row used to lead with a green Mark done of its own. The Host fixture has no mail, so the page is told.
REPLIED_AND_PREPARED = r"""() => {
  const r = byPath('projects/fernhill.md'), old = doneKey(threadEntries().find(e => /pilot review/.test(e.t.text)));
  r.original = undefined;
  r.text = r.text.replace('You owe Mara a pilot review.', 'You owe Mara a pilot review [1].')
    .replace('## Sources\n', '## Sources\n- [1] outlook:pilot-review\n');
  REM.source_context = {...REM.source_context, 'outlook:pilot-review': {source: 'outlook', thread: 'mail:fixture:pilot'}};
  REM.drafts = [{id: 'pilot', version: 'v1', provider: 'outlook', thread: 'mail:fixture:pilot', status: 'prepared',
    to: 'Mara Ostrowski <mara@example.test>', from: 'avery@example.test', subject: 'Re: Pilot review', body: 'The review is attached.'}];
  KNOWN.clear(); FACTS.clear(); threadEntries.cached = null;
  const key = doneKey({r, t: threads(r).items.find(t => /pilot review/.test(t.text))});
  REM.today_queue = REM.today_queue.map(row => row.key !== old ? row : {...row, key, keys: [key], text: 'You owe Mara a pilot review [1].',
    reply: {state: 'replied', last_word_yours: true, provider: 'outlook', thread: 'mail:fixture:pilot', source: 'outlook:pilot-review'}});
  render();
  const entry = threadEntries().find(e => doneKey(e) === key);
  return {draft: threadDraft(entry)?.status, reply: REM.today_queue.find(row => row.key === key).reply.state};
}"""


def test_a_replied_row_with_a_prepared_reply_has_one_quiet_mark_done(live):
    """Review of #2955: only the first branch of the row's actions knew about the strip, so a row that was
    replied to and had a prepared reply showed two Mark done, one of them green."""
    page, _ = live
    assert page.evaluate(REPLIED_AND_PREPARED, isolated_context=False) == {"draft": "prepared", "reply": "replied"}
    rows = page.locator(".task-band ul.threads > li")
    assert rows.count() >= 2
    for i in range(rows.count()):
        assert rows.nth(i).get_by_role("button", name="Mark done", exact=True).count() == 1
    row = _row(page, "pilot review")
    done = row.get_by_role("button", name="Mark done", exact=True)
    assert done.evaluate("node => node.className + '|' + !!node.closest('.handoff-line')") == "btn-quiet|true"
    assert row.locator(".btn-act").count() == 0        # nothing green on the row: its reply is already written


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
