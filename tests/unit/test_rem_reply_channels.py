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


def test_a_draft_already_rewritten_for_a_channel_keeps_it(channels):
    assert channels(saved={"channel": "whatsapp"}) == ["mail", "whatsapp"]


def test_a_person_with_no_page_gets_mail(tmp_path, monkeypatch):
    monkeypatch.setattr(drafts, "_identities", lambda root, row: {"person": {}})
    assert drafts.reachable_channels(tmp_path, {"id": "r1"}, {}) == ["mail"]
