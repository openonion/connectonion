"""A reply card offers only the channels this person can be reached on (#3302).

Owner, 2026-11-22: an email reply offered "redraft with Lark / WhatsApp" for someone he has never chatted
with on either. Chats are read live and never stored, so the evidence is the person's own page: a cited chat
source or a handle it names, and for WhatsApp the number the send goes to.
"""

import pytest

from connectonion.rem import drafts
from connectonion.rem.files import Notebook

PAGE = "# Sam Rivers\n\n## Facts\n- Email: sam@example.test\n{facts}\n\n## Sources\n- [1] outlook:abc — 2026-11-01\n{sources}\n"


@pytest.fixture
def channels(tmp_path, monkeypatch):
    def of(facts="", sources="", saved=None):
        Notebook(tmp_path).write("people/sam.md", PAGE.format(facts=facts, sources=sources))
        monkeypatch.setattr(drafts, "_identities", lambda root, row: {"person": {"page": "people/sam.md"}})
        return drafts.reachable_channels(tmp_path, {"id": "r1"}, saved or {})
    return of


def test_an_email_only_person_is_offered_mail_alone(channels):
    assert channels() == ["mail"]


def test_a_phone_number_alone_is_not_a_whatsapp_thread(channels):
    assert channels(facts="- Phone: +61 400 000 000") == ["mail"]


def test_a_cited_whatsapp_chat_with_a_number_offers_whatsapp(channels):
    assert channels(facts="- Phone: +61 400 000 000", sources="- [2] whatsapp:61400000000@s.whatsapp.net:9 — 2026-11-02") == ["mail", "whatsapp"]


def test_a_whatsapp_chat_without_a_number_cannot_be_sent_to(channels):
    assert channels(sources="- [2] whatsapp:group@g.us:9 — 2026-11-02") == ["mail"]


def test_a_lark_handle_or_chat_offers_lark(channels):
    assert channels(facts="- Handles: Lark sam.rivers") == ["mail", "lark"]
    assert channels(sources="- [3] lark:oc_123:7 — 2026-11-03") == ["mail", "lark"]


def test_a_draft_rewritten_for_a_chat_does_not_make_that_chat_reachable(channels):
    assert channels(saved={"channel": "lark"}) == ["mail"]


def test_a_person_with_no_page_gets_mail(tmp_path, monkeypatch):
    monkeypatch.setattr(drafts, "_identities", lambda root, row: {"person": {}})
    assert drafts.reachable_channels(tmp_path, {"id": "r1"}, {}) == ["mail"]


# The drafting path keeps the same rule as the buttons (#3312 C). Live, an Outlook thread was stored as a Lark
# draft for someone with no Lark chat, while the card still said Outlook; its send would have gone via lark-cli.
ID = "0" * 31 + "1"
ROW = {"id": ID, "provider": "outlook", "thread": "t1", "private": False, "version": "v1"}


@pytest.fixture
def mail_only(tmp_path, monkeypatch):
    Notebook(tmp_path).write("people/sam.md", PAGE.format(facts="", sources=""))
    monkeypatch.setattr(drafts, "_identities", lambda root, row: {"person": {"page": "people/sam.md"}})
    monkeypatch.setattr(drafts, "candidates", lambda root, **kw: [ROW])
    return tmp_path


def _saved(root, **extra):
    from connectonion.rem.files import write_json
    saved = {"id": ID, "version": "v1", "provider": "outlook", "status": "prepared", "to": "sam@example.test",
             "from": "me@example.test", "subject": "Re: plan", "body": "Hi Sam, yes.", "in_reply_to": "m1", "cc": "", **extra}
    drafts.path(root, ID).parent.mkdir(parents=True, exist_ok=True)
    write_json(drafts.path(root, ID), saved)
    return saved


def test_redrafting_onto_a_chat_the_person_is_not_on_is_refused(mail_only, monkeypatch):
    _saved(mail_only)
    monkeypatch.setattr(drafts, "_current", lambda root, draft_id, refresh_index=True: drafts.read_json(drafts.path(root, draft_id), {}))
    monkeypatch.setattr(drafts, "_write_now", lambda *a: pytest.fail("no redraft may run"))
    with pytest.raises(drafts.RemError, match="cannot be reached on Lark"):
        drafts.redraft(mail_only, ID, "lark")


def test_a_stored_lark_draft_for_an_outlook_thread_is_a_defect_and_is_not_sent(mail_only, monkeypatch):
    _saved(mail_only, channel="lark")
    monkeypatch.setattr(drafts, "_current", lambda root, draft_id, refresh_index=True: drafts.read_json(drafts.path(root, draft_id), {}))
    monkeypatch.setattr(drafts, "_send_chat", lambda *a: pytest.fail("nothing may go out on Lark"))
    with pytest.raises(drafts.RemError, match="cannot be reached on Lark"):
        drafts._send_locked(mail_only, ID)
    listed, = [d for d in drafts.listing(mail_only) if d["id"] == ID]
    assert listed["channel_defect"] is True and listed["channels"] == ["mail"]


def test_an_outlook_threads_draft_is_stored_and_sent_as_outlook(mail_only, monkeypatch):
    _saved(mail_only)
    monkeypatch.setattr(drafts, "_current", lambda root, draft_id, refresh_index=True: drafts.read_json(drafts.path(root, draft_id), {}))
    sent = []

    class Outlook:
        def reply(self, message, text, cc=None):
            sent.append((message, text))
            return {"ok": True}
    monkeypatch.setattr(drafts, "mail_client", lambda provider: Outlook() if provider == "outlook" else pytest.fail(provider))
    monkeypatch.setattr(drafts, "_send_chat", lambda *a: pytest.fail("an email reply never leaves through a chat"))
    listed, = [d for d in drafts.listing(mail_only) if d["id"] == ID]
    assert listed.get("channel", "mail") == "mail" and listed["channel_defect"] is False
    drafts._send_locked(mail_only, ID)
    assert sent == [("m1", "Hi Sam, yes.")]
