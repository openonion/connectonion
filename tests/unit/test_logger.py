"""Unit tests for connectonion/logger.py"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

import connectonion.logger as logger_mod
from connectonion.logger import Logger


class TestLoggerInit:
    """Test Logger initialization."""

    def test_default_init(self):
        """Test Logger with default parameters."""
        logger = Logger("test-agent")

        assert logger.agent_name == "test-agent"
        assert logger.enable_console is True
        assert logger.enable_sessions is True
        assert logger.enable_file is True
        assert logger.log_file_path == Path(".co/logs/test-agent.log")
        assert logger.console is not None

    def test_quiet_mode(self):
        """Test Logger with quiet=True suppresses console but keeps sessions."""
        logger = Logger("test-agent", quiet=True)

        assert logger.enable_console is False
        assert logger.enable_sessions is True  # Sessions still enabled
        assert logger.enable_file is False  # File logging disabled with quiet
        assert logger.console is None

    def test_log_false_disables_everything(self):
        """Test Logger with log=False disables all logging."""
        logger = Logger("test-agent", log=False)

        assert logger.enable_sessions is False
        assert logger.enable_file is False
        assert logger.console is not None  # Console still shows output

    def test_custom_log_path(self):
        """Test Logger with custom log path."""
        logger = Logger("test-agent", log="custom/path.log")

        assert logger.log_file_path == Path("custom/path.log")
        assert logger.enable_file is True
        assert logger.enable_sessions is True

    def test_quiet_with_log_false(self):
        """Test Logger with both quiet=True and log=False."""
        logger = Logger("test-agent", quiet=True, log=False)

        assert logger.enable_console is False
        assert logger.enable_sessions is False
        assert logger.enable_file is False


class TestLoggerDelegation:
    """Test Logger delegates to Console correctly."""

    @patch.object(logger_mod, 'Console')
    def test_print_delegates_to_console(self, mock_console_class):
        """Test Logger.print delegates to Console.print."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        logger = Logger("test-agent")
        logger.print("test message", "bold")

        mock_console.print.assert_called_once_with("test message", "bold")

    @patch.object(logger_mod, 'Console')
    def test_print_silent_when_no_console(self, mock_console_class):
        """Test Logger.print does nothing when quiet=True."""
        logger = Logger("test-agent", quiet=True)

        # Should not raise error
        logger.print("test message")

        # Console should never be created
        mock_console_class.assert_not_called()

    @patch.object(logger_mod, 'Console')
    def test_log_llm_response_delegates(self, mock_console_class):
        """Test Logger.log_llm_response delegates to Console."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        logger = Logger("test-agent")
        logger.log_llm_response(100, 2, MagicMock())

        mock_console.log_llm_response.assert_called_once()


class TestSessionLogging:
    """Test YAML session logging."""

    def test_start_session_creates_file(self, tmp_path, monkeypatch):
        """Test start_session creates session file in .co/sessions/."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        assert logger.session_file is not None
        assert logger.session_file.parent == Path(".co/sessions")
        assert "test-agent" in logger.session_file.name
        assert logger.session_data is not None
        assert logger.session_data["name"] == "test-agent"
        assert logger.session_data["turns"] == []

    def test_start_session_disabled_when_log_false(self, tmp_path, monkeypatch):
        """Test start_session does nothing when log=False."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", log=False)
        logger.start_session()

        assert logger.session_file is None
        assert logger.session_data is None

    def test_log_turn_writes_yaml(self, tmp_path, monkeypatch):
        """Test log_turn writes turn data to YAML file."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        turn_data = {
            "input": "test query",
            "model": "gpt-4",
            "duration_ms": 1000,
            "tokens": 500,
            "cost": 0.01,
            "tools_called": ["search"],
            "result": "test result",
            "messages": '[{"role": "system", "content": "test"}]'
        }

        logger.log_turn(turn_data)

        # Verify file was written
        assert logger.session_file.exists()

        # Verify content
        with open(logger.session_file) as f:
            data = yaml.safe_load(f)

        assert data["name"] == "test-agent"
        assert len(data["turns"]) == 1
        assert data["turns"][0]["input"] == "test query"
        assert data["turns"][0]["model"] == "gpt-4"
        assert data["turns"][0]["tools_called"] == ["search"]

    def test_log_multiple_turns(self, tmp_path, monkeypatch):
        """Test logging multiple turns to same session."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        logger.log_turn({"input": "turn 1", "result": "result 1"})
        logger.log_turn({"input": "turn 2", "result": "result 2"})

        with open(logger.session_file) as f:
            data = yaml.safe_load(f)

        assert len(data["turns"]) == 2
        assert data["turns"][0]["input"] == "turn 1"
        assert data["turns"][1]["input"] == "turn 2"

    def test_log_turn_without_start_session(self, tmp_path, monkeypatch):
        """Test log_turn does nothing if start_session not called."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        # Don't call start_session

        # Should not raise error
        logger.log_turn({"input": "test"})

        assert logger.session_file is None


class TestAgentIntegration:
    """Test Logger integration with Agent._aggregate_turn format."""

    def test_session_format_matches_spec(self, tmp_path, monkeypatch):
        """Test session YAML format matches design spec."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("gmail_agent", quiet=True)
        logger.start_session()

        # Simulate what Agent._aggregate_turn would produce
        turn_data = {
            "input": "check my emails",
            "model": "gemini-2.5-pro",
            "duration_ms": 11200,
            "tokens": 1234,
            "cost": 0.01,
            "tools_called": ["get_emails"],
            "result": "You have 3 emails",
            "messages": '[{"role":"system","content":"You are an email agent"}]'
        }

        logger.log_turn(turn_data)

        with open(logger.session_file) as f:
            data = yaml.safe_load(f)

        # Verify structure matches design doc
        assert "name" in data
        assert "timestamp" in data
        assert "turns" in data
        assert isinstance(data["turns"], list)

        turn = data["turns"][0]
        assert turn["input"] == "check my emails"
        assert turn["model"] == "gemini-2.5-pro"
        assert turn["duration_ms"] == 11200
        assert turn["tokens"] == 1234
        assert turn["cost"] == 0.01
        assert turn["tools_called"] == ["get_emails"]
        assert turn["result"] == "You have 3 emails"
        assert "messages" in turn
