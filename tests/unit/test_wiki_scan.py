"""The census: what the sources already list, handed over as signals."""

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
