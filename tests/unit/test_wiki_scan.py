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
