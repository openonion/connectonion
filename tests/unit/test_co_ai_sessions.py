"""Tests for co_ai session management."""

from pathlib import Path

import connectonion.cli.co_ai.sessions as sessions_mod


def test_session_manager_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions_mod, "get_db_path", lambda: tmp_path / "sessions.db")
    sessions_mod._manager = None

    manager = sessions_mod.get_session_manager()
    session_id = manager.create_session(model="test-model")
    assert session_id

    manager.save_message("user", "hello")
    manager.save_message("assistant", "hi")

    sessions = manager.list_sessions(limit=10)
    assert sessions and sessions[0]["id"] == session_id

    messages = manager.load_session(session_id)
    assert messages and messages[0]["content"] == "hello"

    assert manager.delete_session(session_id) is True
    assert manager.load_session(session_id) is None
