"""One page's mailbox failure never ends the night (sprint 14).

From 2026-11-12 every scheduled turn ended with no task: a Graph 404, then a
ReadTimeout listing one mail's attachments, both while preparing one person's
page, left `co rem next` and were tried again 15 minutes later. Fictional
notebooks and mailboxes only.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.provider_credentials import ProviderCredentialError
from connectonion.rem import daily, fetch_stalls, investigate as inv, native, native_round, project_pages, quota, runner, service
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from connectonion.rem.project_material import mark_written

NEW = "2026-10-02T00:00:00Z"


def graph_404():
    # What OutlookMailbox._request raises for a message that was deleted or moved.
    return ProviderCredentialError("provider_unavailable", "Microsoft Graph API error (HTTP 404).",
                                   "co outlook inbox", status=404)


def read_timeout():
    return httpx.ReadTimeout("The read operation timed out")


class Mailbox:
    """A fictional Outlook mailbox: two mails from Ivy, with chosen failures."""

    def __init__(self, *, body_errors=None, attachment_errors=None):
        now = datetime.now(timezone.utc)
        self.rows = [{"id": f"mail-{n}", "from": "ivy@lantern.example", "to": ["me@example.org"],
                      "subject": f"Pilot note {n}", "date": (now - timedelta(days=n)).isoformat()} for n in (1, 2)]
        self.body_errors, self.attachment_errors = body_errors or {}, attachment_errors or {}

    def my_addresses(self):
        return {"me@example.org"}

    def list_between(self, start, end, limit):
        return [row for row in self.rows if start <= row["date"] < end]

    def get_email_body(self, key):
        if key in self.body_errors:
            raise self.body_errors[key]()
        return f"Body of {key}: the pilot starts Monday."

    def list_attachments(self, key):
        if key in self.attachment_errors:
            raise self.attachment_errors[key]()
        return [{"id": "part", "filename": f"{key}.pdf", "mime_type": "application/pdf", "size": 10}]


@pytest.fixture
def no_wait(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)


def gather(tmp_path, mailbox):
    return inv.gather("Ivy", ["ivy@lantern.example"], days=5, clients={"outlook": mailbox}, subscriptions={},
                      record="people/ivy.md", attachments_dir=tmp_path / ".state/attachments")


def test_an_attachment_listing_timeout_is_a_coverage_line_not_the_end_of_the_page(tmp_path, no_wait):
    items, coverage = gather(tmp_path, Mailbox(attachment_errors={"mail-1": read_timeout}))
    bodies = [item for item in items if item["role"] == "other"]
    assert len(bodies) == 2
    assert [item["reference"] for item in items if item["role"] == "attachments-index"] == ["outlook:mail-2"]
    assert "outlook: attachments for 1 message(s) not listed: timed out" in coverage


def test_a_mail_gone_from_the_server_is_skipped_with_a_coverage_line(tmp_path, no_wait):
    items, coverage = gather(tmp_path, Mailbox(body_errors={"mail-2": graph_404}))
    assert [item["subject"] for item in items if item["role"] == "other"] == ["Pilot note 1"]
    assert "outlook: 1 message(s) skipped: not found on the server (deleted or moved)" in coverage
    assert any("1 bodies read" in line for line in coverage), coverage


def test_a_bug_is_not_a_provider_failure_and_still_stops_the_gather(tmp_path, no_wait):
    with pytest.raises(KeyError):
        gather(tmp_path, Mailbox(attachment_errors={"mail-1": lambda: KeyError("bug")}))


@pytest.fixture
def notebook(tmp_path, monkeypatch, rem_clock):
    root = tmp_path / "fixture-notebook"
    prepare(root)
    set_config(root, ["schedule.timezone", "UTC"])
    write_json(state_path(root, "subscriptions.json"), {})
    write_json(state_path(root, "consent.json"), {"authorized_at": service.now().isoformat()})
    monkeypatch.setattr(quota, "read", lambda config: {"unknown": "fixture"})
    monkeypatch.setattr(runner, "run_task", lambda *a, **kw: pytest.fail("No child model"))
    monkeypatch.setattr(runner, "run_claim_task", lambda *a, **kw: pytest.fail("No child audit"))
    monkeypatch.setenv("CO_REM_TURN_ID", "fixture-turn-1")
    return root


def round_of(root, monkeypatch, people, *, error=read_timeout):
    """People pages whose preparation fails on Outlook, then the Heron project page, which needs no mail."""
    book = Notebook(root)
    book.stub_project("projects/heron.md", "Heron")
    mark_written(root, "projects/heron.md", "2026-10-01T00:00:00Z", inputs_read=0, inputs_available=0)
    item = {"role": "user", "source": "codex:heron:1", "timestamp": NEW, "text": "Please review the pilot."}
    monkeypatch.setattr(project_pages, "material", lambda root, record, **kw: ([
        {"role": "page", "record": record, "source": "investigation:page", "text": book.read(record)}, item], NEW))
    monkeypatch.setattr(project_pages, "pending", lambda root, record: ([item], "update"))
    asked = []

    class Outlook:
        def list_between(self, start, end, limit):
            return []  # the round's new-correspondent listing, before any page

        def list_attachments(self, key):
            asked.append(key)
            raise error()

    monkeypatch.setattr(daily, "_clients", lambda sources: {"outlook": Outlook()})
    monkeypatch.setattr(inv, "page_handles", lambda book, record: (Path(record).stem, [f"{Path(record).stem}@x.example"]))

    def investigation(root, record, *args, clients, **kwargs):
        clients["outlook"].list_attachments(record)
        pytest.fail("the fixture mailbox always fails")

    monkeypatch.setattr(inv, "investigate", investigation)
    cursor = native_round.prepare(root, read_config(root), scheduled=False)
    cursor.update(batch={"done": True}, summaries=[], jobs=[
        *({"record": record, "kind": "person"} for record in people), {"record": "projects/heron.md", "kind": "project"}])
    write_json(state_path(root, "round.json"), cursor)
    return asked


def test_a_page_whose_preparation_times_out_is_parked_and_next_serves_the_next_page(notebook, monkeypatch):
    round_of(notebook, monkeypatch, ["people/ivy.md"])
    task = native.next_task(notebook)
    assert task["outcome"] == "task" and task["record"] == "projects/heron.md", task
    entry = read_json(state_path(notebook, fetch_stalls.LEDGER), {})["items"]["people/ivy.md"]
    assert entry["provider"] == "outlook" and entry["reason"] == "timeout" and entry["attempts"] == 1
    assert entry["retry_at"] == (service.now() + timedelta(hours=1)).isoformat()
    assert any("Set people/ivy.md aside: Outlook timed out" in notice for notice in task["notices"])
    # The next round leaves it out until its retry time, then brings back the same job.
    assert "people/ivy.md" in fetch_stalls.waiting(notebook)
    moment = service.now()
    monkeypatch.setattr(service, "now", lambda: moment + timedelta(hours=2))
    assert fetch_stalls.due(notebook) == {"people/ivy.md": {"record": "people/ivy.md", "kind": "person"}}
    monkeypatch.setattr(service, "now", lambda: moment)
    # Failing again waits longer.
    fetch_stalls.park(notebook, {"record": "people/ivy.md", "kind": "person"}, type("Late", (TimeoutError,), {})())
    assert read_json(state_path(notebook, fetch_stalls.LEDGER), {})["items"]["people/ivy.md"]["retry_at"] == (
        service.now() + timedelta(hours=6)).isoformat()


def test_three_pages_failing_on_one_mailbox_stop_it_for_the_turn_and_other_work_goes_on(notebook, monkeypatch):
    people = [f"people/fixture-{n}.md" for n in range(5)]
    asked = round_of(notebook, monkeypatch, people)
    task = native.next_task(notebook)
    assert task["outcome"] == "task" and task["record"] == "projects/heron.md", task
    # Asked for three pages, then not again: the fourth and fifth wait for a later round, unparked.
    assert asked == people[:3]
    ledger = read_json(state_path(notebook, fetch_stalls.LEDGER), {})
    assert sorted(record for record, entry in ledger["items"].items() if not entry.get("held")) == people[:3]
    assert ledger["turn"]["stopped"] == {"outlook": "timeout"}
    assert any("Outlook is not asked again in this turn" in notice for notice in task["notices"])
    # The two never asked come back in the next round as they were; the three parked wait an hour.
    assert sorted(fetch_stalls.due(notebook)) == people[3:]
    assert [job["record"] for job in native_round._with_parked(notebook, [{"record": people[0], "kind": "person"}])] == people[3:]
    # A new turn asks the mailbox again.
    monkeypatch.setenv("CO_REM_TURN_ID", "fixture-turn-2")
    assert fetch_stalls.stopped(notebook) == {}


def test_expired_authorization_stops_the_mailbox_at_the_first_page(notebook, monkeypatch):
    expired = lambda: ProviderCredentialError("reauth_required", "Microsoft authorization expired.", "co auth microsoft")
    asked = round_of(notebook, monkeypatch, ["people/fixture-a.md", "people/fixture-b.md"], error=expired)
    task = native.next_task(notebook)
    assert task["record"] == "projects/heron.md" and asked == ["people/fixture-a.md"]
    assert fetch_stalls.stopped(notebook) == {"outlook": "auth"}


def test_a_single_message_404_never_tells_the_owner_to_open_the_inbox(notebook, monkeypatch):
    round_of(notebook, monkeypatch, ["people/ivy.md"], error=graph_404)
    monkeypatch.setattr(native, "maintenance_lock", _no_lock)
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "next"])
    assert result.exit_code == 0, result.output
    assert "co outlook inbox" not in result.output
    assert "Set people/ivy.md aside: Outlook not found on the server (deleted or moved)" in result.output


def _no_lock(*args, **kwargs):
    from contextlib import nullcontext
    return nullcontext({})


def test_the_night_line_summary_names_the_mailbox_the_reason_and_what_waits(notebook):
    stuck = type("Stuck", (TimeoutError,), {})()
    stuck.rem_provider = "outlook"
    for _ in range(3):
        fetch_stalls.park(notebook, {"record": "people/ivy.md", "kind": "person"}, stuck)
    night = fetch_stalls.last_night(notebook)
    assert night["provider"] == "Outlook" and night["reason"] == "timeout"
    assert night["times"] == 3 and night["pages"] == 1 and not night["stopped"]
    assert [row["record"] for row in night["parked"]] == ["people/ivy.md"]


def test_the_owners_reader_carries_the_stall_and_a_shared_one_does_not(tmp_path, monkeypatch, rem_clock):
    import sys
    from connectonion.rem.reader import snapshot
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
    from rem_reader_notebook import build
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = build(tmp_path / "rem", datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    gone = graph_404()
    gone.rem_provider = "outlook"
    fetch_stalls.park(root, {"record": "people/tomas-reyes.md", "kind": "person"}, gone)
    night = snapshot(root, local=True, today=True)["night_stall"]
    assert night["provider"] == "Outlook" and night["reason"] == "not_found" and night["pages"] == 1
    assert snapshot(root, local=False, today=True)["night_stall"] is None
