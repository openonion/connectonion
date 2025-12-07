"""Unit tests for connectonion/logger.py"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

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

    @patch.object(logger_mod, 'Console')
    def test_log_tool_call_delegates_to_console(self, mock_console_class):
        """Test Logger.log_tool_call delegates to Console.log_tool_call."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        logger = Logger("test-agent")
        logger.log_tool_call("greet", {"name": "Alice"})

        mock_console.log_tool_call.assert_called_once_with("greet", {"name": "Alice"})

    @patch.object(logger_mod, 'Console')
    def test_log_tool_result_delegates_to_console(self, mock_console_class):
        """Test Logger.log_tool_result delegates to Console.log_tool_result."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        logger = Logger("test-agent")
        logger.log_tool_result("Hello, Alice!", 123.45)

        mock_console.log_tool_result.assert_called_once_with("Hello, Alice!", 123.45)

    def test_log_tool_call_silent_when_no_console(self):
        """Test Logger.log_tool_call does nothing when quiet=True."""
        logger = Logger("test-agent", quiet=True)
        # Should not raise error
        logger.log_tool_call("greet", {"name": "Alice"})

    def test_log_tool_result_silent_when_no_console(self):
        """Test Logger.log_tool_result does nothing when quiet=True."""
        logger = Logger("test-agent", quiet=True)
        # Should not raise error
        logger.log_tool_result("result", 100.0)


class TestFormatToolCall:
    """Test _format_tool_call method for YAML output."""

    def test_format_tool_call_simple(self):
        """Test formatting simple tool call."""
        logger = Logger("test-agent", log=False)
        trace_entry = {
            'tool_name': 'greet',
            'arguments': {'name': 'Alice'}
        }
        result = logger._format_tool_call(trace_entry)
        assert result == "greet(name='Alice')"

    def test_format_tool_call_multiple_args(self):
        """Test formatting tool call with multiple args."""
        logger = Logger("test-agent", log=False)
        trace_entry = {
            'tool_name': 'write_file',
            'arguments': {'path': 'test.py', 'content': 'print("hello")'}
        }
        result = logger._format_tool_call(trace_entry)
        assert result == "write_file(path='test.py', content='print(\"hello\")')"

    def test_format_tool_call_truncates_long_string(self):
        """Test that long string values are truncated to 50 chars."""
        logger = Logger("test-agent", log=False)
        long_content = "x" * 100
        trace_entry = {
            'tool_name': 'write',
            'arguments': {'content': long_content}
        }
        result = logger._format_tool_call(trace_entry)
        assert "x" * 50 + "..." in result
        assert "x" * 51 not in result

    def test_format_tool_call_non_string_value(self):
        """Test formatting tool call with non-string values."""
        logger = Logger("test-agent", log=False)
        trace_entry = {
            'tool_name': 'search',
            'arguments': {'limit': 10, 'include_all': True}
        }
        result = logger._format_tool_call(trace_entry)
        assert "limit=10" in result
        assert "include_all=True" in result

    def test_format_tool_call_empty_args(self):
        """Test formatting tool call with no arguments."""
        logger = Logger("test-agent", log=False)
        trace_entry = {
            'tool_name': 'get_time',
            'arguments': {}
        }
        result = logger._format_tool_call(trace_entry)
        assert result == "get_time()"


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

    def test_start_session_with_system_prompt(self, tmp_path, monkeypatch):
        """Test start_session stores system prompt."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session("You are a helpful assistant")

        assert logger.session_data["system_prompt"] == "You are a helpful assistant"

    def test_start_session_disabled_when_log_false(self, tmp_path, monkeypatch):
        """Test start_session does nothing when log=False."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", log=False)
        logger.start_session()

        assert logger.session_file is None
        assert logger.session_data is None

    def _create_mock_session(self, tool_calls=None):
        """Helper to create mock session dict for log_turn."""
        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cost = 0.01

        trace = [
            {'type': 'llm_call', 'usage': mock_usage}
        ]
        if tool_calls:
            for tc in tool_calls:
                trace.append({
                    'type': 'tool_execution',
                    'tool_name': tc['name'],
                    'arguments': tc.get('args', {})
                })

        return {
            'trace': trace,
            'messages': [
                {'role': 'system', 'content': 'You are helpful'},
                {'role': 'user', 'content': 'test query'},
                {'role': 'assistant', 'content': 'test result'}
            ]
        }

    def test_log_turn_writes_yaml(self, tmp_path, monkeypatch):
        """Test log_turn writes turn data to YAML file."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        session = self._create_mock_session([{'name': 'search', 'args': {'query': 'test'}}])
        logger.log_turn("test query", "test result", 1000, session, "gpt-4")

        # Verify file was written
        assert logger.session_file.exists()

        # Verify content
        with open(logger.session_file) as f:
            data = yaml.safe_load(f)

        assert data["name"] == "test-agent"
        assert len(data["turns"]) == 1
        assert data["turns"][0]["input"] == "test query"
        assert data["turns"][0]["result"] == "test result"
        assert data["turns"][0]["model"] == "gpt-4"
        assert data["turns"][0]["duration_ms"] == 1000

    def test_log_turn_tools_called_format(self, tmp_path, monkeypatch):
        """Test tools_called uses natural function-call format."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        session = self._create_mock_session([
            {'name': 'greet', 'args': {'name': 'Alice'}},
            {'name': 'write', 'args': {'path': 'test.txt'}}
        ])
        logger.log_turn("test", "result", 100, session, "gpt-4")

        with open(logger.session_file) as f:
            data = yaml.safe_load(f)

        tools = data["turns"][0]["tools_called"]
        assert "greet(name='Alice')" in tools
        assert "write(path='test.txt')" in tools

    def test_log_multiple_turns(self, tmp_path, monkeypatch):
        """Test logging multiple turns to same session."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        session1 = self._create_mock_session()
        session2 = self._create_mock_session()

        logger.log_turn("turn 1", "result 1", 100, session1, "gpt-4")
        logger.log_turn("turn 2", "result 2", 200, session2, "gpt-4")

        with open(logger.session_file) as f:
            data = yaml.safe_load(f)

        assert len(data["turns"]) == 2
        assert data["turns"][0]["input"] == "turn 1"
        assert data["turns"][0]["turn"] == 1
        assert data["turns"][1]["input"] == "turn 2"
        assert data["turns"][1]["turn"] == 2

    def test_log_turn_aggregates_cost_and_tokens(self, tmp_path, monkeypatch):
        """Test total_cost and total_tokens are aggregated across turns."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        session1 = self._create_mock_session()  # cost=0.01, tokens=150
        session2 = self._create_mock_session()  # cost=0.01, tokens=150

        logger.log_turn("turn 1", "result 1", 100, session1, "gpt-4")
        logger.log_turn("turn 2", "result 2", 200, session2, "gpt-4")

        with open(logger.session_file) as f:
            data = yaml.safe_load(f)

        assert data["total_cost"] == 0.02
        assert data["total_tokens"] == 300

    def test_log_turn_without_start_session(self, tmp_path, monkeypatch):
        """Test log_turn does nothing if start_session not called."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        # Don't call start_session

        session = self._create_mock_session()
        # Should not raise error
        logger.log_turn("test", "result", 100, session, "gpt-4")

        assert logger.session_file is None


class TestSessionYAMLFormat:
    """Test session YAML format matches design spec."""

    def _create_mock_session(self):
        """Helper to create mock session dict."""
        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cost = 0.01

        return {
            'trace': [{'type': 'llm_call', 'usage': mock_usage}],
            'messages': [
                {'role': 'system', 'content': 'System prompt'},
                {'role': 'user', 'content': 'test query'},
                {'role': 'assistant', 'content': 'test result'}
            ]
        }

    def test_yaml_field_order(self, tmp_path, monkeypatch):
        """Test YAML fields are in correct order: metadata, turns, system_prompt, messages."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session("You are helpful")
        logger.log_turn("test", "result", 100, self._create_mock_session(), "gpt-4")

        # Read raw file to check order
        with open(logger.session_file) as f:
            content = f.read()

        # Check order by finding positions
        name_pos = content.find("name:")
        turns_pos = content.find("turns:")
        system_prompt_pos = content.find("system_prompt:")
        messages_pos = content.find("messages:")

        assert name_pos < turns_pos < system_prompt_pos < messages_pos

    def test_messages_keyed_by_turn_number(self, tmp_path, monkeypatch):
        """Test messages are keyed by turn number (1, 2, 3...)."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        session = self._create_mock_session()
        logger.log_turn("turn 1", "result 1", 100, session, "gpt-4")
        logger.log_turn("turn 2", "result 2", 200, session, "gpt-4")

        with open(logger.session_file) as f:
            data = yaml.safe_load(f)

        assert 1 in data["messages"]
        assert 2 in data["messages"]
        assert isinstance(data["messages"][1], list)
        assert isinstance(data["messages"][2], list)


class TestLoadMethods:
    """Test load_messages and load_session methods."""

    def _setup_session_file(self, tmp_path, monkeypatch):
        """Helper to set up a session file with test data."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session("You are a helpful assistant")

        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cost = 0.01

        session = {
            'trace': [{'type': 'llm_call', 'usage': mock_usage}],
            'messages': [
                {'role': 'system', 'content': 'You are a helpful assistant'},
                {'role': 'user', 'content': 'hello'},
                {'role': 'assistant', 'content': 'Hi there!'}
            ]
        }
        logger.log_turn("hello", "Hi there!", 100, session, "gpt-4")
        return logger

    def test_load_messages_reconstructs_history(self, tmp_path, monkeypatch):
        """Test load_messages reconstructs full message history."""
        logger = self._setup_session_file(tmp_path, monkeypatch)

        messages = logger.load_messages()

        assert len(messages) >= 1
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant"

    def test_load_messages_empty_when_no_file(self, tmp_path, monkeypatch):
        """Test load_messages returns empty list when no session file."""
        monkeypatch.chdir(tmp_path)
        logger = Logger("test-agent", quiet=True)
        # Don't call start_session

        messages = logger.load_messages()
        assert messages == []

    def test_load_session_returns_data(self, tmp_path, monkeypatch):
        """Test load_session returns session data dict."""
        logger = self._setup_session_file(tmp_path, monkeypatch)

        data = logger.load_session()

        assert data["name"] == "test-agent"
        assert data["system_prompt"] == "You are a helpful assistant"
        assert len(data["turns"]) == 1
        assert data["turns"][0]["input"] == "hello"

    def test_load_session_returns_default_when_no_file(self, tmp_path, monkeypatch):
        """Test load_session returns default dict when no file."""
        monkeypatch.chdir(tmp_path)
        logger = Logger("test-agent", quiet=True)
        # Don't call start_session

        data = logger.load_session()

        assert data == {'system_prompt': '', 'turns': [], 'messages': {}}
