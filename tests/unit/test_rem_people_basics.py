"""Archive-backed basics and coverage, using fictional correspondents only."""

import json
import re

import pytest

from connectonion.rem import facts, runner, store
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json

OWNER = "owner@example.test"
ADDRESS = "lena@student.lantern.edu.sg"
RECORD = "people/lena.md"


def archive(root, address=ADDRESS):
    prepare(root)
    book = Notebook(root)
    book.stub_person(RECORD, "Lena Vale", [address], email=address)
    book.stub_org("orgs/lantern.md", "Lantern University", ["lantern.edu.sg"])
    write_json(state_path(root, "map.json"), {
        "owner": {"record": "people/owner.md", "addresses": [OWNER]},
        "orgs": [{"record": "orgs/lantern.md", "domain": "lantern.edu.sg", "people": [RECORD]}],
        "people": [{"record": RECORD, "address": address, "addresses": [address], "sent": 1, "received": 1}]})
    rows = [
        {"source": "gmail", "id": "earliest", "date": "2024-02-01T02:00:00Z", "from": address, "to": [OWNER]},
        {"source": "gmail", "id": "latest", "date": "2026-10-05T02:00:00Z", "from": OWNER, "to": [address]},
    ]
    inventory = state_path(root, "source-inventory.jsonl")
    inventory.write_text("".join(json.dumps({"type": "mail", **row}) + "\n" for row in rows))
    store.refresh(root)
    return book


@pytest.mark.parametrize("first", ["Unknown", "2026-01-01 [7]"])
@pytest.mark.parametrize("native", [False, True])
def test_promotion_recomputes_archive_dates_and_fills_cited_basics(tmp_path, first, native):
    book = archive(tmp_path)
    page = book.read(RECORD).replace("- First contact: Unknown", f"- First contact: {first}")
    page = page.replace("- Location: Unknown", "- Location: Sydney [7]")
    page = page.replace("- Last contact: Unknown", "- Last contact: 2025-01-01 [7]")
    page = page.replace("- (none yet)", "- [7] gmail:location — 2026-01-01")
    receipt = tmp_path / "promotion.json" if native else None
    runner._write_page(book, RECORD, page, [], receipt=receipt)
    parsed = facts.parse(book.read(RECORD), RECORD)
    assert parsed["First contact"][0]["value"] == "2024-02-01"
    assert parsed["Last contact"][0]["value"] == "2026-10-05"
    assert parsed["Time zone"][0]["value"] == "Australia/Sydney"
    assert "Lantern University" in parsed["Company"][0]["value"]
    for label in ("First contact", "Last contact", "Time zone", "Company"):
        assert parsed[label][0]["citations"]
    assert "gmail:earliest" in book.read(RECORD) and "gmail:latest" in book.read(RECORD)
    assert store.person(tmp_path, RECORD)["first_contact"] == "2024-02-01"
    if native:
        import hashlib
        assert json.loads(receipt.read_text())["sha256"] == hashlib.sha256(book.read(RECORD).encode()).hexdigest()


def test_sync_fills_basics_even_without_new_model_work(tmp_path, monkeypatch):
    from connectonion.rem import service
    book = archive(tmp_path)
    service.approve_sources(tmp_path)
    monkeypatch.setattr(service, "_selected_sources", lambda *args: {})
    monkeypatch.setattr("connectonion.rem.sessions.import_sessions", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_resume_archive", lambda *args: None)
    result = service.run_sync(tmp_path, runner=lambda *args, **kwargs: pytest.fail("No model work expected"))
    parsed = facts.parse(book.read(RECORD), RECORD)
    assert parsed["First contact"][0]["value"] == "2024-02-01"
    assert parsed["Time zone"][0]["value"] == "Asia/Singapore"
    assert "Lantern University" in parsed["Company"][0]["value"]
    assert store.person(tmp_path, RECORD)["first_contact"] == "2024-02-01"
    assert result["basics_changed"] == [RECORD]


@pytest.mark.parametrize("address", ["lena@gmail.com", "lena@example.com.au", "no-reply@lantern.edu.sg"])
def test_uncertain_or_automated_domains_do_not_fill_basics(tmp_path, address):
    book = archive(tmp_path, address)
    book.stub_org("orgs/mail-provider.md", "Mail Provider", ["gmail.com"])
    runner._write_page(book, RECORD, book.read(RECORD), [])
    parsed = facts.parse(book.read(RECORD), RECORD)
    assert not parsed["Company"] and not parsed["Time zone"]
    if address.startswith("no-reply@"):
        assert not parsed["First contact"] and not parsed["Last contact"]


@pytest.mark.parametrize("shared", [False, True])
def test_role_address_fills_basics_only_when_not_marked_shared(tmp_path, shared):
    address = "support@lantern.edu.sg"
    book = archive(tmp_path, address)
    page = book.read(RECORD)
    if shared:
        page = page.replace(f"- Email: {address}", f"- Email: {address} (shared)")
    runner._write_page(book, RECORD, page, [])
    parsed = facts.parse(book.read(RECORD), RECORD)
    for label in ("Company", "Time zone", "First contact", "Last contact"):
        assert bool(parsed[label]) is not shared
    if not shared:
        assert "Lantern University" in parsed["Company"][0]["value"]
        assert parsed["Time zone"][0]["value"] == "Asia/Singapore"


def test_populated_company_and_timezone_are_preserved(tmp_path):
    book = archive(tmp_path)
    page = book.read(RECORD).replace("- Company: Unknown", "- Company: Owner's correction [1]")
    page = page.replace("- Time zone: Unknown", "- Time zone: Europe/London [1]")
    runner._write_page(book, RECORD, page, [])
    parsed = facts.parse(book.read(RECORD), RECORD)
    assert parsed["Company"][0]["value"] == "Owner's correction"
    assert parsed["Time zone"][0]["value"] == "Europe/London"
    assert parsed["First contact"][0]["value"] == "2024-02-01"


def test_people_coverage_counts_qualifying_archive_correspondents_without_pages(tmp_path):
    from connectonion.cli.commands import rem_status
    from connectonion.rem.reader import snapshot
    from connectonion.rem.service import status
    book = archive(tmp_path)
    book.write(RECORD, book.read(RECORD).replace("not investigated yet", "investigated 2026-10-06"))
    inventory = state_path(tmp_path, "source-inventory.jsonl")
    rows = [
        {"from": OWNER, "to": ["niko@example.test"]},
        {"from": "niko@example.test", "to": [OWNER]},
        {"from": "newsletter@example.test", "to": [OWNER]},
        {"from": OWNER, "to": ["once@example.test"]},
    ]
    with inventory.open("a") as handle:
        for n, row in enumerate(rows):
            handle.write(json.dumps({"type": "mail", "source": "gmail", "id": f"extra{n}",
                                     "date": "2026-10-06T02:00:00Z", **row}) + "\n")
    store.refresh(tmp_path)
    data = snapshot(tmp_path)
    assert data["people_coverage"] == {"total": 2, "covered": 1, "missing": 1}
    assert status(tmp_path)["people_coverage"] == data["people_coverage"]
    shown = rem_status.dashboard(tmp_path, status(tmp_path), lambda args: "co rem " + " ".join(args))
    from rich.text import Text
    plain = Text.from_markup(shown).plain
    assert "50%" in next(line for line in plain.splitlines() if "People" in line)
    assert "1 people you write to have no page yet" in plain


def test_archive_coverage_uses_the_maps_recipient_and_alias_rules(tmp_path):
    from connectonion.rem.census import people_coverage
    book = archive(tmp_path)
    alias = "lena@personal.test"
    book.write(RECORD, book.read(RECORD).replace(f"- Email: {ADDRESS}", f"- Email: {ADDRESS}; {alias}"))
    with state_path(tmp_path, "source-inventory.jsonl").open("a") as handle:
        for n in range(2):
            handle.write(json.dumps({"type": "mail", "source": "gmail", "id": f"copy{n}",
                                     "date": "2026-10-06T00:00:00Z", "from": OWNER,
                                     "to": [alias], "cc": ["copied@example.test"]}) + "\n")
    # One person with two addresses, one qualifying copied recipient still without a page.
    assert people_coverage(tmp_path) == {"total": 2, "covered": 1, "missing": 1}


def test_company_cites_mail_from_the_matching_domain(tmp_path):
    from connectonion.rem import people_basics
    book = archive(tmp_path)
    newer = "lena@other-company.test"
    page = book.read(RECORD).replace(f"- Email: {ADDRESS}", f"- Email: {ADDRESS}; {newer}")
    book.write(RECORD, page)
    with state_path(tmp_path, "source-inventory.jsonl").open("a") as handle:
        handle.write(json.dumps({"type": "mail", "source": "gmail", "id": "new-company",
                                 "from": newer, "to": [OWNER], "date": "2026-11-01T00:00:00Z"}) + "\n")
    people_basics.refresh(tmp_path)
    text = book.read(RECORD)
    company = facts.parse(text, RECORD)["Company"][0]
    sources = dict(re.findall(r"^- \[(\d+)\] (\S+)", text.partition("\n## Sources\n")[2], re.M))
    assert "Lantern University" in company["value"]
    assert sources[company["citations"][0]] != "gmail:new-company"


@pytest.mark.parametrize("email", [f"{ADDRESS} (shared)", ADDRESS])
def test_shared_addresses_and_narrative_mentions_are_not_personal_evidence(tmp_path, email):
    from connectonion.rem import people_basics
    book = archive(tmp_path)
    book.stub_person("people/other.md", "Rowan Finch", [ADDRESS], email=email)
    book.write(RECORD, book.read(RECORD) + "\nAn unrelated person uses support@lantern.edu.sg.\n")
    people_basics.refresh(tmp_path)
    parsed = facts.parse(book.read(RECORD), RECORD)
    assert not parsed["First contact"] and not parsed["Company"] and not parsed["Time zone"]


def test_native_sync_preparation_fills_basics_before_tasks_are_hashed(tmp_path, monkeypatch):
    from connectonion.rem import native_round, service
    from connectonion.rem.config import read_config
    book = archive(tmp_path)
    service.approve_sources(tmp_path)
    monkeypatch.setattr(service, "_selected_sources", lambda *args: {})
    monkeypatch.setattr("connectonion.rem.sessions.import_sessions", lambda *args, **kwargs: {})
    monkeypatch.setattr("connectonion.rem.project_material.extract", lambda *args, **kwargs: {})
    monkeypatch.setattr(native_round, "_jobs", lambda *args: [])
    cursor = native_round.prepare(tmp_path, read_config(tmp_path), scheduled=False)
    assert facts.parse(book.read(RECORD), RECORD)["First contact"][0]["value"] == "2024-02-01"
    assert RECORD in cursor["changed"]


def test_merge_promotion_recomputes_basics_before_native_commit_hashes(tmp_path):
    from connectonion.rem import merge
    book = archive(tmp_path)
    other = "people/lena-alias.md"
    book.stub_person(other, "Lena Vale", [ADDRESS], email=ADDRESS)
    plan = merge.prepare_merge(book, RECORD, other, "Their own address")
    parsed = facts.parse(plan["page"], RECORD)
    assert parsed["First contact"][0]["value"] == "2024-02-01"
    assert parsed["Last contact"][0]["value"] == "2026-10-05"
    assert "Lantern University" in parsed["Company"][0]["value"]
    merge.promote_merge(book, plan)
    assert store.person(tmp_path, RECORD)["first_contact"] == "2024-02-01"


def test_reader_does_not_label_an_explicit_contact_date_as_map_metadata():
    from connectonion.rem.reader import TEMPLATE
    from tests.unit.test_rem_reader import _run_reader_js
    script = re.search(r"function mappedContact\(r\) \{[^\n]*\}", TEMPLATE.read_text())[0]
    script += '''
      const REM = {owner: "people/owner.md"};
      const known = r => ({status: "Mapped"});
      const parseFacts = r => new Map(r.explicit ? [["Last contact", [{value: "2026-10-05"}]]] : []);
      const r = {path: "people/lena.md", category: "people", last_activity: "2026-10-05"};
      console.log(JSON.stringify([mappedContact(r), mappedContact({...r, explicit: true})]));
    '''
    assert _run_reader_js(script) == [True, False]
