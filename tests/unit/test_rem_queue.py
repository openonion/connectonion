"""The order a category run spends its minutes in (#1656)."""

from datetime import date

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.queue import last_investigated, order


def test_most_mail_first_and_never_the_owner_or_what_may_be_the_owner(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    for record, name in (("people/me.md", "Me"), ("people/corin.md", "Corin"), ("people/briar.md", "Briar"),
                         ("people/second-gmail.md", "second"), ("people/noreply.md", "noreply"),
                         ("people/greta.md", "Greta")):
        notebook.stub_person(record, name, [])
    greta = notebook.read("people/greta.md").replace(
        "Investigation: mapped", "Investigation: investigated 2026-09-22 (outlook) · mapped").replace(
        "- (none yet)", "- [1] outlook:0123456789ab")
    notebook.write("people/greta.md", greta)
    write_json(state_path(tmp_path, "map.json"), {
        "owner": {"record": "people/me.md"},
        "possible_own_addresses": [{"record": "people/second-gmail.md"}],
        "people": [{"record": "people/corin.md", "mails": 185, "classification": "unassessed"},
                   {"record": "people/briar.md", "mails": 40, "classification": "unassessed"},
                   {"record": "people/greta.md", "mails": 90, "classification": "unassessed"},
                   {"record": "people/second-gmail.md", "mails": 106, "classification": "unassessed"},
                   {"record": "people/noreply.md", "mails": 300, "classification": "automated candidate"}]})
    rows = order(tmp_path, "people", today=date(2026, 9, 24))
    assert [row["path"] for row in rows] == ["people/corin.md", "people/briar.md", "people/greta.md"]
    assert rows[-1]["recent"] and rows[-1]["last_investigated"] == "2026-09-22"   # this week's page waits


def test_the_status_line_is_read_for_the_last_investigation_only():
    assert last_investigated("Investigation: mapped 2026-09-01 · not investigated yet") is None
    assert last_investigated("Investigation: investigated 2026-09-10 (gmail) · investigated 2026-09-20 (outlook)") \
        == date(2026, 9, 20)


def test_an_older_maps_row_for_a_company_writing_as_itself_is_never_queued(tmp_path):
    """#2031: the daily round spent 100,080 tokens on people/flagship-minerals, an
    investor-update sender an older map had kept as a person."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/flagship.md", "Flagship Minerals", ["ceo@flagshipminerals.com"])
    notebook.stub_person("people/mia.md", "Mia Tan", ["mia@flagshipminerals.com"])
    write_json(state_path(tmp_path, "map.json"), {"people": [
        {"record": "people/flagship.md", "address": "ceo@flagshipminerals.com", "name": "Flagship Minerals",
         "mails": 1, "sent": 0, "received": 1, "one_way": True, "classification": "unassessed"},
        {"record": "people/mia.md", "address": "mia@flagshipminerals.com", "name": "Mia Tan",
         "mails": 1, "sent": 0, "received": 1, "one_way": True, "classification": "unassessed"}]})
    rows = order(tmp_path, "people", today=date(2026, 9, 24))
    assert [row["path"] for row in rows] == ["people/mia.md"]


def test_a_page_sync_wrote_counts_as_read_from_its_sources():
    """#2046: straight after sync rewrote the connectonion project page, the
    queue ranked it first as "158 sessions, not investigated"."""
    assert last_investigated("Investigation: mapped 2026-09-01 · written 2026-10-01 (own messages: codex)") \
        == date(2026, 10, 1)


def test_an_org_of_unsubscribe_addresses_is_not_queued_and_an_org_counts_only_real_people(tmp_path):
    """#2046: github.com led the 1.9.0a7 orgs queue with "6 people", every one an
    unsub+...@reply.github.com address the people queue already leaves out."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_org("orgs/github.md", "github.com", ["github.com"])
    notebook.stub_org("orgs/google.md", "google.com", ["google.com"])
    unsubs = [f"people/unsub-{n}.md" for n in range(6)]
    for record in unsubs:
        notebook.stub_person(record, "unsub", [])
    notebook.stub_person("people/glen.md", "Glen Ross", [])
    write_json(state_path(tmp_path, "map.json"), {
        "people": [{"record": r, "address": f"unsub+{n}@reply.github.com", "mails": 1, "sent": 1,
                    "classification": "unassessed"} for n, r in enumerate(unsubs)]
                  + [{"record": "people/glen.md", "address": "glenross@google.com", "mails": 2, "sent": 1,
                      "classification": "unassessed"}],
        "orgs": [{"record": "orgs/github.md", "domain": "github.com", "people": unsubs},
                 {"record": "orgs/google.md", "domain": "google.com", "people": ["people/glen.md"]}]})
    rows = order(tmp_path, "orgs", today=date(2026, 10, 1))
    assert [(row["path"], row["weight"]) for row in rows] == [("orgs/google.md", 1)]


def test_the_owners_company_is_queued_even_when_its_contacts_are_excluded(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.write("people/avery.md", "# Avery Lin\n\n- Company: Mara Labs\n")
    for domain in ("maralabs.example", "example.edu.au"):
        notebook.stub_org(f"orgs/{domain}.md", domain, [domain], [])
    write_json(state_path(tmp_path, "map.json"), {
        "owner": {"record": "people/avery.md", "addresses": ["avery@maralabs.example"]},
        "people": [{"record": "people/notices.md", "classification": "automated candidate"}],
        "orgs": [{"record": "orgs/maralabs.example.md", "people": ["people/notices.md"]}],
    })
    assert {row["path"] for row in order(tmp_path, "orgs")} == {
        "orgs/example.edu.au.md", "orgs/maralabs.example.md"}
