"""Granola local records flow through the current REM source boundary."""

import copy
import json
from datetime import datetime, timezone

import pytest
import yaml

from connectonion.rem import service
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError, read_json, state_path
from connectonion.useful_tools.adapter import append_daily_jsonl, make_record


KIND = "granola"


@pytest.fixture
def imported(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "mail_available", lambda _: False)
    monkeypatch.setattr("connectonion.rem.config.local_timezone", lambda: "UTC")
    monkeypatch.setattr("connectonion.rem.config.ZoneInfo", lambda _: timezone.utc)
    monkeypatch.setattr(service, "ZoneInfo", lambda _: timezone.utc)
    monkeypatch.setattr("connectonion.rem.sessions.ZoneInfo", lambda _: timezone.utc)
    # The current upstream SQLite index uses POSIX O_NOFOLLOW.  Its own
    # platform coverage belongs upstream; Granola tests exercise the source
    # boundary and do not depend on rebuilding that index.
    monkeypatch.setattr("connectonion.rem.store.refresh_safely", lambda _: {"fresh": False})
    monkeypatch.setattr("connectonion.rem.people_basics.refresh", lambda _: False)
    root = tmp_path / "rem"
    prepare(root)
    for name in ("codex", "claude-code", "gmail", "outlook", "whatsapp"):
        service.toggle_source(root, name, False)
    now = datetime.now(timezone.utc).isoformat()
    scope = {"folder_id": "folder-1", "limit": 2}
    row = make_record(
        KIND, "test-account", "note-1", "meeting_note", title="Atlas design discussion",
        text="The fictional Atlas project needs a review.", at=now, updated=now,
        fetched=now, url="https://example.invalid/notes/1",
        extensions={"folder_id": "folder-1", "summary_kind": "generated_summary"},
    )
    directory = root / "docs" / KIND
    append_daily_jsonl([row], directory, keep_versions=True)
    (directory / "source.yaml").write_text(yaml.safe_dump({
        "driver": KIND, "account": "test-account", "scope": scope,
        "media_policy": "metadata_only", "complete": True,
    }))
    return root, directory, row


def approve(root):
    service.toggle_source(root, KIND, True)
    service.approve_sources(root)


def test_opt_in_dry_run_never_reads_summary(imported):
    root, directory, _ = imported
    assert not service.subscriptions(root)[KIND]["enabled"]
    service.toggle_source(root, KIND, True)
    next(directory.rglob("*.jsonl")).write_text("broken")
    assert service.run_sync(root, source=KIND, dry_run=True)["sources"][KIND]["body_reads"] is False
    with pytest.raises(RemError, match="authorized"):
        service.run_sync(root, source=KIND)


def test_current_rem_sync_consumes_versioned_local_snapshots(imported):
    root, directory, row = imported
    approve(root)
    calls = []
    result = service.run_sync(root, source=KIND, runner=lambda *args, **kwargs: calls.append(args) or {})
    assert result["items"] == 1 and calls
    assert service.run_sync(root, source=KIND, runner=lambda *args, **kwargs: {})["items"] == 0
    changed = copy.deepcopy(row)
    changed["text"] = "Atlas review is still pending after the revised meeting."
    append_daily_jsonl([changed], directory, keep_versions=True)
    assert service.run_sync(root, source=KIND, runner=lambda *args, **kwargs: {})["items"] == 1


@pytest.mark.parametrize("damage", ["json", "account", "folder", "declaration"])
def test_invalid_local_evidence_is_reported_without_advancing_progress(imported, damage):
    root, directory, row = imported
    approve(root)
    path = next(directory.rglob("*.jsonl"))
    if damage == "json":
        path.write_text("broken")
    elif damage == "declaration":
        document = yaml.safe_load((directory / "source.yaml").read_text())
        document["account"] = "other"
        (directory / "source.yaml").write_text(yaml.safe_dump(document))
    else:
        bad = copy.deepcopy(row)
        if damage == "account":
            bad["account"] = "foreign"
        else:
            bad["extensions"]["folder_id"] = "other"
        path.write_text(json.dumps(bad) + "\n")
    result = service.run_sync(root, source=KIND, runner=lambda *args, **kwargs: pytest.fail("model called"))
    assert result["outcome"] == "failed"
    assert KIND not in read_json(state_path(root, "progress.json"), {})


def test_investigation_reads_selected_local_snapshot_without_remote_polling(imported):
    from connectonion.rem.investigate import gather
    root, _, row = imported
    approve(root)
    Notebook(root).stub_project("projects/atlas.md", "Atlas")
    items, coverage = gather("Atlas", ["atlas"], days=60, clients={},
                             subscriptions=service.subscriptions(root), archive_root=root,
                             record="projects/atlas.md")
    assert len(items) == 1
    assert json.loads(items[0]["text"])["text"] == row["text"]
    assert any("no remote polling" in line for line in coverage)
