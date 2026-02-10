"""Unit tests for connectonion/useful_plugins/shell_approval.py

Tests cover:
- _is_safe: safe command pattern matching
- _check_approval: approval workflow for shell commands
- Plugin registration with correct events
"""

import pytest
import importlib
from unittest.mock import Mock, patch

# Import the module directly to avoid __init__.py shadowing
shell_approval_module = importlib.import_module('connectonion.useful_plugins.shell_approval')
_is_safe = shell_approval_module._is_safe
_check_approval = shell_approval_module._check_approval
shell_approval = shell_approval_module.shell_approval
SAFE_PATTERNS = shell_approval_module.SAFE_PATTERNS


class FakeAgent:
    """Fake agent for testing plugins."""

    def __init__(self):
        self.current_session = {
            'messages': [],
            'trace': [],
            'pending_tool': None,
        }
        self.logger = Mock()


class TestIsSafe:
    """Tests for _is_safe function - safe command detection."""

    @pytest.mark.parametrize("command", [
        "ls",
        "ls -la",
        "ls /home/user",
        "ll",
        "cat file.txt",
        "head -n 10 file.txt",
        "tail -f log.txt",
        "grep pattern file.txt",
        "rg pattern",
        "find . -name '*.py'",
        "fd pattern",
        "which python",
        "whereis bash",
        "type ls",
        "file image.png",
        "stat file.txt",
        "wc -l file.txt",
        "pwd",
        "echo hello",
        "printf 'test'",
        "date",
        "whoami",
        "id",
        "env",
        "printenv",
        "uname -a",
        "hostname",
        "df -h",
        "du -sh .",
        "free -h",
        "ps aux",
        "top -n 1",
        "htop",
        "tree",
        "git status",
        "git log --oneline",
        "git diff HEAD",
        "git show HEAD",
        "git branch",
        "git remote -v",
        "git tag",
        "npm list",
        "npm ls",
        "pip list",
        "pip show requests",
        "python --version",
        "node --version",
        "cargo --version",
    ])
    def test_safe_commands_are_detected(self, command):
        """Test that all safe commands return True."""
        assert _is_safe(command) is True

    @pytest.mark.parametrize("command", [
        "rm file.txt",
        "rm -rf /",
        "sudo apt install",
        "chmod 777 file",
        "chown user file",
        "mv file1 file2",
        "cp file1 file2",
        "mkdir new_dir",
        "rmdir old_dir",
        "touch newfile",
        "wget http://example.com",
        "curl -X POST http://api.com",
        "git push",
        "git commit -m 'message'",
        "git checkout branch",
        "npm install",
        "pip install requests",
        "python script.py",
        "node script.js",
        "bash script.sh",
        "sh script.sh",
        "./script.sh",
    ])
    def test_dangerous_commands_are_not_safe(self, command):
        """Test that dangerous commands return False."""
        assert _is_safe(command) is False

    def test_empty_command_is_not_safe(self):
        """Test that empty command returns False."""
        assert _is_safe("") is False
        assert _is_safe("   ") is False

    def test_whitespace_stripping(self):
        """Test that leading/trailing whitespace is handled."""
        assert _is_safe("  ls -la  ") is True
        assert _is_safe("\tgit status\n") is True


class TestCheckApproval:
    """Tests for _check_approval function - approval workflow."""

    def test_no_pending_tool_does_nothing(self):
        """Test that no pending tool means no action."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = None

        # Should not raise
        _check_approval(agent)

    def test_non_shell_tool_skipped(self):
        """Test that non-shell tools are skipped."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'search',
            'arguments': {'query': 'test'}
        }

        # Should not raise
        _check_approval(agent)

    @pytest.mark.parametrize("tool_name", ['bash', 'shell', 'run'])
    def test_shell_tool_names_are_checked(self, tool_name):
        """Test that bash, shell, and run tool names are checked."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': tool_name,
            'arguments': {'command': 'ls -la'}  # safe command
        }

        # Safe command should pass without interaction
        _check_approval(agent)

    def test_safe_command_no_approval_needed(self):
        """Test that safe commands don't trigger approval."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'shell',
            'arguments': {'command': 'git status'}
        }

        # Should not raise or require approval
        _check_approval(agent)

    def test_auto_approved_command_skips_approval(self):
        """Test that previously auto-approved commands skip approval."""
        agent = FakeAgent()
        agent.current_session['shell_approved_cmds'] = {'npm'}
        agent.current_session['pending_tool'] = {
            'name': 'shell',
            'arguments': {'command': 'npm install'}
        }

        # Should not raise because 'npm' was auto-approved
        _check_approval(agent)

    @patch.object(shell_approval_module, 'pick')
    @patch.object(shell_approval_module, '_console')
    def test_dangerous_command_shows_approval_dialog(self, mock_console, mock_pick):
        """Test that dangerous commands trigger approval dialog."""
        mock_pick.return_value = "Yes, execute"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'shell',
            'arguments': {'command': 'rm -rf /tmp/test'}
        }

        # Should call pick for approval
        _check_approval(agent)
        mock_pick.assert_called_once()

    @patch.object(shell_approval_module, 'pick')
    @patch.object(shell_approval_module, '_console')
    def test_approval_yes_executes_command(self, mock_console, mock_pick):
        """Test that 'Yes, execute' allows command to run."""
        mock_pick.return_value = "Yes, execute"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'shell',
            'arguments': {'command': 'npm install'}
        }

        # Should not raise
        _check_approval(agent)

    @patch.object(shell_approval_module, 'pick')
    @patch.object(shell_approval_module, '_console')
    def test_auto_approve_adds_to_session(self, mock_console, mock_pick):
        """Test that auto-approve adds command to session set."""
        mock_pick.return_value = "Auto approve 'npm' in this session"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'shell',
            'arguments': {'command': 'npm install'}
        }

        _check_approval(agent)

        assert 'shell_approved_cmds' in agent.current_session
        assert 'npm' in agent.current_session['shell_approved_cmds']

    @patch.object(shell_approval_module, 'pick')
    @patch.object(shell_approval_module, '_console')
    @patch('builtins.input', return_value='use pip instead')
    def test_rejection_raises_value_error(self, mock_input, mock_console, mock_pick):
        """Test that rejection raises ValueError with feedback."""
        mock_pick.return_value = "No, tell agent what I want"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'shell',
            'arguments': {'command': 'npm install'}
        }

        with pytest.raises(ValueError) as exc_info:
            _check_approval(agent)

        assert "Feedback: use pip instead" in str(exc_info.value)


class TestShellApprovalPlugin:
    """Tests for shell_approval plugin bundle."""

    def test_shell_approval_contains_one_handler(self):
        """Test that shell_approval plugin has one handler."""
        assert len(shell_approval) == 1

    def test_handler_has_correct_event_type(self):
        """Test that handler is registered for before_each_tool event."""
        handler = shell_approval[0]
        assert hasattr(handler, '_event_type')
        assert handler._event_type == 'before_each_tool'

    def test_plugin_integrates_with_agent(self):
        """Test that plugin can be registered with agent."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        # Create mock LLM
        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="Test response",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        # Should not raise
        agent = Agent(
            "test",
            llm=mock_llm,
            plugins=[shell_approval],
            log=False,
        )

        # Verify event is registered
        assert 'before_each_tool' in agent.events


class TestSafePatterns:
    """Tests for SAFE_PATTERNS constant."""

    def test_safe_patterns_is_list(self):
        """Test that SAFE_PATTERNS is a list."""
        assert isinstance(SAFE_PATTERNS, list)

    def test_safe_patterns_not_empty(self):
        """Test that SAFE_PATTERNS has patterns."""
        assert len(SAFE_PATTERNS) > 0

    def test_all_patterns_are_valid_regex(self):
        """Test that all patterns are valid regex."""
        import re
        for pattern in SAFE_PATTERNS:
            # Should not raise
            re.compile(pattern)

    def test_patterns_use_word_boundaries(self):
        """Test that patterns use word boundaries to prevent partial matches."""
        # Most patterns should end with \b to prevent 'cat' matching 'caterpillar'
        word_boundary_patterns = [p for p in SAFE_PATTERNS if p.endswith(r'\b')]
        assert len(word_boundary_patterns) > 20  # Most should have boundaries
