"""Copied and divergent Codex rollouts, using invented Atlas messages only."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from connectonion.rem import capture, project_material, source, store, tidy
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError, state_path, write_json
from tests.unit.test_rem_source import rollout, subscription

NOW = datetime(2026, 9, 7, 6, tzinfo=timezone.utc)
SESSION = "00000000-0000-4000-8000-000000000001"
OLD = "Keep the old login flow."
NEW = "Replace the old login flow with OAuth."
RECORD = "projects/atlas.md"


@pytest.fixture
def atlas(tmp_path):
    root, transcripts = tmp_path / "notebook", tmp_path / "transcripts"
    prepare(root)
    Notebook(root).stub_project(RECORD, "Atlas", ["/work/atlas"])
    sub = subscription(transcripts, kind="codex")
    return root, transcripts, sub


def write_rollout(transcripts, name, text):
    path = transcripts / f"rollout-{name}-{SESSION}.jsonl"
    rollout(path, [("user", text)], project="/work/atlas", session=SESSION)
    return path


def extract(atlas):
    root, _, sub = atlas
    return project_material.extract(root, {"codex": sub}, now=NOW, create_pages=False)


def test_divergent_rollouts_collect_merge_and_retain_both(atlas):
    root, transcripts, sub = atlas
    first = write_rollout(transcripts, "original", OLD)
    assert extract(atlas)["pages"][0]["added"] == 1
    second = write_rollout(transcripts, "resumed", NEW)
    assert first.read_bytes().splitlines()[0] == second.read_bytes().splitlines()[0]
    batch = source.collect(sub, {}, 20, 10000)
    by_text = {item["text"]: item["source"] for item in batch.items}
    assert len(set(by_text.values())) == 2
    offset = len(first.read_bytes().splitlines(keepends=True)[0])
    for text, identity in by_text.items():
        assert identity == f"codex:{SESSION}:{offset}-" + hashlib.sha256(text.encode()).hexdigest()[:8]
    report = extract(atlas)
    assert report["pages"][0]["added"] == 1
    assert report["conflicts"] == []
    assert {m["source"] for m in project_material.stored(root, RECORD)} == set(by_text.values())
    assert project_material.page_state(root, RECORD)["sessions"] == 1
    project_material.retain_cited_sessions(root, batch.items, set(by_text.values()))
    for text, identity in by_text.items():
        assert project_material.retained_session_context(root, identity)["excerpt"] == text
    assert {row["body"] for row in store.thread(root, f"session:codex:{SESSION}", bodies=True)} == {OLD, NEW}


def test_identical_copied_prefix_deduplicates(atlas):
    root, transcripts, sub = atlas
    write_rollout(transcripts, "original", OLD)
    write_rollout(transcripts, "copy", OLD)
    items = source.collect(sub, {}, 20, 10000).items
    assert len(items) == 2 and items[0]["source"] == items[1]["source"]
    assert extract(atlas)["pages"][0]["added"] == 1
    assert len(project_material.stored(root, RECORD)) == 1
    assert extract(atlas)["pages"][0]["added"] == 0


def test_legacy_citation_and_stored_message_stay_valid(atlas, monkeypatch):
    root, transcripts, sub = atlas
    path = write_rollout(transcripts, "original", OLD)
    item, = source.collect(sub, {}, 20, 10000).items
    legacy = item["source"].rsplit("-", 1)[0]
    project_material.retain_cited_sessions(root, [{**item, "source": legacy}], {legacy})
    Notebook(root).write(RECORD, f"# Atlas\n\nKeep the login flow. [1]\n\n## Sources\n- [1] {legacy}\n")
    assert project_material.retained_session_context(root, legacy)["excerpt"] == OLD
    monkeypatch.setattr("connectonion.rem.service.subscriptions", lambda _: {"codex": sub})
    assert tidy._typed(tidy._session_files(root), legacy)
    assert tidy._not_typed(Notebook(root)) == []
    assert legacy in Notebook(root).read(RECORD)
    message = {**item, "source": legacy, "tool": "codex", "cwd": "/work/atlas"}
    project_material._merge(root, RECORD, [message], full=False, now=NOW)
    result = project_material._merge(root, RECORD, [{**message, "source": item["source"]}], full=False, now=NOW)
    assert result["added"] == 0 and result["conflicts"] == []
    assert project_material.stored(root, RECORD)[0]["source"] == legacy
    different = {**message, "source": source.session_source("codex", SESSION,
                  source.parse_session_source(legacy)[2], NEW), "text": NEW}
    assert project_material._merge(root, RECORD, [different], full=False, now=NOW)["added"] == 1


@pytest.mark.parametrize("same_batch", [False, True])
def test_merge_reports_same_id_with_different_text(atlas, same_batch):
    root, transcripts, sub = atlas
    write_rollout(transcripts, "original", OLD)
    item, = source.collect(sub, {}, 20, 10000).items
    message = {**item, "tool": "codex", "cwd": "/work/atlas"}
    changed = {**message, "text": NEW}
    if not same_batch:
        project_material._merge(root, RECORD, [message], full=False, now=NOW)
    result = project_material._merge(root, RECORD, [message, changed] if same_batch else [changed],
                                     full=False, now=NOW)
    assert result["conflicts"] == [message["source"]]
    assert result["added"] == int(same_batch)
    assert [m["text"] for m in project_material.stored(root, RECORD)] == [OLD]
    with pytest.raises(RemError, match="conflicting content"):
        project_material.retain_cited_sessions(root, [item, {**item, "text": NEW}], {item["source"]})


def test_extraction_and_cli_report_conflicts(atlas, monkeypatch, capsys):
    from connectonion.cli.commands.rem_projects import _refresh
    root, transcripts, sub = atlas
    write_rollout(transcripts, "original", OLD)
    extract(atlas)
    message, = project_material.stored(root, RECORD)
    monkeypatch.setattr(project_material, "session_messages", lambda *args, **kwargs:
        ([{**message, "text": NEW}], {"files": 1, "harness": 0, "unfamiliar": 0, "excluded": {}, "attributed": 0}))
    monkeypatch.setattr("connectonion.rem.service.subscriptions", lambda _: {"codex": sub})
    report = _refresh(root, False, 14)
    assert report["conflicts"] == [message["source"]]
    assert "conflicting content; kept stored messages: " + message["source"] in capsys.readouterr().err


def test_hash_precedes_redaction_and_fit(atlas):
    root, transcripts, sub = atlas
    text = "Keep the login flow. " + "x" * 3000 + " sk-" + "A" * 48
    path = write_rollout(transcripts, "original", text)
    offset = len(path.read_bytes().splitlines(keepends=True)[0])
    expected = source.session_source("codex", SESSION, offset, text)
    item, = source.collect(sub, {}, 20, 1000).items
    assert item["source"] == expected and item["text"] != text
    messages, _ = project_material.session_messages({"codex": sub}, since=NOW - timedelta(days=1))
    assert messages[0]["source"] == expected
    assert project_material.REDACTED in messages[0]["text"]
    from connectonion.rem.sessions import _read_session
    session, _ = _read_session(path, "codex", NOW - timedelta(days=1))
    assert session["messages"][0]["source"] == expected
    assert capture.capture(root, path, "codex")["captured"] == 1
    assert capture.pending(root, [], 20, 10000)[0]["source"] == expected


def test_capture_reports_conflict_without_overwriting(atlas):
    root, transcripts, sub = atlas
    path = write_rollout(transcripts, "original", OLD)
    item, = source.collect(sub, {}, 20, 10000).items
    queue = state_path(root, "capture-queue/" + hashlib.sha256(item["source"].encode()).hexdigest() + ".json")
    write_json(queue, {**item, "text": NEW})
    with pytest.raises(RemError, match="conflicting content"):
        capture.capture(root, path, "codex")
    assert json.loads(queue.read_text())["text"] == NEW


@pytest.mark.parametrize("kind", ["codex", "claude-code"])
def test_shared_parser_accepts_old_ids_and_preserves_session(kind):
    old = f"{kind}:{SESSION}:128"
    identity = source.session_source(kind, SESSION, 128, OLD)
    assert source.parse_session_source(old) == (kind, SESSION, 128)
    assert source.parse_session_source(identity) == (kind, SESSION, 128)
    assert identity.rsplit(":", 1)[0] == f"{kind}:{SESSION}"
    assert (identity == old) == (kind == "claude-code")
