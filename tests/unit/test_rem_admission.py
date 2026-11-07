"""Continuous admission and early identity checks, using fictional mail only."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from connectonion.rem import daily, native_round, people_pages, same_person, service
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, maintenance_lock, read_json, state_path, write_json
from connectonion.rem.mail import collect_mail

OWNER = "owner@example.org"


class Mail:
    def __init__(self, rows):
        self.rows = rows
        self.read = []

    def my_addresses(self):
        return [OWNER]

    def list_between(self, start, end, limit):
        return [row for row in self.rows if start <= row["date"] < end]

    def get_email_body(self, identity):
        self.read.append(identity)
        return "--- Email Body ---\nCould we discuss the prototype?"


def message(identity, sender, recipient, moment):
    return {"id": identity, "from": sender, "to": [recipient], "cc": [],
            "date": moment.isoformat(), "subject": "Prototype"}


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.timezone", "UTC"])
    monkeypatch.setattr(daily.quota, "read", lambda config: {"unknown": "fixture"})
    monkeypatch.setattr(daily, "subscriptions", lambda root: {})
    monkeypatch.setattr(daily, "_owner_due", lambda root: [])
    write_json(state_path(tmp_path, "map.json"), {
        "owner": {"record": "people/owner.md", "addresses": [OWNER]}, "people": [], "without_page": [], "projects": [], "orgs": []})
    return tmp_path


@pytest.mark.parametrize("path", ["native", "daily"])
@pytest.mark.parametrize("first", [True, False])
def test_new_correspondents_are_admitted_and_queued_within_one_round(notebook, monkeypatch, path, first):
    moment = service.now() - timedelta(hours=2)
    client = Mail([
        message("out", OWNER, "Nora Vale <nora@work.example>", moment),
        message("in", "Nora Vale <nora@work.example>", OWNER, moment + timedelta(minutes=1)),
        *[message(f"founder{i}", "Lena Frost <hello@cedar.example>", OWNER, moment + timedelta(minutes=i))
          for i in range(3)],
        *[message(f"robot{i}", "No Reply <no-reply@robot.example>", OWNER, moment + timedelta(minutes=i))
          for i in range(4)],
    ])
    monkeypatch.setattr(daily, "_clients", lambda sources: {"gmail": client})
    logs = [] if first else [{"phase": "daily-investigation", "started_at": (moment - timedelta(hours=1)).isoformat()}]
    for index, row in enumerate(logs):
        write_json(state_path(notebook, f"runs/run_prior{index}.json"), {"id": f"run_prior{index}", **row})
    if path == "native":
        with maintenance_lock(notebook):
            jobs = native_round._jobs(notebook, first, logs, {})
        queued = [row["record"] for row in jobs if row["kind"] == "person"]
    else:
        queued = []
        daily.run_daily(notebook, maintain=lambda root: {"outcome": "no_change"},
                        person_one=lambda root, row, **kw: queued.append(row["record"]) or {})
    rows = read_json(state_path(notebook, "map.json"), {})["people"]
    assert {address for row in rows for address in row["addresses"]} == {"nora@work.example", "hello@cedar.example"}
    assert queued[:2] == [next(row["record"] for row in rows if "nora@work.example" in row["addresses"]),
                          next(row["record"] for row in rows if "hello@cedar.example" in row["addresses"])]
    assert all("not investigated yet" in Notebook(notebook).read(row["record"]) for row in rows)
    assert all(len(row["first"]) == len(row["last"]) == 10 for row in rows)


def test_admission_counts_across_rounds_without_counting_overlap_twice(notebook):
    moment = service.now() - timedelta(hours=2)
    client = Mail([message("one", "Nora Vale <nora@work.example>", OWNER, moment)])
    people_pages.correspondents_since(notebook, {"gmail": client}, since=moment - timedelta(hours=1), now=moment + timedelta(minutes=1))
    people_pages.correspondents_since(notebook, {"gmail": client}, since=moment, now=moment + timedelta(minutes=2))
    assert Notebook(notebook).list("people") == []
    client.rows += [message("two", "Nora Vale <nora@work.example>", OWNER, moment + timedelta(minutes=3)),
                    message("three", "Nora Vale <nora@work.example>", OWNER, moment + timedelta(minutes=4))]
    found = people_pages.correspondents_since(notebook, {"gmail": client}, since=moment, now=moment + timedelta(minutes=5))
    [row] = read_json(state_path(notebook, "map.json"), {})["people"]
    assert row["received"] == row["mails"] == 3 and row["record"] in found["records"]
    people_pages.correspondents_since(notebook, {"gmail": client}, since=moment, now=moment + timedelta(minutes=6))
    assert len(read_json(state_path(notebook, "map.json"), {})["people"]) == 1


def test_mail_from_a_merged_alias_updates_the_kept_page(notebook):
    book = Notebook(notebook)
    book.stub_person("people/nora.md", "Nora Vale", email="nora@work.example")
    book.write("people/nora.md", book.read("people/nora.md").replace("not investigated yet", "investigated 2026-01-01")
               .replace("- (none yet)", "- [1] gmail:0123456789ab"))
    write_json(state_path(notebook, "aliases.json"), {"people/old.md": {"into": "people/nora.md"}})
    write_json(state_path(notebook, "map.json"), {"owner": {"record": "people/owner.md", "addresses": [OWNER]}, "people": [
        {"record": "people/old.md", "addresses": ["nora@home.example"], "sent": 1, "received": 1}]})
    moment = service.now() - timedelta(minutes=1)
    found = people_pages.correspondents_since(notebook, {"gmail": Mail([
        message("alias", "Nora Vale <nora@home.example>", OWNER, moment)])}, since=moment - timedelta(hours=1))
    assert found["records"] == ["people/nora.md"]
    [row] = people_pages.queue(notebook)
    assert row["record"] == "people/nora.md" and row["mode"] == "update"
    assert book.list("people") == ["people/nora.md"]


@pytest.mark.parametrize("local", ["hello", "info", "team", "support", "updates"])
def test_role_address_mail_is_read_but_no_reply_is_excluded(local):
    moment = service.now() - timedelta(minutes=1)
    client = Mail([message("founder", f"Lena Frost <{local}@cedar.example>", OWNER, moment),
                   message("robot", "no-reply@robot.example", OWNER, moment)])
    batch = collect_mail({"kind": "gmail", "enabled": True, "consented": True,
                          "since": (moment - timedelta(hours=1)).isoformat()}, {}, 10, 20000, client)
    assert client.read == ["founder"] and len(batch.items) == 1


@pytest.mark.parametrize("role", ["agent mailbox", "shared", "assistant or delegate", "shared or family mailbox", "team or role inbox", "none shared", "unclear"])
def test_same_verdict_requires_the_persons_own_address(notebook, role):
    book = Notebook(notebook)
    book.stub_person("people/nora.md", "Nora", email="nora@home.example")
    book.stub_person("people/nora-vale.md", "Nora Vale", email="nora@work.example")
    [pair] = same_person.candidates(notebook)
    result = same_person.check({"root": str(notebook), "pair": pair}, {
        "result": json.dumps({"same": True, "address_role": role, "reason": "Writes on their behalf."})})
    assert result["same"] is False and "kept" not in result
    assert len(book.list("people")) == 2
    assert not read_json(state_path(notebook, "aliases.json"), {})


def _pairs(root, count):
    book = Notebook(root)
    for index in range(count):
        for suffix, name in [("short", f"Nora{index}"), ("full", f"Nora{index} Vale")]:
            book.stub_person(f"people/nora{index}-{suffix}.md", name, email=f"{suffix}{index}@work.example")


def test_native_judges_uninvestigated_pairs_before_jobs_with_cap_ten(notebook, monkeypatch):
    _pairs(notebook, 11)
    cursor = {"batch": {"done": True}, "summaries": [{"record": "projects/session.md", "key": "session"}],
              "phase": "daily-investigation",
              "jobs": [{"record": "people/nora0-full.md", "kind": "person"}], "job_index": 0,
              "current": None, "same_left": 3, "same_new_left": 10, "changed": []}
    monkeypatch.setattr(same_person, "prepare", lambda root, pair, directory: {"root": str(root), "pair": pair})
    monkeypatch.setattr(native_round, "_prepare_job", lambda *args: {"handler": "investigation"})
    for index in range(10):
        task = native_round.prepare_task(notebook, cursor, read_config(notebook), notebook)
        assert task["handler"] == "same-person", index
        result = same_person.check(task["task"], {"result": json.dumps({
            "same": False, "address_role": "unclear", "reason": "Different people."})})
        native_round.advance(notebook, cursor, task, result)
    assert native_round.prepare_task(notebook, cursor, read_config(notebook), notebook)["handler"] == "investigation"


def test_daily_judges_uninvestigated_pairs_before_jobs_with_cap_ten(notebook, monkeypatch):
    from connectonion.rem import runner
    _pairs(notebook, 11)
    events = []
    monkeypatch.setattr(daily, "_clients", lambda sources: {})

    def run(*args, **kwargs):
        events.append("judge")
        return {"result": json.dumps({"same": False, "address_role": "unclear", "reason": "Different people."})}

    monkeypatch.setattr(runner, "run_claim_task", run)
    daily.run_daily(notebook, maintain=lambda root: {"outcome": "no_change"},
                    person_one=lambda *args, **kwargs: events.append("investigate") or {})
    assert events[:11] == ["judge"] * 10 + ["investigate"]
    assert events.count("judge") == 10


@pytest.mark.parametrize("both_queued", [False, True])
def test_native_early_merge_queues_the_kept_page_once(notebook, both_queued):
    book = Notebook(notebook)
    book.stub_person("people/nora.md", "Nora", email="nora@home.example")
    book.stub_person("people/nora-vale.md", "Nora Vale", email="nora@work.example")
    book.write("people/nora-vale.md", book.read("people/nora-vale.md").replace(
        "not investigated yet", "investigated 2026-01-01").replace(
        "## Insight\n", "## Insight\n- Builds experimental sensors.\n"))
    [pair] = same_person.candidates(notebook)
    result = same_person.check({"root": str(notebook), "pair": pair}, {"result": json.dumps({
        "same": True, "address_role": "their own", "reason": "Both are her own addresses."})})
    cursor = {"jobs": [{"record": "people/nora.md", "kind": "person", "days": 730}],
              "job_index": 0, "changed": [], "same_new_left": 10}
    if both_queued:
        cursor["jobs"].append({"record": "people/nora-vale.md", "kind": "person", "days": 30})
    native_round.advance(notebook, cursor, {"operation": "same-person", "early_pair": True}, result)
    assert [job["record"] for job in cursor["jobs"]] == ["people/nora-vale.md"]
    assert cursor["jobs"][0]["days"] == 730


def test_admission_keeps_suspected_owner_addresses_held(notebook):
    state = read_json(state_path(notebook, "map.json"), {})
    state["possible_own_addresses"] = [{"address": "riley.finch@home.example", "record": None}]
    write_json(state_path(notebook, "map.json"), state)
    moment = service.now() - timedelta(hours=1)
    client = Mail([message(str(i), OWNER, "Riley Finch <riley.finch@home.example>", moment + timedelta(minutes=i))
                   for i in range(2)])
    people_pages.correspondents_since(notebook, {"gmail": client}, since=moment - timedelta(minutes=1))
    assert Notebook(notebook).list("people") == []
    assert read_json(state_path(notebook, "map.json"), {})["people"] == []


def test_admission_reuses_historical_role_address_counts(notebook):
    moment = service.now() - timedelta(hours=1)
    state = read_json(state_path(notebook, "map.json"), {})
    state["automated_correspondents"] = [{"address": "hello@cedar.example", "name": "Lena Frost",
        "sent": 0, "received": 3, "mails": 3, "one_way": True}]
    write_json(state_path(notebook, "map.json"), state)
    found = people_pages.correspondents_since(notebook, {"gmail": Mail([
        message("new", "Lena Frost <hello@cedar.example>", OWNER, moment)])}, since=moment - timedelta(minutes=1))
    [row] = read_json(state_path(notebook, "map.json"), {})["people"]
    assert row["received"] == 4 and row["record"] in found["records"]
    assert [entry["record"] for entry in people_pages.queue(notebook)] == [row["record"]]


def test_daily_early_merge_updates_the_kept_page_from_new_alias_mail(notebook, monkeypatch):
    from connectonion.rem import runner
    moment = service.now() - timedelta(hours=1)
    book = Notebook(notebook)
    book.stub_person("people/nora.md", "Nora", email="nora@home.example")
    book.stub_person("people/nora-vale.md", "Nora Vale", email="nora@work.example")
    book.write("people/nora-vale.md", book.read("people/nora-vale.md").replace(
        "not investigated yet", "investigated " + (moment - timedelta(days=2)).date().isoformat()).replace(
        "- (none yet)", "- [1] gmail:0123456789ab"))
    state = read_json(state_path(notebook, "map.json"), {})
    state["people"] = [{"record": "people/nora.md", "addresses": ["nora@home.example"], "sent": 1, "received": 1},
                       {"record": "people/nora-vale.md", "addresses": ["nora@work.example"], "sent": 1, "received": 1}]
    write_json(state_path(notebook, "map.json"), state)
    write_json(state_path(notebook, "runs/run_prior.json"), {"id": "run_prior", "phase": "daily-investigation",
        "started_at": (moment - timedelta(hours=1)).isoformat()})
    monkeypatch.setattr(daily, "_clients", lambda sources: {"gmail": Mail([
        message("alias", "Nora <nora@home.example>", OWNER, moment)])})
    monkeypatch.setattr(runner, "run_claim_task", lambda *args, **kwargs: {"result": json.dumps({
        "same": True, "address_role": "their own", "reason": "Both her own addresses."})})
    investigated = []
    daily.run_daily(notebook, maintain=lambda root: {"outcome": "no_change"},
                    person_one=lambda root, row, **kwargs: investigated.append(row["record"]) or {})
    assert investigated == ["people/nora-vale.md"]
