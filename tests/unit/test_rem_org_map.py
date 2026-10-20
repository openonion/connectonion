"""Organisation candidates the map writes, from people pages; no model."""

from connectonion.rem.files import Notebook
from connectonion.rem.org_map import map_orgs


def _record_for(kind, key, name):
    return f"{kind}/{key.replace('.', '-')}.md"


def test_a_domain_whose_only_correspondents_are_automated_or_one_way_gets_no_page(tmp_path):
    """2026-10-20: an events platform got an org page from sign-in codes and registrations alone."""
    notebook = Notebook(tmp_path)
    people = [
        {"address": "codes@eventsdesk.example", "record": "people/events-codes.md", "automated_hint": True},
        {"address": "hosts@eventsdesk.example", "record": "people/events-hosts.md", "one_way": True},
        {"address": "mia.chen@harbour.example", "record": "people/mia-chen.md"},
    ]
    rows, created = map_orgs(notebook, people, "2026-10-20", 180, _record_for)
    assert [row["domain"] for row in rows] == ["harbour.example"]
    assert created == ["orgs/harbour-example.md"]


def test_one_real_correspondent_keeps_the_domain(tmp_path):
    notebook = Notebook(tmp_path)
    people = [
        {"address": "codes@eventsdesk.example", "record": "people/events-codes.md", "automated_hint": True},
        {"address": "theo.park@eventsdesk.example", "record": "people/theo-park.md"},
    ]
    rows, _ = map_orgs(notebook, people, "2026-10-20", 180, _record_for)
    assert [row["domain"] for row in rows] == ["eventsdesk.example"]
    assert rows[0]["people"] == ["people/events-codes.md", "people/theo-park.md"]
