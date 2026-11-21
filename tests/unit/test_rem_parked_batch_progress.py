"""One parked page does not throw away a mail batch's scan progress (2026-11-16).

A batch of 40 mails was extracted and maintained page by page; one lead page was
refused twice by its claim audit and parked. Parking discarded the task, a discard
abandoned the batch, and an abandoned batch skipped its progress save without a
word: the next round read the same 40 mails, extracted, maintained and parked again,
five times in one day, and status said the mailbox was "not read since" nine days
ago while the read itself was fine. Fictional people only.
"""

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import native, native_round, refusals, service
from connectonion.rem.config import read_config, set_config
from connectonion.rem.files import Notebook, RemError, read_json, state_path, write_json
from connectonion.rem.source import Batch
from tests.unit.test_rem_unstick import notebook  # noqa: F401

pytestmark = pytest.mark.usefixtures("rem_clock")

WREN = "people/wren-okafor.md"
FIRST, SECOND = "2026-09-20T09:00:00+00:00", "2026-09-29T09:00:00+00:00"


def mail(number, day):
    return {"role": "user", "source": f"outlook:fixture:{number}", "timestamp": f"2026-09-{day}T10:00:00Z",
            "speaker": "wren@example.test", "text": f"Wren Okafor asks to move pilot review {number} to Friday."}


def outlook(root, monkeypatch):
    """A mailbox whose scan hands out two mails from wherever the saved scan point is."""
    write_json(state_path(root, "subscriptions.json"),
               {"outlook": {"kind": "outlook", "enabled": True, "consented": True}})
    set_config(root, ["limits.items_per_batch", "1"])
    Notebook(root).stub_person(WREN, "Wren Okafor", ["wren@example.test"], email="wren@example.test")
    reads = []

    def collect(subscription, progress, max_items, max_chars, client, **kwargs):
        start = 3 if progress.get("scanned_until") == SECOND else 1
        reads.append(start)
        return Batch([mail(start, 18 + start), mail(start + 1, 19 + start)],
                     {"scanned_until": SECOND if start == 1 else "2026-10-01T09:00:00+00:00"})
    monkeypatch.setattr(service, "mail_client", lambda kind, **kwargs: object())
    monkeypatch.setattr(service, "collect_mail", collect)
    return reads


def refuse(root, task, monkeypatch):
    def unsupported(*args):
        raise RemError("Cited-claim audit did not pass: 1 claim is not supported by its source")
    monkeypatch.setattr(native_round, "check_task", unsupported)
    return native.submit(root, task["id"])


def park_the_lead(root, monkeypatch):
    """Extract, then the lead's maintain task refused twice for one reason: parked."""
    extract = native.next_task(root)
    assert extract["stage"] == "extract", extract
    monkeypatch.setattr(native_round, "check_task", lambda *a: {"notes": "Wren Okafor asks to move the pilot review."})
    assert native.submit(root, extract["id"])["outcome"] == "accepted"
    maintain = native.next_task(root)
    assert maintain["stage"] == "maintain" and maintain["record"] == WREN, maintain
    assert refuse(root, maintain, monkeypatch)["outcome"] == "refused"
    parked = refuse(root, maintain, monkeypatch)
    assert parked["outcome"] == "parked", parked
    return maintain


def close_the_batch(root):
    cursor = read_json(state_path(root, "round.json"), {})
    directory = root / "closing"
    directory.mkdir()
    assert native_round.prepare_batch(root, cursor, read_config(root), directory) is None
    write_json(state_path(root, "round.json"), cursor)
    return cursor


def test_a_parked_lead_keeps_the_batchs_scan_progress(notebook, monkeypatch):
    reads = outlook(notebook, monkeypatch)
    park_the_lead(notebook, monkeypatch)
    close_the_batch(notebook)
    progress = read_json(state_path(notebook, "progress.json"), {})
    assert progress["outlook"]["scanned_until"] == SECOND, "the scan point of the whole batch was thrown away"
    assert progress["rem_last_source"] == "outlook"
    assert {"outlook:fixture:1", "outlook:fixture:2"} <= set(progress["rem_seen_source_ids"])
    # The next read starts after the batch: the same mail is not extracted and maintained again.
    following = service.prepare_sync(notebook, service._selected_sources(notebook, ""), progress, read_config(notebook))
    assert reads == [1, 3]
    assert {item["source"] for item in following["items"]} == {"outlook:fixture:3", "outlook:fixture:4"}


def test_the_parked_lead_keeps_what_its_retry_needs(notebook, monkeypatch):
    """The scan point moves on, so the batch is not read again: the page's retry reads what the ledger holds."""
    outlook(notebook, monkeypatch)
    park_the_lead(notebook, monkeypatch)
    entry = refusals.refused_for(notebook, WREN)
    assert entry["parked"].startswith("parked: refused twice for the same reason")
    assert {"outlook:fixture:1", "outlook:fixture:2"} <= set(entry["sources"])
    held = entry["material"]
    assert held and all(item.get("role") != "page" for item in held)
    assert "pilot review" in held[0]["text"]
    # What `_retry_task` is given: material it can prepare a maintain task from, with no mailbox.
    prepared = service_retry(notebook, entry)
    assert prepared["material"] == held and prepared["kind"] == "outlook"


def service_retry(root, entry):
    from connectonion.rem import daily
    return daily.prepare_retry(root, WREN, entry, read_config(root))


def test_a_discarded_extract_still_leaves_the_scan_point_where_it_was(notebook, monkeypatch):
    """Nothing was read into a page: the batch has to be read again, and its run record says so."""
    outlook(notebook, monkeypatch)
    extract = native.next_task(notebook)
    cursor = read_json(state_path(notebook, "round.json"), {})
    task = read_json(state_path(notebook, f"tasks/{extract['id']}/task.json"), {})
    native._discard(notebook, cursor, task, "stale: older than the daily window")
    cursor = close_the_batch(notebook)
    assert "outlook" not in read_json(state_path(notebook, "progress.json"), {})
    run = read_json(state_path(notebook, f"runs/{cursor['run']['id']}.json"), {})
    assert run["batch"]["progress_not_saved"] == "stale: older than the daily window"


def test_status_says_the_progress_was_not_saved_and_why(notebook, monkeypatch):
    outlook(notebook, monkeypatch)
    monkeypatch.setattr(service, "mail_available", lambda kind: True)
    extract = native.next_task(notebook)
    cursor = read_json(state_path(notebook, "round.json"), {})
    task = read_json(state_path(notebook, f"tasks/{extract['id']}/task.json"), {})
    native._discard(notebook, cursor, task, "stale: older than the daily window")
    close_the_batch(notebook)
    state, _ = service.mailbox_state("outlook", service.subscriptions(notebook)["outlook"], root=notebook)
    assert "progress was not saved" in state and "stale: older than the daily window" in state, state
    assert "read again" in state and "not read since" not in state
    status = CliRunner().invoke(app, ["rem", "--root", str(notebook), "status"])
    assert "progress was not saved" in status.output, status.output
