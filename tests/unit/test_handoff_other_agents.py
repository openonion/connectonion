"""Handoffs drafted from agents besides Codex and Claude Code (#2501): Gemini CLI, opencode, droid and
Cursor, each from a synthetic session written where and how that agent keeps its own."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from connectonion.handoff import other_agents, sessions


@pytest.fixture
def cwd(tmp_path):
    folder = tmp_path / "login-app"
    folder.mkdir()
    return folder.resolve()


def _gemini(cwd: Path, name: str = "session-2026-10-14T09-00-aaaa.json") -> Path:
    chats = Path.home() / ".gemini" / "tmp" / hashlib.sha256(str(cwd).encode()).hexdigest() / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    path = chats / name
    path.write_text(json.dumps({"sessionId": "g1", "projectHash": hashlib.sha256(str(cwd).encode()).hexdigest(), "messages": [
        {"timestamp": "2026-10-14T09:00:00.000Z", "type": "user", "content": [{"text": "<session_context>\nToday is…"}]},
        {"timestamp": "2026-10-14T09:00:01.000Z", "type": "user", "content": [{"text": "Cookie or localStorage for the token?"}]},
        {"timestamp": "2026-10-14T09:00:02.000Z", "type": "info", "content": "Request cancelled."},
        {"timestamp": "2026-10-14T09:00:03.000Z", "type": "gemini", "content": "The cookie: JS cannot read it.",
         "toolCalls": [{"name": "read_file", "result": "SECRET FILE BODY"}]},
    ]}))
    return path


def test_a_gemini_cli_session_is_found_by_its_project_hash_and_read(cwd):
    path = _gemini(cwd)
    assert sessions.find_session(cwd) == ("gemini", path)
    turns = sessions.read_turns("gemini", path)
    assert [(t["role"], t["text"]) for t in turns] == [("user", "Cookie or localStorage for the token?"),
                                                      ("assistant", "The cookie: JS cannot read it.")]


def test_a_gemini_cli_jsonl_session_takes_its_latest_messages(cwd):
    chats = Path.home() / ".gemini" / "tmp" / "login-app" / "chats"
    chats.mkdir(parents=True)
    (chats.parent / ".project_root").write_text(str(cwd))
    path = chats / "session-2026-10-14T09-00-bbbb.jsonl"
    header = {"sessionId": "g2", "projectHash": hashlib.sha256(str(cwd).encode()).hexdigest()}
    said = [{"timestamp": "2026-10-14T09:00:01.000Z", "type": "user", "content": [{"text": "Ship it?"}]}]
    path.write_text("\n".join(json.dumps(r) for r in [header, {"$set": {"messages": said}},
                    {"timestamp": "2026-10-14T09:00:02.000Z", "type": "gemini", "content": "Yes, after the tests."}]) + "\n")
    assert sessions.find_session(cwd, "gemini") == ("gemini", path)
    assert [t["text"] for t in sessions.read_turns("gemini", path)] == ["Ship it?", "Yes, after the tests."]
    assert sessions.places("gemini", path) == [(cwd, "", "")]


def test_an_opencode_session_is_read_from_its_messages_and_text_parts(cwd):
    storage = Path.home() / ".local" / "share" / "opencode" / "storage"
    (storage / "session" / "p1").mkdir(parents=True)
    path = storage / "session" / "p1" / "ses_1.json"
    path.write_text(json.dumps({"id": "ses_1", "directory": str(cwd), "title": "token"}))
    for n, (role, parts) in enumerate([("user", [{"type": "text", "text": "Cookie or localStorage?"}]),
                                       ("assistant", [{"type": "reasoning", "text": "thinking…"},
                                                      {"type": "tool", "state": {"output": "SECRET"}},
                                                      {"type": "text", "text": "Synthetic note", "synthetic": True},
                                                      {"type": "text", "text": "The cookie."}])]):
        (storage / "message" / "ses_1").mkdir(parents=True, exist_ok=True)
        (storage / "message" / "ses_1" / f"msg_{n}.json").write_text(json.dumps(
            {"id": f"msg_{n}", "role": role, "time": {"created": 1760432400000 + n * 1000}}))
        (storage / "part" / f"msg_{n}").mkdir(parents=True)
        for k, part in enumerate(parts):
            (storage / "part" / f"msg_{n}" / f"prt_{k}.json").write_text(json.dumps(part))
    assert sessions.find_session(cwd) == ("opencode", path)
    turns = sessions.read_turns("opencode", path)
    assert [(t["role"], t["text"]) for t in turns] == [("user", "Cookie or localStorage?"), ("assistant", "The cookie.")]
    assert turns[0]["timestamp"].startswith("2025-10-14T") and sessions.places("opencode", path) == [(cwd, "", "")]


def test_a_droid_session_drops_its_reminders_and_tool_rows(cwd):
    folder = Path.home() / ".factory" / "sessions" / sessions.claude_slug(cwd)
    folder.mkdir(parents=True)
    path = folder / "d1.jsonl"
    rows = [{"type": "session_start", "id": "d1", "cwd": str(cwd)},
            {"type": "message", "timestamp": "2026-10-14T09:00:01Z", "message": {"role": "user", "content": [
                {"type": "text", "text": "<system-reminder>\nModel: X\n</system-reminder>"},
                {"type": "text", "text": "Review the login code"}]}},
            {"type": "message", "timestamp": "2026-10-14T09:00:02Z", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Read", "input": {"path": "a.py"}}]}},
            {"type": "message", "timestamp": "2026-10-14T09:00:03Z", "message": {"role": "user", "content": [
                {"type": "tool_result", "content": "SECRET"}]}},
            {"type": "message", "timestamp": "2026-10-14T09:00:04Z", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Two issues: no CSRF token, and the cookie is not httpOnly."}]}}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert sessions.find_session(cwd) == ("droid", path)
    assert [t["text"] for t in sessions.read_turns("droid", path)] == [
        "Review the login code", "Two issues: no CSRF token, and the cookie is not httpOnly."]
    assert sessions.places("droid", path) == [(cwd, "", "")]


def _cursor(cwd: Path) -> None:
    user = other_agents._cursor_storage()
    workspace = user / "workspaceStorage" / "w1"
    workspace.mkdir(parents=True)
    (workspace / "workspace.json").write_text(json.dumps({"folder": cwd.as_uri()}))
    with sqlite3.connect(workspace / "state.vscdb") as db:
        db.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
        db.execute("INSERT INTO ItemTable VALUES ('composer.composerData', ?)",
                   (json.dumps({"allComposers": [{"composerId": "c1"}]}),))
    (user / "globalStorage").mkdir(parents=True)
    with sqlite3.connect(user / "globalStorage" / "state.vscdb") as db:
        db.execute("CREATE TABLE cursorDiskKV (key TEXT, value TEXT)")
        db.execute("INSERT INTO cursorDiskKV VALUES ('composerData:c1', ?)", (json.dumps({
            "name": "token", "createdAt": 1760432400000, "lastUpdatedAt": 1760432460000,
            "fullConversationHeadersOnly": [{"bubbleId": "b1", "type": 1}, {"bubbleId": "b2", "type": 2},
                                            {"bubbleId": "b3", "type": 2}]}),))
        for bubble, text in (("b1", "Cookie or localStorage?"), ("b2", ""), ("b3", "The cookie.")):
            db.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", (f"bubbleId:c1:{bubble}", json.dumps({"text": text})))


def test_a_cursor_conversation_is_copied_out_of_its_database_and_read(cwd):
    _cursor(cwd)
    kind, path = sessions.find_session(cwd)
    assert kind == "cursor" and path.parent == other_agents.imported_home() / "cursor"
    assert [(t["role"], t["text"]) for t in sessions.read_turns("cursor", path)] == [
        ("user", "Cookie or localStorage?"), ("assistant", "The cookie.")]
    assert sessions.places("cursor", path) == [(cwd, "", "")]
    assert sessions.find_by_id(str(path)) == ("cursor", path)


def test_the_newest_session_of_any_agent_is_the_one_drafted(cwd):
    gemini = _gemini(cwd)
    os.utime(gemini, (1, 1))                            # an old Gemini chat
    folder = Path.home() / ".factory" / "sessions" / sessions.claude_slug(cwd)
    folder.mkdir(parents=True)
    (folder / "d1.jsonl").write_text(json.dumps({"type": "session_start", "cwd": str(cwd)}) + "\n")
    assert sessions.find_session(cwd)[0] == "droid"
    assert sessions.find_session(cwd, "gemini") == ("gemini", gemini)


def test_no_session_names_every_place_it_looked(cwd):
    with pytest.raises(sessions.SessionNotFound) as missing:
        sessions.find_session(cwd)
    for name in ("Gemini CLI", "opencode", "droid", "Cursor"):
        assert name in str(missing.value)


def test_a_grok_session_is_found_by_its_summarys_cwd_and_read_without_tool_rows(cwd):
    """xAI's Grok CLI: the folder name is the cwd encoded (a slug and a hash when long), so the match is
    summary.json's info.cwd; updates.jsonl holds what was said, with tool calls and reasoning between."""
    folder = Path.home() / ".grok" / "sessions" / "a-slug-and-hash" / "01a13809-1cae"
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps({"info": {"id": "01a13809-1cae", "cwd": str(cwd)}}))

    def row(kind, text=None, ms=1791941484827, method="session/update", **extra):
        update = {"sessionUpdate": kind, **({"content": {"type": "text", "text": text}} if text else {}), **extra}
        return json.dumps({"timestamp": ms // 1000 + 6, "method": method,
                           "params": {"sessionId": "01a13809-1cae", "update": update, "_meta": {"agentTimestampMs": ms}}})
    (folder / "updates.jsonl").write_text("\n".join([
        row("user_message_chunk", "Cookie or localStorage for the token?"),
        row("agent_thought_chunk", "thinking about XSS", ms=1791941490000),
        row("tool_call", title="read_file", rawInput={"target_file": "SECRET.txt"}, ms=1791941495371),
        row("tool_call_update", status="completed", rawOutput="SECRET BODY", ms=1791941496000),
        row("agent_message_chunk", "The cookie: JS cannot read it.", ms=1791941497578),
        row("turn_completed", method="_x.ai/session/update", ms=1791941498000)]) + "\n")
    path = folder / "updates.jsonl"
    assert sessions.find_session(cwd) == ("grok", path)
    turns = sessions.read_turns("grok", path)
    assert [(t["role"], t["text"]) for t in turns] == [("user", "Cookie or localStorage for the token?"),
                                                      ("assistant", "The cookie: JS cannot read it.")]
    assert turns[0]["timestamp"] == "2026-10-14T01:31:24.827Z"     # when it was said, not when written
    assert sessions.places("grok", path) == [(cwd, "", "")] and sessions.find_by_id(str(path)) == ("grok", path)
