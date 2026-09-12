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
    assert [i["role"] for i in batch.items] == ["user"]  # the assistant's reply is execution, not read
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


def test_oldest_sessions_are_consumed_first(tmp_path):
    """The notebook grows the way the user's understanding did: a backfill walks the
    lookback from its start forward, so later sessions revise earlier pages rather
    than earlier sessions overwriting later ones."""
    old, new = tmp_path / "2026/09/07/rollout-b.jsonl", tmp_path / "2026/09/01/rollout-a.jsonl"
    rollout(old, [("user", "old news")])
    rollout(new, [("user", "fresh news")])
    os.utime(old, (1_790_000_000, 1_790_000_000))   # path order says otherwise; mtime decides
    os.utime(new, (1_790_500_000, 1_790_500_000))
    batch = collect(subscription(tmp_path), {}, 1, 10000)
    assert [item["text"] for item in batch.items] == ["old news"]


def test_codex_injected_blocks_are_not_user_messages(tmp_path):
    """Every codex exec session starts with a `role: user` <recommended_plugins> block the
    user never typed; the first real journey turned it into an 'opportunities' page."""
    file = tmp_path / "2026/09/07/rollout-a.jsonl"
    rollout(file, [("user", "<recommended_plugins>\nHere is a list of plugins that are available but not installed.\n\n- Airtable"),
                   ("user", "<environment_context>\n  <cwd>/work/demo</cwd>\n</environment_context>"),
                   ("user", "Note for the record: Aurora uses Markdown."),
                   ("assistant", "noted")])
    batch = collect(subscription(tmp_path), {}, 10, 10000)
    assert [item["text"] for item in batch.items] == ["Note for the record: Aurora uses Markdown."]


def claude_transcript(path, rows):
    """Rows as Claude Code writes them: one JSON object per line, message.content str or blocks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, (kind, content, extra) in enumerate(rows):
        row = {"type": kind, "timestamp": f"2026-09-07T05:{index:02d}:00.000Z", "cwd": "/work/demo",
               "sessionId": "sess-1", "uuid": f"u{index}", "userType": "external",
               "message": {"role": kind, "content": content}, **extra}
        lines.append(json.dumps(row, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_claude_code_transcript_yields_only_what_the_two_of_them_said(tmp_path):
    file = tmp_path / "-Users-me-projects" / "abc.jsonl"
    claude_transcript(file, [
        ("file-history-snapshot", "", {"message": None}),
        ("user", "<command-message>loop</command-message>\n<command-name>/loop</command-name>", {}),
        ("user", "Alice prefers email over calls.", {}),
        ("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "42 passed"}], {}),
        ("user", [{"type": "text", "text": "Base directory for this skill: /x"}], {"isMeta": True}),
        ("assistant", [{"type": "thinking", "thinking": "hmm"}], {}),
        ("assistant", [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}], {}),
        ("assistant", [{"type": "text", "text": "Noted: Alice prefers email."}], {}),
        ("user", "[Image: original 1080x2348]", {"isMeta": True}),
    ])
    sub = {**subscription(tmp_path), "kind": "claude-code"}
    batch = collect(sub, {}, 10, 10000)
    assert [(i["role"], i["text"]) for i in batch.items] == [("user", "Alice prefers email over calls.")]
    assert batch.items[0]["project"] == "/work/demo"
    assert batch.items[0]["source"].startswith("claude-code:sess-1:")


def test_hyphenated_injected_tags_are_scaffolding_too(tmp_path):
    file = tmp_path / "2026/09/07/rollout-a.jsonl"
    rollout(file, [("user", "<permissions_instructions>\nyou may...</permissions_instructions>"),
                   ("user", "<command-name>/loop</command-name>"), ("user", "real words")])
    assert [i["text"] for i in collect(subscription(tmp_path), {}, 10, 10000).items] == ["real words"]


def test_pasted_blobs_are_capped_and_assistant_rows_are_not_read(tmp_path):
    """60 days of one machine held 134M characters of 'user' text: files and tool output
    relayed as input, not typing. Assistant rows -- commentary or final answer -- are
    execution, not the user's will, and are not read at all."""
    from connectonion.wiki.source import MAX_MESSAGE_CHARS
    file = tmp_path / "2026/09/07/rollout-a.jsonl"
    file.parent.mkdir(parents=True)
    rows = [{"type": "session_meta", "payload": {"id": "s", "cwd": "/work/demo"}}]
    def msg(role, text, **extra):
        return {"timestamp": "2026-09-07T05:00:00Z", "type": "response_item",
                "payload": {"type": "message", "role": role, **extra,
                            "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}]}}
    rows += [msg("user", "x" * (MAX_MESSAGE_CHARS * 3)),
             msg("assistant", "Working on it...", phase="commentary"),
             msg("assistant", "Done: Markdown chosen.", phase="final_answer"),
             msg("assistant", "Older Codex, no phase field.")]
    file.write_text("".join(json.dumps(r) + "\n" for r in rows))
    batch = collect(subscription(tmp_path), {}, 10, 10_000_000)
    texts = [i["text"] for i in batch.items]
    assert len(texts) == 1 and "Working on it" not in "".join(texts) and "Markdown chosen" not in "".join(texts)
    assert len(texts[0]) < MAX_MESSAGE_CHARS + 100 and "truncated" in texts[0]


def test_coding_sessions_yield_only_what_the_user_said(tmp_path):
    """The user's messages are their will; the assistant's replies are execution — code,
    counts, confirmations. Reading only the user halves a coding session and loses
    nothing the notebook is for. (Mail keeps `other` senders: those are people.)"""
    file = tmp_path / "2026/09/07/rollout-a.jsonl"
    rollout(file, [("user", "For Aurora we chose Markdown."), ("assistant", "Noted. I wrote 40 files and ran tests."),
                   ("user", "Correction: inspectability is the reason.")])
    assert [i["role"] for i in collect(subscription(tmp_path), {}, 10, 10000).items] == ["user", "user"]
    claude = tmp_path / "claude" / "abc.jsonl"
    claude_transcript(claude, [("user", "Alice prefers email.", {}),
                               ("assistant", [{"type": "text", "text": "Noted: Alice prefers email."}], {})])
    sub = {**subscription(tmp_path / "claude"), "kind": "claude-code"}
    assert [i["role"] for i in collect(sub, {}, 10, 10000).items] == ["user"]


def passthrough_rollout(path, rows):
    """Codex marks everything it injects into the user turn with a metadata passthrough key;
    a message the human typed carries only `role` and `type`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "session_meta", "payload": {"id": "s1", "cwd": "/work/demo",
                                                             "originator": "codex_cli_rs"}})]
    for typed, text in rows:
        payload = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}
        if not typed:
            payload = {**payload, "id": "msg_1", "internal_chat_message_metadata_passthrough": {"kind": "x"}}
        lines.append(json.dumps({"timestamp": "2026-09-07T05:00:00Z", "type": "response_item", "payload": payload}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_only_what_the_human_typed_survives_the_codex_user_turn(tmp_path):
    """Measured on a real week: 1,493 of 2,062 `role: user` messages were the harness
    talking to itself -- AGENTS.md, the approval reviewer feeding the agent's own
    transcript back in, goal re-injection -- and they were 97.2% of the characters.
    That is where the git SHAs, CI counts and PR numbers on the notebook's pages came
    from: not from the user, whose words are the whole point of reading a session."""
    passthrough_rollout(tmp_path / "2026/09/07/rollout-a.jsonl", [
        (False, "# AGENTS.md instructions for /Users/me/projects\n\n<INSTRUCTIONS>\nRepository Guidelines"),
        (False, "The following is the Codex agent history whose request action you are assessing.\n"
                ">>> TRANSCRIPT START\n[1] shell: git fetch origin main\nHEAD is 89f448e"),
        (False, '<codex_internal_context source="goal">\nContinue working toward the active thread goal.'),
        (True, "然后合并吧，因为 push 破的话，远端也有别的来进行操作。"),
    ])
    batch = collect(subscription(tmp_path), {}, 10, 100000)
    assert [i["text"] for i in batch.items] == ["然后合并吧，因为 push 破的话，远端也有别的来进行操作。"]


def test_harness_preambles_are_not_user_words_even_without_the_marker(tmp_path):
    """Belt and braces: the same texts, with no passthrough key, are still not typed."""
    rollout(tmp_path / "2026/09/07/rollout-b.jsonl", [
        ("user", "# AGENTS.md instructions for /Users/me/projects\n\nRepository Guidelines"),
        ("user", "The following is the Codex agent history added since your last approval assessment."),
        ("user", '<codex_internal_context source="goal">\nContinue working toward the goal.'),
        ("user", "<local-command-stdout>Compacted (ctrl+o to see full summary)</local-command-stdout>"),
        ("user", "This session is being continued from a previous conversation that ran out of context."),
        ("user", "Ship 1.8.5 with the free engine by default."),
    ])
    batch = collect(subscription(tmp_path), {}, 10, 100000)
    assert [i["text"] for i in batch.items] == ["Ship 1.8.5 with the free engine by default."]


def test_claude_code_subagent_prompts_and_skill_bodies_are_not_the_user(tmp_path):
    """A sidechain row is a prompt the assistant wrote for its own subagent, and a skill
    body arrives as a user text block. Neither is the user asking for anything."""
    file = tmp_path / "-Users-me-projects" / "abc.jsonl"
    claude_transcript(file, [
        ("user", "You are one finder angle in a code review. Repo root: /Users/me", {"isSidechain": True}),
        ("user", [{"type": "text", "text": "Base directory for this skill: /Users/me/.claude/skills/x"}], {}),
        ("user", "Keep the release notes short this time.", {}),
    ])
    batch = collect({**subscription(tmp_path), "kind": "claude-code"}, {}, 10, 100000)
    assert [i["text"] for i in batch.items] == ["Keep the release notes short this time."]


def test_an_unfamiliar_codex_user_payload_is_not_assumed_to_be_typed(tmp_path):
    """The allowlist is the whole guarantee, so it must fail closed. Over 30 real days
    there are exactly two shapes in the `role: user` slot: what the person typed
    (`content`, `role`, `type`; median 172 chars) and what Codex injected (the same
    plus `id` and a metadata passthrough; median 3,828 chars). Recognising the
    injection marker would be a denylist, and the day it is renamed we would silently
    go back to reading the agent's own transcript. Recognising the typed shape instead
    means an unfamiliar message is skipped and counted, never read."""
    path = tmp_path / "2026/09/07/rollout-a.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    def row(payload):
        return json.dumps({"timestamp": "2026-09-07T05:00:00Z", "type": "response_item", "payload": payload})
    path.write_text("\n".join([
        json.dumps({"type": "session_meta", "payload": {"id": "s1", "cwd": "/work/demo", "originator": "codex_cli_rs"}}),
        row({"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Ship it on Friday."}]}),
        # tomorrow's Codex, with the marker renamed and a field we have never seen
        row({"type": "message", "role": "user", "id": "m2", "provenance": {"kind": "goal_reinjection"},
             "content": [{"type": "input_text", "text": "Continue working toward the active thread goal."}]}),
    ]) + "\n", encoding="utf-8")
    batch = collect(subscription(tmp_path), {}, 10, 100000)
    assert [i["text"] for i in batch.items] == ["Ship it on Friday."]
    assert batch.skipped == 1 and batch.unrecognised == 1  # skipped, and known to be unfamiliar


def test_claude_code_keeps_what_was_typed_and_counts_the_rest(tmp_path):
    """Typed content is a plain string, or text next to an image the user pasted.
    A list of bare text blocks is the client's own marker ("[Request interrupted by
    user]", a skill body) -- 14 of them in 30 days, none of them typed."""
    file = tmp_path / "-Users-me-projects" / "abc.jsonl"
    claude_transcript(file, [
        ("user", "Ship it on Friday.", {}),
        ("user", [{"type": "image", "source": {}}, {"type": "text", "text": "look at this one"}], {}),
        ("user", [{"type": "text", "text": "[Request interrupted by user]"}], {}),
        ("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "42 passed"}], {}),
    ])
    batch = collect({**subscription(tmp_path), "kind": "claude-code"}, {}, 10, 100000)
    assert [i["text"] for i in batch.items] == ["Ship it on Friday.", "look at this one"]
    assert batch.skipped == 2 and batch.unrecognised == 0  # both shapes are known machinery


def test_a_pass_that_reads_nothing_while_skipping_a_lot_is_not_silent(tmp_path):
    """Failing closed is only safe if it is loud: if the transcript format moves and
    the typed shape stops matching, the notebook would quietly stop learning."""
    path = tmp_path / "2026/09/07/rollout-a.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [json.dumps({"type": "session_meta", "payload": {"id": "s1", "cwd": "/work/demo", "originator": "codex_cli_rs"}})]
    rows += [json.dumps({"timestamp": "2026-09-07T05:00:00Z", "type": "response_item",
                         "payload": {"type": "message", "role": "user", "id": f"m{i}", "unknown_future_field": 1,
                                     "content": [{"type": "input_text", "text": "x" * 100}]}}) for i in range(30)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    batch = collect(subscription(tmp_path), {}, 10, 100000)
    assert batch.items == [] and batch.unrecognised == 30
    assert batch.unreadable  # the caller says so instead of reporting "nothing new"
