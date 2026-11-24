"""A reply stored on a channel the person can't be reached on is redrafted by REM, not left for the owner (#3348).

Owner's rule: a mistake the system can undo, the system fixes. A live Outlook thread sat drafted as a Lark message
for someone with no Lark chat; the card showed the defect and waited for the owner to press 改写成邮件, and it only
became an email again because the thread moved on and the next round happened to draft afresh. Now the drafting
queue offers such a draft again on purpose, it is rewritten on the thread's own channel, and the card says so.
"""

import json

import pytest

from connectonion.rem import drafts, threads
from connectonion.rem.files import Notebook, write_json

ID = "0" * 31 + "2"
PAGE = "# Sam Rivers\n\n## Facts\n- Email: sam@example.test\n\n## Sources\n- [1] outlook:abc — 2026-11-01\n"
ROW = {"id": ID, "provider": "outlook", "thread": "t1", "private": False, "version": "v1", "time": "2026-11-21T09:00:00",
       "to": "sam@example.test", "from": "me@example.test", "cc": "", "subject": "Re: plan", "in_reply_to": "m1",
       "material": [{"source": "outlook:m1", "message": {}}], "obligations": []}


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    Notebook(tmp_path).write("people/sam.md", PAGE)
    monkeypatch.setattr(drafts, "_identities", lambda root, row: {"person": {"page": "people/sam.md"}})
    monkeypatch.setattr(drafts, "candidates", lambda root, **kw: [dict(ROW)])
    monkeypatch.setattr(threads, "listing", lambda root: {})
    import connectonion.rem.today as today
    monkeypatch.setattr(today, "queue", lambda root, states=None: [])
    return tmp_path


def _saved(root, **extra):
    saved = {"id": ID, "version": "v1", "provider": "outlook", "status": "prepared", "to": "sam@example.test",
             "from": "me@example.test", "subject": "Re: plan", "body": "Hi Sam, yes.", "in_reply_to": "m1", "cc": "", **extra}
    drafts.path(root, ID).parent.mkdir(parents=True, exist_ok=True)
    write_json(drafts.path(root, ID), saved)
    return saved


def test_a_draft_on_an_unreachable_channel_is_named_and_a_mail_draft_is_not(notebook):
    assert drafts.wrong_channel(notebook, ROW, _saved(notebook, channel="lark")) == "lark"
    assert drafts.wrong_channel(notebook, ROW, _saved(notebook)) is None


def test_only_a_current_prepared_draft_counts(notebook):
    # A sent or held reply is history, and a draft of an older message is already being replaced.
    assert drafts.wrong_channel(notebook, ROW, _saved(notebook, channel="lark", status="sent")) is None
    assert drafts.wrong_channel(notebook, ROW, _saved(notebook, channel="lark", status="held")) is None
    assert drafts.wrong_channel(notebook, ROW, _saved(notebook, channel="lark", version="v0")) is None


def test_the_queue_offers_a_wrong_channel_draft_again_marked_for_redraft(notebook):
    _saved(notebook, channel="lark")
    row, = drafts.queue(notebook)
    assert row["id"] == ID and row["redrafted_from"] == "lark" and row.get("channel", "mail") == "mail"


def test_a_good_mail_draft_is_not_offered_again(notebook):
    _saved(notebook)
    assert drafts.queue(notebook) == []


def test_the_redraft_lands_as_an_outlook_draft_with_the_note_and_no_defect(notebook):
    # The drafting step the night and the daily round both run: prepare → model → check → promote.
    _saved(notebook, channel="lark")
    row, = drafts.queue(notebook)
    task = {"row": row, "candidate": "candidate.json"}
    plan = drafts.check(task, {"result": json.dumps({"body": "Hi Sam, yes — Thursday works.", "sources": ["outlook:m1"]})})
    drafts.promote(notebook, plan)
    listed, = [d for d in drafts.listing(notebook) if d["id"] == ID]
    assert listed.get("channel", "mail") == "mail"
    assert listed["channel_defect"] is False
    assert listed["redrafted_from"] == "lark"


def test_an_ordinary_redraft_carries_no_stale_note(notebook):
    _saved(notebook, channel="mail", redrafted_from="lark")
    row = {**ROW, "version": "v2"}
    plan = drafts.check({"row": row, "candidate": "c.json"}, {"result": json.dumps({"body": "Hi again.", "sources": ["outlook:m1"]})})
    drafts.promote(notebook, plan)
    assert "redrafted_from" not in drafts.read_json(drafts.path(notebook, ID), {})


def test_the_night_does_not_count_a_wrong_channel_draft_as_prepared(notebook, monkeypatch):
    from connectonion.rem import night
    _saved(notebook, channel="lark")
    key = "people/sam.md::reply"
    owed = {"key": key, "keys": [key], "reply": {"state": "queued", "source": "v1"}, "record": "people/sam.md",
            "title": "Sam Rivers", "text": "Reply to Sam about the plan"}
    monkeypatch.setattr(night, "_owed", lambda rows: [owed])
    monkeypatch.setattr(night, "_draft_for", lambda row, candidates: dict(ROW))
    monkeypatch.setattr(night, "_revision", lambda row: "r")
    outcome, = night.listing(notebook, rows=[owed])
    assert outcome["kind"] != "prepared"
