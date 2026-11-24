"""The Codex week's floor holds investigation, never mail (11-09).

The owner's round had a page open (investigation part 2, job 7 of 8) when the
week reached its 90% floor. Each later turn stopped at the floor; the slot's mail
read waits for the open page to close, and the floor kept it open: 26 turns, no
mail, Gmail unread for two days, status saying only "last turn completed".
Fictional notebooks only.
"""

from datetime import timedelta

import pytest

from connectonion.rem import native, native_round, quota, service
from connectonion.rem.config import read_config
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from tests.unit.test_rem_unstick import notebook  # noqa: F401

pytestmark = pytest.mark.usefixtures("rem_clock")

MAIL = [{"role": "user", "source": "gmail:fixture:1", "timestamp": "2026-09-07T10:00:00Z",
         "speaker": "wren@example.test", "text": "Can we move the pilot review to Friday?"}]


def at_floor(monkeypatch):
    week = {"used_percent": 90, "window_minutes": 10080, "plan": "pro",
            "resets_at": int((service.now() + timedelta(days=2)).timestamp())}
    monkeypatch.setattr(quota, "read", lambda config, request=None: week)


def mailbox(monkeypatch, reads):
    def fetch(root, selected, progress, config, *args, **kwargs):
        reads.append(sorted(selected))
        return {"done": False, "items": MAIL, "updated": {**progress, "gmail": {"scanned_until": "x"}},
                "record": {"extracted": False, "id": "run_" + "b" * 32}, "kind": "gmail", "leads": [None],
                "digested": None}
    monkeypatch.setattr(service, "prepare_sync", fetch)


def held_round(root, *, record="people/fixture-6.md"):
    """The owner's round.json shape: batch done, job 7 of 8, part 2 of an investigation open."""
    config = read_config(root)
    slot = service.latest_slot(config, service.now() + service.EARLY_FIRE)
    Notebook(root).stub_person(record, "Fixture Six", ["six@example.test"], email="six@example.test")
    cursor = native_round.prepare(root, config, scheduled=False)
    cursor.update(batch={"done": True}, batch_index=0, summaries=[], job_index=6, investigation_left=5,
                  jobs=[{"record": f"people/fixture-{n}.md", "kind": "person"} for n in range(8)],
                  slot=(slot - timedelta(days=1)).isoformat(), mail_slot=(slot - timedelta(hours=13)).isoformat(),
                  pending=None, project_quote=None,
                  current={"record": record, "number": 2, "parts": [[]], "inquiry": "plan",
                           "before": Notebook(root).read(record), "draft": Notebook(root).read(record)})
    write_json(state_path(root, "round.json"), cursor)
    return slot


def test_a_round_held_at_the_floor_with_a_page_open_reads_the_new_slots_mail(notebook, monkeypatch):
    at_floor(monkeypatch)
    slot = held_round(notebook)
    reads = []
    mailbox(monkeypatch, reads)
    result = native.next_task(notebook, scheduled=True)
    assert reads, "the floor kept the slot's mail unread"
    assert result["outcome"] == "task" and result["stage"] == "maintain", result
    assert read_json(state_path(notebook, "round.json"), {})["mail_slot"] == slot.isoformat()


def test_a_slots_mail_read_reads_the_mailboxes_not_the_coding_sessions(notebook, monkeypatch):
    """11-09: both slot reads that got through took codex and claude-code; Gmail waited."""
    at_floor(monkeypatch)
    held_round(notebook)
    reads = []
    mailbox(monkeypatch, reads)
    monkeypatch.setattr(service, "_selected_sources", lambda root, selector: {
        "codex": {"kind": "codex"}, "claude-code": {"kind": "claude-code"},
        "gmail": {"kind": "gmail"}, "outlook": {"kind": "outlook"}})
    native.next_task(notebook, scheduled=True)
    assert reads == [["gmail", "outlook"]]


def test_the_floor_still_holds_the_investigation_after_the_mail(notebook, monkeypatch):
    at_floor(monkeypatch)
    held_round(notebook)
    cursor = read_json(state_path(notebook, "round.json"), {})
    cursor["mail_slot"] = cursor["slot"] = service.latest_slot(read_config(notebook), service.now()).isoformat()
    write_json(state_path(notebook, "round.json"), cursor)
    monkeypatch.setattr(native_round, "_prepare_job", lambda *a: pytest.fail("investigation under the floor"))
    result = native.next_task(notebook, scheduled=True)
    assert result["outcome"] == "done" and "floor" in result["reason"]


def test_an_open_page_changed_by_mail_starts_its_investigation_again(notebook, monkeypatch):
    """Mail read under the floor may edit the open page; resuming must not refuse every turn after."""
    held_round(notebook)
    book = Notebook(notebook)
    book.path("people/fixture-6.md").write_text(book.read("people/fixture-6.md") + "\n- Moved the review to Friday.\n")
    cursor = read_json(state_path(notebook, "round.json"), {})
    fresh = {"record": "people/fixture-6.md", "number": 1, "page": {"role": "page"}}
    monkeypatch.setattr(native_round, "_prepare_investigation", lambda root, cursor, job, directory: fresh)
    monkeypatch.setattr(native_round.investigate, "prepare_round", lambda book, state, page: None)
    monkeypatch.setattr(native_round, "_followup_items", lambda book, state: None)
    monkeypatch.setattr(native_round, "_finish_investigation", lambda root, cursor: None)
    native_round._prepare_job(notebook, cursor, read_config(notebook), notebook)
    assert fresh.get("before") == book.read("people/fixture-6.md")


def test_status_says_the_round_is_held_by_the_floor_and_when_it_resets(notebook, monkeypatch):
    at_floor(monkeypatch)
    held_round(notebook)
    cursor = read_json(state_path(notebook, "round.json"), {})
    cursor["mail_slot"] = cursor["slot"] = service.latest_slot(read_config(notebook), service.now()).isoformat()
    write_json(state_path(notebook, "round.json"), cursor)
    write_json(state_path(notebook, "last-turn.json"), {"result": "completed", "started_at": service.now().isoformat()})
    native.next_task(notebook, scheduled=True)
    found = service.round_state(notebook, read_config(notebook))
    assert found["state"] == "stuck" and "90% floor" in found["reason"], found
    assert "resets" in found["reason"], found
