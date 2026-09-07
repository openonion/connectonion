"""Synthetic native rollouts: never inspect the operator's session store."""

import json
import os
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



def test_huge_rollout_is_streamed_not_refused(tmp_path, monkeypatch):
    """A 426 MB session exists on a real machine. Refusing it would block every source forever."""
    monkeypatch.setattr("connectonion.wiki.source.SCAN_BYTES_PER_PASS", 2000)
    file = tmp_path / "2026/09/07/rollout-huge.jsonl"
    file.parent.mkdir(parents=True)
    meta = json.dumps({"type": "session_meta", "payload": {"id": "s", "cwd": "/work/demo"}}) + "\n"
    blob = json.dumps({"timestamp": "2026-09-07T05:00:00Z", "type": "response_item",
                       "payload": {"type": "function_call_output", "output": "x" * 5000}}) + "\n"
    late = json.dumps({"timestamp": "2026-09-07T06:00:00Z", "type": "response_item",
                       "payload": {"type": "message", "role": "user",
                                   "content": [{"type": "input_text", "text": "Keep Markdown"}]}}) + "\n"
    file.write_text(meta + blob + late)
    progress, texts = {}, []
    for _ in range(6):  # several bounded passes walk past the blob and reach the message
        batch = collect(subscription(tmp_path), progress, 10, 10000)
        texts += [item["text"] for item in batch.items]
        progress = batch.progress
    assert texts == ["Keep Markdown"]
    assert progress["2026/09/07/rollout-huge.jsonl"]["offset"] == len(meta + blob + late)


def test_files_older_than_the_lookback_are_not_opened(tmp_path, monkeypatch):
    file = tmp_path / "2026/08/01/rollout-old.jsonl"
    rollout(file, [("user", "ancient")])
    os.utime(file, (1_600_000_000, 1_600_000_000))  # 2020: nothing inside can postdate `since`
    monkeypatch.setattr("connectonion.wiki.source._read_rollout",
                        lambda *a, **k: pytest.fail("opened a file that cannot contain new messages"))
    batch = collect(subscription(tmp_path), {}, 10, 10000)
    assert batch.items == []


def test_oversized_single_message_is_truncated_and_progress_advances(tmp_path):
    file = tmp_path / "2026/09/07/rollout-big-message.jsonl"
    rollout(file, [("user", "y" * 5000), ("user", "after")])
    batch = collect(subscription(tmp_path), {}, 10, 1200)
    assert [item["text"][:5] for item in batch.items][0] == "yyyyy"
    assert "truncated" in batch.items[0]["text"]
    assert len(json.dumps(batch.items[0], ensure_ascii=False)) <= 1200
    assert batch.progress["2026/09/07/rollout-big-message.jsonl"]["offset"] > 0


def test_newest_sessions_are_consumed_first(tmp_path):
    """On first start the backlog is a week deep; the notebook should be useful today, not in June."""
    old, new = tmp_path / "2026/09/01/rollout-a.jsonl", tmp_path / "2026/09/07/rollout-b.jsonl"
    rollout(old, [("user", "old news")])
    rollout(new, [("user", "fresh news")])
    os.utime(old, (1_790_000_000, 1_790_000_000))
    os.utime(new, (1_790_500_000, 1_790_500_000))
    batch = collect(subscription(tmp_path), {}, 1, 10000)
    assert [item["text"] for item in batch.items] == ["fresh news"]


def test_codex_injected_blocks_are_not_user_messages(tmp_path):
    """Every codex exec session starts with a `role: user` <recommended_plugins> block the
    user never typed; the first real journey turned it into an 'opportunities' page."""
    file = tmp_path / "2026/09/07/rollout-a.jsonl"
    rollout(file, [("user", "<recommended_plugins>\nHere is a list of plugins that are available but not installed.\n\n- Airtable"),
                   ("user", "<environment_context>\n  <cwd>/work/demo</cwd>\n</environment_context>"),
                   ("user", "Note for the record: Aurora uses Markdown."),
                   ("assistant", "noted")])
    batch = collect(subscription(tmp_path), {}, 10, 10000)
    assert [item["text"] for item in batch.items] == ["Note for the record: Aurora uses Markdown.", "noted"]
