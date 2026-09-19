"""The census: what the sources already list, handed over as signals."""

import pytest

from connectonion.wiki.scan import _display_name, scan_people


class Box:
    def __init__(self, me, rows):
        self.me, self.rows = me, rows

    def my_addresses(self):
        return {self.me}

    def list_between(self, start, end, n):
        return [r for r in self.rows if start[:10] <= r["date"][:10] < end[:10]]


def test_the_other_partys_name_comes_from_their_side_of_the_mail():
    """Mail the user sent lists the user in From; a census read the user's own
    display name as Ody's, Dora's and a private Gmail's."""
    sent = {"from": "openonion ai <me@x.y>", "to": ["Ody Zhou <ody@g.com>"], "cc": []}
    assert _display_name(sent, "ody@g.com") == "Ody Zhou"
    received = {"from": "Ody Zhou <ody@g.com>", "to": ["me@x.y"], "cc": []}
    assert _display_name(received, "ody@g.com") == "Ody Zhou"


def test_own_addresses_are_never_correspondents_even_across_mailboxes():
    rows = [{"id": "1", "from": "me@x.y", "to": ["private@gmail.com"], "cc": [], "date": "2026-09-10", "subject": "s"},
            {"id": "2", "from": "Ody <ody@g.com>", "to": ["me@x.y"], "cc": [], "date": "2026-09-11", "subject": "s"}]
    people = scan_people({"outlook": Box("me@x.y", rows)}, days=30, own_addresses={"private@gmail.com"})
    assert [p["address"] for p in people] == ["ody@g.com"]


def test_signals_are_handed_over_and_verdicts_are_not():
    rows = [{"id": "1", "from": "no-reply.products@edm.bank.au", "to": ["me@x.y"], "cc": [], "date": "2026-09-10", "subject": "Statement"},
            {"id": "2", "from": "no-reply.products@edm.bank.au", "to": ["me@x.y"], "cc": [], "date": "2026-09-11", "subject": "Statement"},
            {"id": "3", "from": "Ody <ody@g.com>", "to": ["me@x.y"], "cc": [], "date": "2026-09-11", "subject": "Re: terms"},
            {"id": "4", "from": "me@x.y", "to": ["ody@g.com"], "cc": [], "date": "2026-09-12", "subject": "terms"}]
    people = {p["address"]: p for p in scan_people({"outlook": Box("me@x.y", rows)}, days=30, own_addresses=set())}
    bank, ody = people["no-reply.products@edm.bank.au"], people["ody@g.com"]
    # the pattern anchored at "@" missed this one; anywhere before the @ catches it
    assert bank["automated_hint"] and bank["one_way"]
    assert not ody["automated_hint"] and not ody["one_way"]
    assert ody["sent"] == 1 and ody["received"] == 1
    assert "terms" in ody["subjects"][0]
    # nothing is dropped here: classifying is the Skill's job
    assert len(people) == 2


def test_one_transient_timeout_does_not_end_the_gather(monkeypatch):
    """The owner's first investigation died on one slow body fetch."""
    from connectonion.wiki import investigate as inv

    monkeypatch.setattr(inv.time if hasattr(inv, "time") else __import__("time"), "sleep", lambda s: None)
    calls = {"n": 0}

    class Flaky:
        def my_addresses(self): return {"me@x.y"}
        def list_between(self, s, e, n):
            return [{"id": "1", "from": "Ody <ody@g.com>", "to": ["me@x.y"], "cc": [],
                     "date": "2026-09-10T00:00:00+00:00", "subject": "terms"}]
        def get_email_body(self, i):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("The read operation timed out")
            return "--- Email Body ---\nhello"

    items, coverage = inv.gather("Ody", ["ody"], days=7, clients={"outlook": Flaky()}, subscriptions={})
    assert len(items) == 1 and calls["n"] == 2
    assert "1 matched" in coverage[0]


def test_a_persistent_failure_still_surfaces(monkeypatch):
    from connectonion.wiki import investigate as inv
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)

    class Down:
        def my_addresses(self): return {"me@x.y"}
        def list_between(self, s, e, n): raise TimeoutError("timed out")
        def get_email_body(self, i): return ""

    import pytest
    with pytest.raises(TimeoutError):
        inv.gather("x", ["x"], days=7, clients={"outlook": Down()}, subscriptions={})


def test_a_senders_name_is_read_from_from_name_when_from_is_a_bare_address():
    """Outlook and Gmail hand back `from` bare and the name beside it; a real
    census left Tamara, Vern and Wisiani nameless for exactly this reason."""
    row = {"from": "tamara.berryman@unsw.edu.au", "from_name": "Tamara Berryman", "to": ["me@x.y"], "cc": []}
    assert _display_name(row, "tamara.berryman@unsw.edu.au") == "Tamara Berryman"


def test_material_over_the_room_is_digested_in_order_not_dropped():
    """Ody's investigation kept the newest 107 of 182 and dropped 75 -- the
    oldest, where the terms of the relationship were set."""
    from connectonion.wiki.investigate import digest_in_chunks
    config = {"limits": {"extract_items_per_batch": 3, "extract_chars_per_batch": 10_000}}
    items = [{"text": f"m{d}", "source": f"outlook:{d}", "timestamp": f"2026-09-{d:02d}T00:00:00+00:00", "project": ""}
             for d in range(1, 8)]
    seen = []

    def extractor(chunk, cfg, kind):
        seen.append(([i["text"] for i in chunk], kind))
        return {"notes": "## People\n- " + ",".join(i["text"] for i in chunk), "usage": {"input_tokens": 10}}

    digests, usage = digest_in_chunks(items, config, extractor)
    assert [c for c, _ in seen] == [["m1", "m2", "m3"], ["m4", "m5", "m6"], ["m7"]]   # oldest first, nothing lost
    assert all(kind == "outlook" for _, kind in seen)                              # single-source chunk names its kind
    assert len(digests) == 3 and all(d["role"] == "extract" for d in digests)
    assert usage == {"input_tokens": 30}


def test_a_chunk_with_nothing_worth_keeping_yields_no_digest():
    from connectonion.wiki.investigate import digest_in_chunks
    from connectonion.wiki.extract import NOTHING
    config = {"limits": {"extract_items_per_batch": 40, "extract_chars_per_batch": 10_000}}
    items = [{"text": "noise", "source": "gmail:1", "timestamp": "2026-09-01T00:00:00+00:00", "project": ""}]
    digests, _ = digest_in_chunks(items, config, lambda c, cfg, k: {"notes": NOTHING, "usage": None})
    assert digests == []


def test_the_runner_is_a_choice_between_the_two_harnesses(tmp_path):
    from connectonion.wiki.config import prepare, read_config, set_config
    from connectonion.wiki.files import WikiError
    root = tmp_path / "wiki"; prepare(root)
    assert read_config(root)["runner"] == "codex"
    set_config(root, ["runner", "coai"])
    assert read_config(root)["runner"] == "coai"
    with pytest.raises(WikiError) as caught:
        set_config(root, ["runner", "ollama"])
    assert "codex" in str(caught.value) and "coai" in str(caught.value)


def test_under_coai_the_page_is_read_back_from_disk(tmp_path, monkeypatch):
    """The Skill writes the page itself; what changed is what is on disk, and
    the status line names the sources this code searched."""
    from connectonion.wiki.config import prepare, set_config
    from connectonion.wiki import investigate as inv
    root = tmp_path / "wiki"; prepare(root); set_config(root, ["runner", "coai"])
    nb = inv.Notebook(root)
    nb.stub_person("people/vern.md", "Vern Chan", ["vern"], email="vern.chan@unsw.edu.au")

    class Quiet:
        def my_addresses(self): return {"me@x.y"}
        def list_between(self, s, e, n): return []
        def get_email_body(self, i): return ""

    def fake_co_ai(argv, cwd, capture_output, text, timeout):
        page = root / "people/vern.md"
        import re
        from pathlib import Path
        candidate = Path(re.search(r'NEW file (.+?candidate.md)', argv[-1])[1])
        candidate.write_text(page.read_text().replace("- Phone: Unknown", "- Phone: +61 2 9385 1000 [W1]").replace(
            '- (none yet)', '- [W1] https://example.org/contact — observed 2026-09-19'))
        import json, types
        return types.SimpleNamespace(stdout=json.dumps({"outcome": "natural", "result": "filled", "usage": {"cost": 0.01}}),
                                     stderr="", returncode=0)

    monkeypatch.setattr(inv.subprocess if hasattr(inv, "subprocess") else __import__("subprocess"), "run", fake_co_ai)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/co")
    out = inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                          clients={"outlook": Quiet()}, subscriptions={})
    assert out["changed"] == ["people/vern.md"]
    status = [l for l in nb.read("people/vern.md").splitlines() if l.startswith("Investigation:")][0]
    assert "outlook" in status
    material = next((root / ".state/tasks").glob("*/material.json"))
    assert __import__("json").loads(material.read_text())[0]["role"] == "page"


def test_an_organisation_is_only_proposed_where_two_people_share_a_work_domain():
    """Measured over 180 real days: 182 correspondents, 168 of them on a work domain,
    but 111 of those domains hold exactly one person. A page for each would repeat the
    one-line-person failure at company scale. What earns a page is a domain several
    people write from -- unsw.edu.au alone holds 24 -- because then the same
    institutional facts are otherwise copied onto every one of their pages."""
    from connectonion.wiki.scan import scan_orgs
    people = [
        {"address": "vern.chan@unsw.edu.au", "name": "Vern Chan", "mails": 7, "last": "2026-09-10"},
        {"address": "k.dalapa@unsw.edu.au", "name": "Karen da Lapa-Soares", "mails": 6, "last": "2026-09-12"},
        {"address": "tamara@unsw.edu.au", "name": "Tamara Berryman", "mails": 15, "last": "2026-09-01"},
        {"address": "solo@dataquaranteed.com", "name": "Siraj Deen", "mails": 4, "last": "2026-09-09"},
        {"address": "ody@gmail.com", "name": "Ody", "mails": 30, "last": "2026-09-14"},
        {"address": "someone.else@gmail.com", "name": "Else", "mails": 9, "last": "2026-09-14"},
    ]
    orgs = scan_orgs(people)
    assert [o["domain"] for o in orgs] == ["unsw.edu.au"]          # the only domain two people share
    assert orgs[0]["people"] == 3 and orgs[0]["mails"] == 28
    assert orgs[0]["addresses"][0] == "tamara@unsw.edu.au"          # busiest first
    assert "Vern Chan" in orgs[0]["names"]
    assert orgs[0]["last"] == "2026-09-12"


def test_a_personal_mailbox_is_never_an_organisation():
    """gmail.com is not a company however many people write from it."""
    from connectonion.wiki.scan import scan_orgs
    people = [{"address": f"p{i}@gmail.com", "name": f"P{i}", "mails": 5, "last": "2026-09-10"} for i in range(4)]
    people += [{"address": "a@hotmail.com", "name": "A", "mails": 5, "last": "2026-09-10"},
               {"address": "b@hotmail.com", "name": "B", "mails": 5, "last": "2026-09-10"}]
    assert scan_orgs(people) == []


def test_a_single_person_on_a_work_domain_stays_a_field_unless_asked_for():
    """One person with a work address is a `Company:` field on their own page. The
    threshold can be lowered deliberately, which is how a one-person client that
    signed a contract gets a page."""
    from connectonion.wiki.scan import scan_orgs
    people = [{"address": "solo@dataquaranteed.com", "name": "Siraj", "mails": 4, "last": "2026-09-09"}]
    assert scan_orgs(people) == []
    assert [o["domain"] for o in scan_orgs(people, min_people=1)] == ["dataquaranteed.com"]


def test_a_domain_that_only_sends_notices_is_not_an_organisation_we_deal_with():
    """Run against 180 real days, the first version proposed 53 organisations and the
    top of the list was google.com (29 "people": Google Analytics, Google Play),
    mail.anthropic.com, an event platform's per-event senders, and the user's own
    agent domain. None is a relationship; all are one-way notices. What makes a
    domain an organisation is that people there write *to* the user and are written
    back to, so only those count toward the threshold -- the rest stay visible on the
    row, because a domain can hold both."""
    from connectonion.wiki.scan import scan_orgs
    notices = [{"address": f"noreply+{i}@google.com", "name": "Google Play", "mails": 4, "last": "2026-09-10",
                "automated_hint": True, "one_way": True} for i in range(29)]
    real = [{"address": "vern@unsw.edu.au", "name": "Vern", "mails": 7, "last": "2026-09-10",
             "automated_hint": False, "one_way": False},
            {"address": "karen@unsw.edu.au", "name": "Karen", "mails": 6, "last": "2026-09-12",
             "automated_hint": False, "one_way": False},
            {"address": "no-reply@unsw.edu.au", "name": "UNSW Alerts", "mails": 40, "last": "2026-09-12",
             "automated_hint": True, "one_way": True}]
    orgs = scan_orgs(notices + real)
    assert [o["domain"] for o in orgs] == ["unsw.edu.au"]
    org = orgs[0]
    assert org["people"] == 2          # the two who correspond decide the threshold
    assert org["notices"] == 1         # the alert sender is still reported, not hidden
    assert org["addresses"][0] == "vern@unsw.edu.au"   # ranked among the people, not the notices


def test_the_users_own_domain_is_not_an_organisation_they_deal_with():
    """On the real census `mail.openonion.ai` came third with 18 correspondents: the
    user's own agent addresses. A domain the user sends from is the user."""
    from connectonion.wiki.scan import scan_orgs
    rows = [{"address": f"agent{i}@mail.openonion.ai", "name": f"0x{i}", "mails": 3, "last": "2026-09-10",
             "automated_hint": False, "one_way": False} for i in range(4)]
    rows += [{"address": "vern@unsw.edu.au", "name": "Vern", "mails": 7, "last": "2026-09-10",
              "automated_hint": False, "one_way": False},
             {"address": "karen@unsw.edu.au", "name": "Karen", "mails": 6, "last": "2026-09-12",
              "automated_hint": False, "one_way": True}]
    orgs = scan_orgs(rows, own_addresses={"aaron@mail.openonion.ai", "me@x.y"})
    assert [o["domain"] for o in orgs] == ["unsw.edu.au"]


def test_the_row_carries_how_many_of_them_wrote_back():
    """Neither count decides it alone. Two-way correspondence is the strongest signal
    a domain is a counterparty, but a reply sent from the user's other mailbox leaves
    `sent` at zero, so a real client can look one-way. Both numbers go on the row and
    the Skill judges: brand names all one-way is a vendor, human names are people."""
    from connectonion.wiki.scan import scan_orgs
    rows = [{"address": "tara@cubpbc.com", "name": "Tara Sassine", "mails": 3, "last": "2026-09-10",
             "automated_hint": False, "one_way": True},
            {"address": "gemma@cubpbc.com", "name": "Gemma Ingles", "mails": 2, "last": "2026-09-11",
             "automated_hint": False, "one_way": False}]
    org = scan_orgs(rows)[0]
    assert org["people"] == 2 and org["two_way"] == 1
