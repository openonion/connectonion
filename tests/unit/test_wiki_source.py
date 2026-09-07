"""Synthetic native rollouts: never inspect the operator's session store."""

import json
from pathlib import Path

import pytest

from connectonion.wiki.files import WikiError
from connectonion.wiki.source import collect, pending_metadata


def rollout(path, messages, *, project="/work/demo", originator="codex_cli_rs"):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "session_meta", "payload": {
        "id": "session-1", "cwd": project, "originator": originator}}]
    for role, text in messages:
        rows.append({"timestamp": "2026-09-07T05:00:00Z", "type": "response_item",
                     "payload": {"type": "message", "role": role,
                                 "content": [{"type": "input_text", "text": text}]}})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def subscription(path, **kwargs):
    return {"id": "codex", "root": str(path), "since": "2026-09-01T00:00:00Z",
            "project": None, "enabled": True, "consented": True, **kwargs}


def test_second_pass_is_noop_and_appends_only_new_messages(tmp_path):
    file = tmp_path / "2026/09/07/rollout-one.jsonl"
    rollout(file, [("user", "Use SQL"), ("assistant", "Possible option")])
    batch = collect(subscription(tmp_path), {}, max_items=20, max_chars=10000)
    assert [i["role"] for i in batch.items] == ["user", "assistant"]
    assert not collect(subscription(tmp_path), batch.progress, 20, 10000).items
    rollout(file, [("user", "Use SQL"), ("assistant", "Possible option"),
                   ("user", "Correction: choose Markdown")])
    new = collect(subscription(tmp_path), batch.progress, 20, 10000)
    assert [i["text"] for i in new.items] == ["Correction: choose Markdown"]


def test_partial_batch_keeps_unread_input(tmp_path):
    rollout(tmp_path / "rollout-a.jsonl", [("user", str(i)) for i in range(4)])
    first = collect(subscription(tmp_path), {}, 2, 10000)
    second = collect(subscription(tmp_path), first.progress, 2, 10000)
    assert [i["text"] for i in first.items + second.items] == ["0", "1", "2", "3"]


def test_only_authorized_project_and_user_assistant_text(tmp_path):
    rollout(tmp_path / "rollout-a.jsonl", [("developer", "secret rules"),
                                           ("tool", "secret tool result"),
                                           ("user", "Keep this")])
    rollout(tmp_path / "rollout-b.jsonl", [("user", "other project")], project="/work/other")
    batch = collect(subscription(tmp_path, project="/work/demo"), {}, 20, 10000)
    assert [i["text"] for i in batch.items] == ["Keep this"]


def test_organizer_does_not_ingest_itself(tmp_path):
    rollout(tmp_path / "rollout-a.jsonl", [("user", "recursive input")], originator="co_wiki")
    assert not collect(subscription(tmp_path), {}, 20, 10000).items


def test_incomplete_tail_is_not_consumed(tmp_path):
    file = tmp_path / "rollout-a.jsonl"
    rollout(file, [("user", "complete")])
    with file.open("a") as output:
        output.write('{"type":')
    first = collect(subscription(tmp_path), {}, 20, 10000)
    assert len(first.items) == 1
    assert first.progress["rollout-a.jsonl"]["offset"] < file.stat().st_size


def test_rewritten_consumed_prefix_fails_without_losing_progress(tmp_path):
    file = tmp_path / "rollout-a.jsonl"
    rollout(file, [("user", "first")])
    first = collect(subscription(tmp_path), {}, 20, 10000)
    rollout(file, [("user", "changed")])
    with pytest.raises(WikiError, match="changed"):
        collect(subscription(tmp_path), first.progress, 20, 10000)


def test_dry_run_does_not_open_bodies(tmp_path, monkeypatch):
    rollout(tmp_path / "rollout-a.jsonl", [("user", "do not read")])
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("opened body"))
    assert pending_metadata(subscription(tmp_path), {})["candidate_files"] == 1


def test_disabled_and_unconsented_sources_cannot_be_collected(tmp_path):
    for overrides in ({"enabled": False}, {"consented": False}):
        with pytest.raises(WikiError):
            collect(subscription(tmp_path, **overrides), {}, 20, 10000)


def test_huge_message_is_not_silently_consumed(tmp_path):
    rollout(tmp_path / "rollout-a.jsonl", [("user", "x" * 2000)])
    with pytest.raises(WikiError, match="limit"):
        collect(subscription(tmp_path), {}, 20, 500)
