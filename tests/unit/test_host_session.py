"""Unit tests for connectonion/network/host/session.py

Tests cover:
- Session model (Pydantic BaseModel)
- SessionStorage JSONL file operations
- Session save, get, list operations
- Expiration handling
- Running vs completed sessions
"""

import json
import time
import pytest
from pathlib import Path

from connectonion.network.host.session import Session, SessionStorage


class TestSession:
    """Test Session Pydantic model."""

    def test_create_minimal_session(self):
        """Create session with only required fields."""
        session = Session(session_id="abc123", status="running", prompt="Hello")

        assert session.session_id == "abc123"
        assert session.status == "running"
        assert session.prompt == "Hello"
        assert session.result is None
        assert session.created is None
        assert session.expires is None
        assert session.duration_ms is None

    def test_create_full_session(self):
        """Create session with all fields."""
        now = time.time()
        session = Session(
            session_id="xyz789",
            status="done",
            prompt="Calculate 2+2",
            result="4",
            created=now,
            expires=now + 3600,
            duration_ms=150
        )

        assert session.session_id == "xyz789"
        assert session.status == "done"
        assert session.prompt == "Calculate 2+2"
        assert session.result == "4"
        assert session.created == now
        assert session.expires == now + 3600
        assert session.duration_ms == 150

    def test_model_dump_json(self):
        """Session serializes to JSON correctly."""
        session = Session(session_id="test", status="running", prompt="Hi")
        json_str = session.model_dump_json()

        parsed = json.loads(json_str)
        assert parsed["session_id"] == "test"
        assert parsed["status"] == "running"
        assert parsed["prompt"] == "Hi"

    def test_model_dump(self):
        """Session converts to dict correctly."""
        session = Session(session_id="test", status="done", prompt="Hi", result="Hello")
        data = session.model_dump()

        assert isinstance(data, dict)
        assert data["session_id"] == "test"
        assert data["result"] == "Hello"


class TestSessionStorageInit:
    """Test SessionStorage initialization."""

    def test_default_path(self, tmp_path, monkeypatch):
        """Default path is .co/session_results.jsonl."""
        monkeypatch.chdir(tmp_path)
        storage = SessionStorage()

        assert storage.path == Path(".co/session_results.jsonl")

    def test_custom_path(self, tmp_path):
        """Custom path is used when provided."""
        custom_path = tmp_path / "custom" / "sessions.jsonl"
        storage = SessionStorage(str(custom_path))

        assert storage.path == custom_path

    def test_creates_parent_directory(self, tmp_path):
        """Parent directory is created if it doesn't exist."""
        # Only one level deep - mkdir with exist_ok=True creates single level
        custom_path = tmp_path / "sessions_dir" / "sessions.jsonl"
        custom_path.parent.parent.mkdir(parents=True, exist_ok=True)  # Ensure tmp_path exists
        storage = SessionStorage(str(custom_path))

        assert custom_path.parent.exists()


class TestSessionStorageSave:
    """Test SessionStorage.save() method."""

    def test_save_creates_file(self, tmp_path):
        """save() creates file if it doesn't exist."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))
        session = Session(session_id="test", status="running", prompt="Hello")

        storage.save(session)

        assert path.exists()

    def test_save_appends_to_file(self, tmp_path):
        """save() appends to existing file."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        session1 = Session(session_id="first", status="running", prompt="One")
        session2 = Session(session_id="second", status="running", prompt="Two")

        storage.save(session1)
        storage.save(session2)

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["session_id"] == "first"
        assert json.loads(lines[1])["session_id"] == "second"

    def test_save_valid_json_per_line(self, tmp_path):
        """Each line is valid JSON."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        storage.save(Session(session_id="a", status="running", prompt="A"))
        storage.save(Session(session_id="b", status="done", prompt="B", result="R"))

        for line in path.read_text().strip().split("\n"):
            parsed = json.loads(line)
            assert "session_id" in parsed
            assert "status" in parsed


class TestSessionStorageGet:
    """Test SessionStorage.get() method."""

    def test_get_existing_session(self, tmp_path):
        """get() returns existing session."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        now = time.time()
        session = Session(
            session_id="abc123",
            status="done",
            prompt="Hello",
            result="World",
            created=now,
            expires=now + 3600
        )
        storage.save(session)

        result = storage.get("abc123")

        assert result is not None
        assert result.session_id == "abc123"
        assert result.result == "World"

    def test_get_nonexistent_session(self, tmp_path):
        """get() returns None for nonexistent session."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        storage.save(Session(session_id="other", status="done", prompt="X"))

        result = storage.get("nonexistent")

        assert result is None

    def test_get_no_file(self, tmp_path):
        """get() returns None when file doesn't exist."""
        path = tmp_path / "nonexistent.jsonl"
        storage = SessionStorage(str(path))

        result = storage.get("any")

        assert result is None

    def test_get_last_entry_wins(self, tmp_path):
        """get() returns most recent entry for same session_id."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        now = time.time()
        # Save initial running state
        storage.save(Session(
            session_id="abc",
            status="running",
            prompt="Test",
            created=now,
            expires=now + 3600
        ))
        # Save completed state
        storage.save(Session(
            session_id="abc",
            status="done",
            prompt="Test",
            result="Complete",
            created=now,
            expires=now + 3600,
            duration_ms=100
        ))

        result = storage.get("abc")

        assert result.status == "done"
        assert result.result == "Complete"
        assert result.duration_ms == 100

    def test_get_running_session_not_expired(self, tmp_path):
        """get() returns running session even if expires is past."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        now = time.time()
        storage.save(Session(
            session_id="running",
            status="running",
            prompt="Long task",
            created=now - 7200,
            expires=now - 3600  # Expired but still running
        ))

        result = storage.get("running")

        assert result is not None
        assert result.status == "running"

    def test_get_expired_session_returns_none(self, tmp_path):
        """get() returns None for expired non-running session."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        now = time.time()
        storage.save(Session(
            session_id="expired",
            status="done",
            prompt="Old task",
            result="Result",
            created=now - 7200,
            expires=now - 3600  # Expired
        ))

        result = storage.get("expired")

        assert result is None

    def test_get_no_expires_never_expires(self, tmp_path):
        """get() returns session without expires field."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        storage.save(Session(
            session_id="eternal",
            status="done",
            prompt="Task",
            result="Done"
            # No expires set
        ))

        result = storage.get("eternal")

        assert result is not None
        assert result.session_id == "eternal"


class TestSessionStorageList:
    """Test SessionStorage.list() method."""

    def test_list_empty_file(self, tmp_path):
        """list() returns empty list when file doesn't exist."""
        path = tmp_path / "nonexistent.jsonl"
        storage = SessionStorage(str(path))

        result = storage.list()

        assert result == []

    def test_list_all_sessions(self, tmp_path):
        """list() returns all valid sessions."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        now = time.time()
        storage.save(Session(session_id="a", status="done", prompt="A", created=now))
        storage.save(Session(session_id="b", status="done", prompt="B", created=now + 1))
        storage.save(Session(session_id="c", status="running", prompt="C", created=now + 2))

        result = storage.list()

        assert len(result) == 3

    def test_list_deduplicates_by_session_id(self, tmp_path):
        """list() returns only latest entry for each session_id."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        now = time.time()
        storage.save(Session(session_id="a", status="running", prompt="A", created=now))
        storage.save(Session(session_id="a", status="done", prompt="A", result="Done", created=now))

        result = storage.list()

        assert len(result) == 1
        assert result[0].status == "done"

    def test_list_excludes_expired(self, tmp_path):
        """list() excludes expired non-running sessions."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        now = time.time()
        storage.save(Session(
            session_id="valid",
            status="done",
            prompt="Valid",
            created=now,
            expires=now + 3600
        ))
        storage.save(Session(
            session_id="expired",
            status="done",
            prompt="Expired",
            created=now - 7200,
            expires=now - 3600
        ))

        result = storage.list()

        assert len(result) == 1
        assert result[0].session_id == "valid"

    def test_list_includes_running_even_if_expired(self, tmp_path):
        """list() includes running sessions even if past expires."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        now = time.time()
        storage.save(Session(
            session_id="still_running",
            status="running",
            prompt="Long task",
            created=now - 7200,
            expires=now - 3600  # Past expires but still running
        ))

        result = storage.list()

        assert len(result) == 1
        assert result[0].session_id == "still_running"

    def test_list_sorted_by_created_descending(self, tmp_path):
        """list() sorts by created timestamp descending (newest first)."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        now = time.time()
        storage.save(Session(session_id="old", status="done", prompt="Old", created=now - 100))
        storage.save(Session(session_id="new", status="done", prompt="New", created=now))
        storage.save(Session(session_id="mid", status="done", prompt="Mid", created=now - 50))

        result = storage.list()

        assert len(result) == 3
        assert result[0].session_id == "new"
        assert result[1].session_id == "mid"
        assert result[2].session_id == "old"

    def test_list_handles_missing_created(self, tmp_path):
        """list() handles sessions without created field."""
        path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(path))

        storage.save(Session(session_id="no_created", status="done", prompt="Test"))

        result = storage.list()

        assert len(result) == 1
        assert result[0].session_id == "no_created"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
