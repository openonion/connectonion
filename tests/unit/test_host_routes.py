"""Unit tests for connectonion/network/host/routes.py

Tests cover:
- input_handler() - POST /input route
- session_handler() - GET /sessions/{id} route
- sessions_handler() - GET /sessions route
- health_handler() - GET /health route
- info_handler() - GET /info route
- admin_logs_handler() - GET /admin/logs route
- admin_sessions_handler() - GET /admin/sessions route
"""

import time
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from connectonion.network.host.routes import (
    input_handler,
    session_handler,
    sessions_handler,
    health_handler,
    info_handler,
    admin_logs_handler,
    admin_sessions_handler,
    admin_trust_promote_handler,
    admin_trust_demote_handler,
    admin_trust_block_handler,
    admin_trust_unblock_handler,
    admin_trust_level_handler,
    admin_admins_add_handler,
    admin_admins_remove_handler,
)
from connectonion.network.host.session import Session, SessionStorage


class TestInputHandler:
    """Test input_handler route."""

    def test_returns_result_dict(self, tmp_path):
        """input_handler returns dict with session info."""
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        mock_agent = Mock()
        mock_agent.input.return_value = "Agent response"
        mock_agent.current_session = {"messages": []}

        # Factory function returns mock agent
        create_agent = Mock(return_value=mock_agent)

        result = input_handler(create_agent, storage, "Hello", result_ttl=3600)

        assert "session_id" in result
        assert result["status"] == "done"
        assert result["result"] == "Agent response"
        assert "duration_ms" in result
        assert "session" in result

    def test_creates_new_session_id(self, tmp_path):
        """input_handler generates new session_id when not provided."""
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        mock_agent = Mock()
        mock_agent.input.return_value = "Response"
        mock_agent.current_session = {}

        create_agent = Mock(return_value=mock_agent)
        result = input_handler(create_agent, storage, "Hello", result_ttl=3600)

        assert result["session_id"] is not None
        assert len(result["session_id"]) > 0

    def test_uses_existing_session_id(self, tmp_path):
        """input_handler uses session_id from session when provided."""
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        mock_agent = Mock()
        mock_agent.input.return_value = "Continued response"
        mock_agent.current_session = {}

        session = {"session_id": "existing-123", "messages": []}

        create_agent = Mock(return_value=mock_agent)
        result = input_handler(create_agent, storage, "Continue", result_ttl=3600, session=session)

        assert result["session_id"] == "existing-123"

    def test_adds_session_id_to_empty_session(self, tmp_path):
        """input_handler adds session_id to session dict if missing."""
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        mock_agent = Mock()
        mock_agent.input.return_value = "Response"
        mock_agent.current_session = {}

        session = {"messages": []}  # No session_id

        create_agent = Mock(return_value=mock_agent)
        result = input_handler(create_agent, storage, "Hello", result_ttl=3600, session=session)

        assert "session_id" in session  # Should be mutated
        assert session["session_id"] == result["session_id"]

    def test_saves_running_then_done(self, tmp_path):
        """input_handler saves session twice (running, then done)."""
        storage_path = tmp_path / "sessions.jsonl"
        storage = SessionStorage(str(storage_path))

        mock_agent = Mock()
        mock_agent.input.return_value = "Result"
        mock_agent.current_session = {}

        create_agent = Mock(return_value=mock_agent)
        input_handler(create_agent, storage, "Hello", result_ttl=3600)

        lines = storage_path.read_text().strip().split("\n")
        assert len(lines) == 2  # Running + Done

    def test_records_duration_ms(self, tmp_path):
        """input_handler records execution duration."""
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        mock_agent = Mock()
        mock_agent.input.return_value = "Response"
        mock_agent.current_session = {}

        create_agent = Mock(return_value=mock_agent)
        result = input_handler(create_agent, storage, "Hello", result_ttl=3600)

        assert result["duration_ms"] >= 0

    def test_factory_creates_fresh_agent(self, tmp_path):
        """input_handler calls factory to create fresh agent per request."""
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        mock_agent = Mock()
        mock_agent.input.return_value = "Response"
        mock_agent.current_session = {}

        create_agent = Mock(return_value=mock_agent)
        input_handler(create_agent, storage, "Hello", result_ttl=3600)

        create_agent.assert_called_once()
        mock_agent.input.assert_called_once()


class TestSessionHandler:
    """Test session_handler route."""

    def test_returns_existing_session(self, tmp_path):
        """session_handler returns session when found."""
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        now = time.time()
        session = Session(
            session_id="test-123",
            status="done",
            prompt="Hello",
            result="World",
            created=now,
            expires=now + 3600
        )
        storage.save(session)

        result = session_handler(storage, "test-123")

        assert result is not None
        assert result["session_id"] == "test-123"
        assert result["result"] == "World"

    def test_returns_none_for_missing(self, tmp_path):
        """session_handler returns None for missing session."""
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        result = session_handler(storage, "nonexistent")

        assert result is None


class TestSessionsHandler:
    """Test sessions_handler route."""

    def test_returns_all_sessions(self, tmp_path):
        """sessions_handler returns list of all sessions."""
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        now = time.time()
        storage.save(Session(session_id="a", status="done", prompt="A", created=now))
        storage.save(Session(session_id="b", status="done", prompt="B", created=now + 1))

        result = sessions_handler(storage)

        assert "sessions" in result
        assert len(result["sessions"]) == 2

    def test_returns_empty_list(self, tmp_path):
        """sessions_handler returns empty list when no sessions."""
        storage = SessionStorage(str(tmp_path / "nonexistent.jsonl"))

        result = sessions_handler(storage)

        assert result == {"sessions": []}


class TestHealthHandler:
    """Test health_handler route."""

    def test_returns_healthy_status(self):
        """health_handler returns healthy status."""
        start_time = time.time() - 60  # Started 60 seconds ago

        result = health_handler("test_agent", start_time)

        assert result["status"] == "healthy"
        assert result["agent"] == "test_agent"
        assert result["uptime"] >= 60

    def test_uptime_calculation(self):
        """health_handler calculates uptime correctly."""
        start_time = time.time() - 120  # 2 minutes ago

        result = health_handler("test", start_time)

        assert result["uptime"] >= 120


class TestInfoHandler:
    """Test info_handler route."""

    def test_returns_agent_info(self):
        """info_handler returns agent information."""
        metadata = {
            "name": "my_agent",
            "tools": ["tool1", "tool2"],
            "address": "0x123",
        }

        result = info_handler(metadata, "careful")

        assert result["name"] == "my_agent"
        assert result["tools"] == ["tool1", "tool2"]
        assert result["trust"] == "careful"
        assert "version" in result

    def test_returns_onboard_info(self):
        """info_handler includes onboard info when trust_config provided."""
        metadata = {
            "name": "agent",
            "tools": [],
            "address": "0x123",
        }
        trust_config = {
            "onboard": {
                "invite_code": ["BETA2024"],
                "payment": 10,
            }
        }

        result = info_handler(metadata, "careful", trust_config)

        assert "onboard" in result
        assert result["onboard"]["invite_code"] is True
        assert result["onboard"]["payment"] == 10

    def test_no_onboard_without_config(self):
        """info_handler doesn't include onboard when no trust_config."""
        metadata = {
            "name": "agent",
            "tools": [],
            "address": "0x123",
        }

        result = info_handler(metadata, "open")

        assert "onboard" not in result

    def test_no_onboard_without_onboard_key(self):
        """info_handler doesn't include onboard when config has no onboard key."""
        metadata = {
            "name": "agent",
            "tools": [],
            "address": "0x123",
        }
        trust_config = {"default": "allow"}  # No onboard key

        result = info_handler(metadata, "open", trust_config)

        assert "onboard" not in result


class TestAdminLogsHandler:
    """Test admin_logs_handler route."""

    def test_returns_log_content(self, tmp_path, monkeypatch):
        """admin_logs_handler returns log file content."""
        monkeypatch.chdir(tmp_path)

        log_dir = tmp_path / ".co" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "test_agent.log"
        log_file.write_text("Log line 1\nLog line 2\n")

        result = admin_logs_handler("test_agent")

        assert "content" in result
        assert "Log line 1" in result["content"]
        assert "Log line 2" in result["content"]

    def test_returns_error_for_missing(self, tmp_path, monkeypatch):
        """admin_logs_handler returns error when log doesn't exist."""
        monkeypatch.chdir(tmp_path)

        result = admin_logs_handler("nonexistent_agent")

        assert "error" in result
        assert result["error"] == "No logs found"


class TestAdminSessionsHandler:
    """Test admin_sessions_handler route."""

    def test_returns_session_files(self, tmp_path, monkeypatch):
        """admin_sessions_handler returns YAML session files as JSON."""
        monkeypatch.chdir(tmp_path)

        evals_dir = tmp_path / ".co" / "evals"
        evals_dir.mkdir(parents=True)

        session_file = evals_dir / "agent_2024-01-15.yaml"
        session_file.write_text("""
name: test_agent
created: "2024-01-15T10:00:00"
updated: "2024-01-15T10:05:00"
total_cost: 0.01
total_tokens: 100
turns:
  - input: Hello
    result: World
""")

        result = admin_sessions_handler()

        assert "sessions" in result
        assert len(result["sessions"]) == 1
        assert result["sessions"][0]["name"] == "test_agent"

    def test_returns_empty_when_no_dir(self, tmp_path, monkeypatch):
        """admin_sessions_handler returns empty list when dir doesn't exist."""
        monkeypatch.chdir(tmp_path)

        result = admin_sessions_handler()

        assert result == {"sessions": []}

    def test_sorted_by_updated_descending(self, tmp_path, monkeypatch):
        """admin_sessions_handler sorts sessions by updated desc."""
        monkeypatch.chdir(tmp_path)

        evals_dir = tmp_path / ".co" / "evals"
        evals_dir.mkdir(parents=True)

        # Older session
        (evals_dir / "old.yaml").write_text("""
name: old
updated: "2024-01-10T10:00:00"
""")

        # Newer session
        (evals_dir / "new.yaml").write_text("""
name: new
updated: "2024-01-15T10:00:00"
""")

        result = admin_sessions_handler()

        assert len(result["sessions"]) == 2
        assert result["sessions"][0]["name"] == "new"  # Newest first
        assert result["sessions"][1]["name"] == "old"


class TestAdminTrustHandlers:
    """Test admin trust route handlers."""

    @pytest.mark.parametrize(
        "level,method_called,new_level,expected_error",
        [
            ("stranger", "promote_to_contact", "contact", None),
            ("contact", "promote_to_whitelist", "whitelist", None),
            ("whitelist", None, None, "Already at highest level"),
            ("blocked", None, None, "Client is blocked. Unblock first."),
            ("unknown", None, None, "Unknown level: unknown"),
        ],
    )
    def test_promote_handler(self, level, method_called, new_level, expected_error):
        trust_agent = Mock()
        if method_called:
            getattr(trust_agent, method_called).return_value = "ok"
            trust_agent.get_level.side_effect = [level, new_level]
        else:
            trust_agent.get_level.return_value = level

        result = admin_trust_promote_handler(trust_agent, "0xclient")

        if expected_error:
            assert result["error"] == expected_error
            return

        assert result["success"] is True
        assert result["level"] == new_level
        getattr(trust_agent, method_called).assert_called_once_with("0xclient")

    @pytest.mark.parametrize(
        "level,method_called,new_level,expected_error",
        [
            ("whitelist", "demote_to_contact", "contact", None),
            ("contact", "demote_to_stranger", "stranger", None),
            ("stranger", None, None, "Already at lowest level"),
            ("blocked", None, None, "Client is blocked. Unblock first."),
            ("unknown", None, None, "Unknown level: unknown"),
        ],
    )
    def test_demote_handler(self, level, method_called, new_level, expected_error):
        trust_agent = Mock()
        if method_called:
            getattr(trust_agent, method_called).return_value = "ok"
            trust_agent.get_level.side_effect = [level, new_level]
        else:
            trust_agent.get_level.return_value = level

        result = admin_trust_demote_handler(trust_agent, "0xclient")

        if expected_error:
            assert result["error"] == expected_error
            return

        assert result["success"] is True
        assert result["level"] == new_level
        getattr(trust_agent, method_called).assert_called_once_with("0xclient")

    def test_block_handler(self):
        trust_agent = Mock()
        trust_agent.block.return_value = "blocked"
        trust_agent.get_level.return_value = "blocked"

        result = admin_trust_block_handler(trust_agent, "0xclient", reason="spam")

        trust_agent.block.assert_called_once_with("0xclient", "spam")
        assert result["success"] is True
        assert result["level"] == "blocked"

    def test_unblock_handler(self):
        trust_agent = Mock()
        trust_agent.unblock.return_value = "unblocked"
        trust_agent.get_level.return_value = "stranger"

        result = admin_trust_unblock_handler(trust_agent, "0xclient")

        trust_agent.unblock.assert_called_once_with("0xclient")
        assert result["success"] is True
        assert result["level"] == "stranger"

    def test_level_handler(self):
        trust_agent = Mock()
        trust_agent.get_level.return_value = "contact"

        result = admin_trust_level_handler(trust_agent, "0xclient")

        assert result == {"client_id": "0xclient", "level": "contact"}

    def test_admin_add_handler(self):
        trust_agent = Mock()
        trust_agent.add_admin.return_value = "added"

        result = admin_admins_add_handler(trust_agent, "0xadmin")

        trust_agent.add_admin.assert_called_once_with("0xadmin")
        assert result["success"] is True

    def test_admin_remove_handler(self):
        trust_agent = Mock()
        trust_agent.remove_admin.return_value = "removed"

        result = admin_admins_remove_handler(trust_agent, "0xadmin")

        trust_agent.remove_admin.assert_called_once_with("0xadmin")
        assert result["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
