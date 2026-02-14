"""Unit tests for connectonion/logger.py"""

import json
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

import connectonion.logger as logger_mod
from connectonion.logger import Logger, _slugify


class TestSlugify:
    """Test _slugify function for file naming."""

    def test_simple_text(self):
        assert _slugify("Say hello to Alice") == "say_hello_to_alice"

    def test_special_characters(self):
        assert _slugify("What's 2+2?") == "what_s_2_2"

    def test_truncates_long_text(self):
        long_text = "a" * 100
        result = _slugify(long_text, max_length=50)
        assert len(result) <= 50

    def test_truncates_at_word_boundary(self):
        result = _slugify("this is a very long sentence that exceeds limit", max_length=20)
        # Should truncate at underscore boundary
        assert "_" not in result[-1:]  # Doesn't end with underscore

    def test_empty_returns_default(self):
        assert _slugify("!!!") == "default"
        assert _slugify("") == "default"

    def test_strips_underscores(self):
        assert _slugify("  hello  ") == "hello"


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
            'name': 'greet',
            'args': {'name': 'Alice'}
        }
        result = logger._format_tool_call(trace_entry)
        assert result == "greet(name='Alice')"

    def test_format_tool_call_multiple_args(self):
        """Test formatting tool call with multiple args."""
        logger = Logger("test-agent", log=False)
        trace_entry = {
            'name': 'write_file',
            'args': {'path': 'test.py', 'content': 'print("hello")'}
        }
        result = logger._format_tool_call(trace_entry)
        assert result == "write_file(path='test.py', content='print(\"hello\")')"

    def test_format_tool_call_truncates_long_string(self):
        """Test that long string values are truncated to 50 chars."""
        logger = Logger("test-agent", log=False)
        long_content = "x" * 100
        trace_entry = {
            'name': 'write',
            'args': {'content': long_content}
        }
        result = logger._format_tool_call(trace_entry)
        assert "x" * 50 + "..." in result
        assert "x" * 51 not in result

    def test_format_tool_call_non_string_value(self):
        """Test formatting tool call with non-string values."""
        logger = Logger("test-agent", log=False)
        trace_entry = {
            'name': 'search',
            'args': {'limit': 10, 'include_all': True}
        }
        result = logger._format_tool_call(trace_entry)
        assert "limit=10" in result
        assert "include_all=True" in result

    def test_format_tool_call_empty_args(self):
        """Test formatting tool call with no arguments."""
        logger = Logger("test-agent", log=False)
        trace_entry = {
            'name': 'get_time',
            'args': {}
        }
        result = logger._format_tool_call(trace_entry)
        assert result == "get_time()"


class TestEvalLogging:
    """Test YAML eval logging with new format."""

    def test_start_session_initializes_state(self, tmp_path, monkeypatch):
        """Test start_session initializes state but doesn't create file yet."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        # File not created until log_turn (lazy init)
        assert logger.eval_file is None
        assert logger.eval_data is None

    def test_start_session_disabled_when_log_false(self, tmp_path, monkeypatch):
        """Test start_session does nothing when log=False."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", log=False)
        logger.start_session()

        assert logger.eval_file is None
        assert logger.eval_data is None

    def _create_mock_session(self, tool_calls=None, turn=1):
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
                    'type': 'tool_result',
                    'name': tc['name'],
                    'args': tc.get('args', {})
                })

        return {
            'trace': trace,
            'turn': turn,
            'messages': [
                {'role': 'system', 'content': 'You are helpful'},
                {'role': 'user', 'content': 'test query'},
                {'role': 'assistant', 'content': 'test result'}
            ]
        }

    def test_log_turn_creates_file_from_input(self, tmp_path, monkeypatch):
        """Test log_turn creates eval file named from first input."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        session = self._create_mock_session()
        logger.log_turn("Say hello to Alice", "Hello, Alice!", 1000, session, "gpt-4")

        # File should be created with slugified input name
        assert logger.eval_file == Path(".co/evals/say_hello_to_alice.yaml")
        assert logger.eval_file.exists()

    def test_log_turn_creates_run_yaml_for_messages(self, tmp_path, monkeypatch):
        """Test log_turn creates run YAML file with messages."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        session = self._create_mock_session()
        logger.log_turn("Say hello", "Hello!", 100, session, "gpt-4")

        # Run YAML file should exist
        run_file = Path(".co/evals/say_hello/run_1.yaml")
        assert run_file.exists()

        # Verify content
        with open(run_file) as f:
            data = yaml.safe_load(f)

        # Check metadata fields
        assert data['model'] == 'gpt-4'
        assert data['system_prompt'] == 'You are helpful'
        assert 'messages' in data

        # Messages should be parseable JSON
        messages = json.loads(data['messages'])
        assert len(messages) == 3  # system, user, assistant

    def test_log_turn_writes_yaml(self, tmp_path, monkeypatch):
        """Test log_turn writes turn data to YAML file."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        session = self._create_mock_session([{'name': 'search', 'args': {'query': 'test'}}])
        logger.log_turn("test query", "test result", 1000, session, "gpt-4")

        # Verify content
        with open(logger.eval_file) as f:
            data = yaml.safe_load(f)

        assert data["name"] == "test_query"
        assert data["runs"] == 1
        assert data["model"] == "gpt-4"
        assert len(data["turns"]) == 1
        assert data["turns"][0]["input"] == "test query"
        assert data["turns"][0]["output"] == "test result"
        assert data["turns"][0]["run"] == 1
        # Metadata is now in compact JSON format
        meta = json.loads(data["turns"][0]["meta"])
        assert meta["duration_ms"] == 1000
        assert meta["tokens"] == 150
        assert meta["cost"] == 0.01

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

        with open(logger.eval_file) as f:
            data = yaml.safe_load(f)

        tools = data["turns"][0]["tools_called"]
        assert "greet(name='Alice')" in tools
        assert "write(path='test.txt')" in tools

    def test_log_multiple_turns(self, tmp_path, monkeypatch):
        """Test logging multiple turns to same session."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        session1 = self._create_mock_session(turn=1)
        session2 = self._create_mock_session(turn=2)

        logger.log_turn("turn 1", "result 1", 100, session1, "gpt-4")
        logger.log_turn("turn 2", "result 2", 200, session2, "gpt-4")

        with open(logger.eval_file) as f:
            data = yaml.safe_load(f)

        assert len(data["turns"]) == 2
        assert data["turns"][0]["input"] == "turn 1"
        assert data["turns"][1]["input"] == "turn 2"

    def test_log_turn_without_start_session(self, tmp_path, monkeypatch):
        """Test log_turn does nothing if enable_sessions is False."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", log=False)

        session = self._create_mock_session()
        # Should not raise error
        logger.log_turn("test", "result", 100, session, "gpt-4")

        assert logger.eval_file is None


class TestRunTracking:
    """Test run tracking for same input sequences."""

    def _create_mock_session(self, turn=1):
        """Helper to create mock session dict."""
        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cost = 0.01

        return {
            'trace': [{'type': 'llm_call', 'usage': mock_usage}],
            'turn': turn,
            'messages': [
                {'role': 'system', 'content': 'You are helpful'},
                {'role': 'user', 'content': 'hello'},
                {'role': 'assistant', 'content': 'Hi there!'}
            ]
        }

    def test_same_input_increments_run(self, tmp_path, monkeypatch):
        """Test same input sequence increments run counter."""
        monkeypatch.chdir(tmp_path)

        # First run
        logger1 = Logger("test-agent", quiet=True)
        logger1.start_session()
        logger1.log_turn("hello", "Hi!", 100, self._create_mock_session(), "gpt-4")

        # Second run (same input)
        logger2 = Logger("test-agent", quiet=True)
        logger2.start_session()
        logger2.log_turn("hello", "Hello!", 150, self._create_mock_session(), "gpt-4")

        # Verify runs counter
        with open(Path(".co/evals/hello.yaml")) as f:
            data = yaml.safe_load(f)

        assert data["runs"] == 2

    def test_history_tracking(self, tmp_path, monkeypatch):
        """Test previous runs are moved to history."""
        monkeypatch.chdir(tmp_path)

        # First run
        logger1 = Logger("test-agent", quiet=True)
        logger1.start_session()
        logger1.log_turn("hello", "First response", 100, self._create_mock_session(), "gpt-4")

        # Second run
        logger2 = Logger("test-agent", quiet=True)
        logger2.start_session()
        logger2.log_turn("hello", "Second response", 150, self._create_mock_session(), "gpt-4")

        with open(Path(".co/evals/hello.yaml")) as f:
            data = yaml.safe_load(f)

        turn = data["turns"][0]
        assert turn["output"] == "Second response"
        assert turn["run"] == 2
        assert len(turn["history"]) == 1
        assert turn["history"][0]["run"] == 1
        assert "meta" in turn["history"][0]

    def test_multiple_run_yaml_files(self, tmp_path, monkeypatch):
        """Test each run creates separate run YAML file."""
        monkeypatch.chdir(tmp_path)

        # First run
        logger1 = Logger("test-agent", quiet=True)
        logger1.start_session()
        logger1.log_turn("hello", "Hi!", 100, self._create_mock_session(), "gpt-4")

        # Second run
        logger2 = Logger("test-agent", quiet=True)
        logger2.start_session()
        logger2.log_turn("hello", "Hello!", 150, self._create_mock_session(), "gpt-4")

        # Both run YAML files should exist
        assert Path(".co/evals/hello/run_1.yaml").exists()
        assert Path(".co/evals/hello/run_2.yaml").exists()


class TestEvalYAMLFormat:
    """Test eval YAML format matches design spec."""

    def _create_mock_session(self):
        """Helper to create mock session dict."""
        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cost = 0.01

        return {
            'trace': [{'type': 'llm_call', 'usage': mock_usage}],
            'turn': 1,
            'messages': [
                {'role': 'system', 'content': 'System prompt'},
                {'role': 'user', 'content': 'test query'},
                {'role': 'assistant', 'content': 'test result'}
            ]
        }

    def test_yaml_field_order(self, tmp_path, monkeypatch):
        """Test YAML fields are in correct order."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session("You are helpful")
        logger.log_turn("test", "result", 100, self._create_mock_session(), "gpt-4")

        # Read raw file to check order
        with open(logger.eval_file) as f:
            content = f.read()

        # Check order by finding positions
        name_pos = content.find("name:")
        created_pos = content.find("created:")
        runs_pos = content.find("runs:")
        model_pos = content.find("model:")
        turns_pos = content.find("turns:")

        assert name_pos < created_pos < runs_pos < model_pos < turns_pos


class TestLoadMethods:
    """Test load_messages and load_session methods."""

    def _setup_eval_file(self, tmp_path, monkeypatch):
        """Helper to set up an eval file with test data."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session("You are a helpful assistant")

        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cost = 0.01

        session = {
            'trace': [{'type': 'llm_call', 'usage': mock_usage}],
            'turn': 1,
            'messages': [
                {'role': 'system', 'content': 'You are a helpful assistant'},
                {'role': 'user', 'content': 'hello'},
                {'role': 'assistant', 'content': 'Hi there!'}
            ]
        }
        logger.log_turn("hello", "Hi there!", 100, session, "gpt-4")
        return logger

    def test_load_messages_from_jsonl(self, tmp_path, monkeypatch):
        """Test load_messages reads from JSONL file."""
        logger = self._setup_eval_file(tmp_path, monkeypatch)

        messages = logger.load_messages()

        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"

    def test_load_messages_specific_run(self, tmp_path, monkeypatch):
        """Test load_messages can load specific run."""
        monkeypatch.chdir(tmp_path)

        # First run
        logger1 = Logger("test-agent", quiet=True)
        logger1.start_session()
        session1 = {
            'trace': [{'type': 'llm_call', 'usage': Mock(input_tokens=100, output_tokens=50, cost=0.01)}],
            'turn': 1,
            'messages': [{'role': 'user', 'content': 'run 1'}]
        }
        logger1.log_turn("hello", "response 1", 100, session1, "gpt-4")

        # Second run
        logger2 = Logger("test-agent", quiet=True)
        logger2.start_session()
        session2 = {
            'trace': [{'type': 'llm_call', 'usage': Mock(input_tokens=100, output_tokens=50, cost=0.01)}],
            'turn': 1,
            'messages': [{'role': 'user', 'content': 'run 2'}]
        }
        logger2.log_turn("hello", "response 2", 100, session2, "gpt-4")

        # Load run 1
        messages = logger2.load_messages(run=1)
        assert messages[0]["content"] == "run 1"

        # Load run 2
        messages = logger2.load_messages(run=2)
        assert messages[0]["content"] == "run 2"

    def test_load_messages_empty_when_no_file(self, tmp_path, monkeypatch):
        """Test load_messages returns empty list when no eval file."""
        monkeypatch.chdir(tmp_path)
        logger = Logger("test-agent", quiet=True)
        # Don't call start_session

        messages = logger.load_messages()
        assert messages == []

    def test_load_session_returns_data(self, tmp_path, monkeypatch):
        """Test load_session returns eval data dict."""
        logger = self._setup_eval_file(tmp_path, monkeypatch)

        data = logger.load_session()

        assert data["name"] == "hello"
        assert data["runs"] == 1
        assert len(data["turns"]) == 1
        assert data["turns"][0]["input"] == "hello"

    def test_load_session_returns_default_when_no_file(self, tmp_path, monkeypatch):
        """Test load_session returns default dict when no file."""
        monkeypatch.chdir(tmp_path)
        logger = Logger("test-agent", quiet=True)
        # Don't call start_session

        data = logger.load_session()

        assert data == {'turns': [], 'runs': 0}


class TestGetEvalPath:
    """Test get_eval_path method."""

    def test_returns_path_after_log_turn(self, tmp_path, monkeypatch):
        """Test get_eval_path returns path after logging."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cost = 0.01

        session = {
            'trace': [{'type': 'llm_call', 'usage': mock_usage}],
            'turn': 1,
            'messages': []
        }
        logger.log_turn("hello", "hi", 100, session, "gpt-4")

        path = logger.get_eval_path()
        # get_eval_path returns absolute path
        assert path.endswith(".co/evals/hello.yaml")

    def test_returns_none_before_log_turn(self, tmp_path, monkeypatch):
        """Test get_eval_path returns None before first log."""
        monkeypatch.chdir(tmp_path)

        logger = Logger("test-agent", quiet=True)
        logger.start_session()

        path = logger.get_eval_path()
        assert path is None
