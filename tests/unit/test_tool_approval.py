"""Unit tests for connectonion/useful_plugins/tool_approval.py

Tests cover:
- Safe tools skip approval
- Dangerous tools require approval
- Session-level approval memory
- reject_soft: skip tool, loop continues, system reminder to call ask_user with options
- reject_hard: skip tool + remaining batch, loop stops
- batch_remaining: approval_needed includes upcoming tools
- No IO = skip (not web mode)
"""

import pytest
from unittest.mock import Mock

from connectonion.useful_plugins.tool_approval import (
    check_approval,
    tool_approval,
    SAFE_TOOLS,
    DANGEROUS_TOOLS,
    COMMAND_TOOLS,
    _is_approved_for_session,
    _save_session_approval,
    _init_approval_state,
    _get_batch_remaining,
    _get_approval_key,
    _resolve_display_name,
)


class FakeIO:
    """Fake IO for testing."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.sent = []
        self.response_index = 0

    def send(self, event):
        self.sent.append(event)

    def receive(self):
        if self.response_index < len(self.responses):
            response = self.responses[self.response_index]
            self.response_index += 1
            return response
        return {'type': 'io_closed'}


class FakeAgent:
    """Fake agent for testing."""

    def __init__(self, io=None):
        self.io = io
        self.current_session = {
            'messages': [],
            'trace': [],
            'pending_tool': None,
        }


class TestToolClassification:
    """Test tool classification (SAFE vs DANGEROUS)."""

    def test_safe_tools_defined(self):
        """SAFE_TOOLS should contain read-only tools."""
        assert 'read' in SAFE_TOOLS
        assert 'read_file' in SAFE_TOOLS
        assert 'glob' in SAFE_TOOLS
        assert 'grep' in SAFE_TOOLS

    def test_dangerous_tools_defined(self):
        """DANGEROUS_TOOLS should contain write/execute tools."""
        assert 'bash' in DANGEROUS_TOOLS
        assert 'write' in DANGEROUS_TOOLS
        assert 'edit' in DANGEROUS_TOOLS
        assert 'run_background' in DANGEROUS_TOOLS

    def test_no_overlap(self):
        """SAFE and DANGEROUS should not overlap."""
        overlap = SAFE_TOOLS & DANGEROUS_TOOLS
        assert len(overlap) == 0, f"Overlap found: {overlap}"


class TestNoIO:
    """Test behavior when no IO (not web mode)."""

    def test_no_io_skips_approval(self):
        """No IO = not web mode, should skip approval."""
        agent = FakeAgent(io=None)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'rm -rf /', 'description': 'Delete everything'}
        }

        # Should not raise (skips approval)
        check_approval(agent)


class TestSafeTools:
    """Test safe tools skip approval."""

    @pytest.mark.parametrize("tool_name", ['read', 'read_file', 'glob', 'grep', 'search', 'task'])
    def test_safe_tools_skip_approval(self, tool_name):
        """Safe tools should not trigger approval request."""
        io = FakeIO()
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': tool_name,
            'arguments': {}
        }

        check_approval(agent)

        # No approval request sent
        assert len(io.sent) == 0


class TestDangerousTools:
    """Test dangerous tools require approval."""

    def test_dangerous_tool_sends_approval_request(self):
        """Dangerous tool should send approval_needed event with command-level name and description."""
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'}
        }

        check_approval(agent)

        # Approval request was sent with "bash:npm" tool name and description
        assert len(io.sent) == 1
        assert io.sent[0]['type'] == 'approval_needed'
        assert io.sent[0]['tool'] == 'bash:npm'
        assert io.sent[0]['arguments'] == {'command': 'npm install', 'description': 'Install dependencies'}
        assert io.sent[0]['description'] == 'Install dependencies'

    def test_approved_once_continues(self):
        """Approved with scope=once should continue without saving."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'once'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'}
        }

        check_approval(agent)

        # Not saved to session
        assert 'approval' not in agent.current_session or \
               'bash' not in agent.current_session.get('approval', {}).get('approved_tools', {})

    def test_approved_session_saves_to_memory(self):
        """Approved with scope=session should save to session memory."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'session'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'}
        }

        check_approval(agent)

        # Saved to session with command-level key
        assert agent.current_session['approval']['approved_tools']['bash:npm'] == 'session'

    def test_session_approved_tool_skips_same_command(self):
        """Session approval for 'npm install' should skip 'npm run build' (same base command)."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'session'}])
        agent = FakeAgent(io=io)

        # First call - requires approval
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'}
        }
        check_approval(agent)
        assert len(io.sent) == 1

        # Second call with same base command - should skip
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm run build', 'description': 'Build the project'}
        }
        check_approval(agent)
        assert len(io.sent) == 1  # Still 1, no new request

    def test_session_approved_tool_does_not_skip_different_command(self):
        """Session approval for 'npm' should NOT skip 'git' (different command)."""
        io = FakeIO(responses=[
            {'approved': True, 'scope': 'session'},
            {'approved': True, 'scope': 'once'},
        ])
        agent = FakeAgent(io=io)

        # First call - approve npm for session
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'}
        }
        check_approval(agent)
        assert len(io.sent) == 1

        # Second call with different command - should still require approval
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'git status', 'description': 'Check git status'}
        }
        check_approval(agent)
        assert len(io.sent) == 2  # New approval request sent

    def test_non_command_tool_session_approval_uses_tool_name(self):
        """Non-command tools (write, edit) use tool name as approval key."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'session'}])
        agent = FakeAgent(io=io)

        agent.current_session['pending_tool'] = {
            'name': 'write',
            'arguments': {'file_path': 'test.txt', 'content': 'hello'}
        }
        check_approval(agent)

        # Saved with tool name only (not command-level)
        assert agent.current_session['approval']['approved_tools']['write'] == 'session'


class TestRejection:
    """Test rejection behavior."""

    def test_rejected_raises_value_error(self):
        """Rejected tool should raise ValueError."""
        io = FakeIO(responses=[{'approved': False}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'rm -rf /', 'description': 'Delete everything'}
        }

        with pytest.raises(ValueError) as exc_info:
            check_approval(agent)

        assert "User rejected tool 'bash'" in str(exc_info.value)

    def test_rejected_with_feedback_includes_feedback(self):
        """Rejected with feedback should include feedback in error."""
        io = FakeIO(responses=[{'approved': False, 'feedback': 'Use yarn instead'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'}
        }

        with pytest.raises(ValueError) as exc_info:
            check_approval(agent)

        assert "Use yarn instead" in str(exc_info.value)

    def test_io_closed_raises_value_error(self):
        """IO closed during approval should raise ValueError."""
        io = FakeIO(responses=[{'type': 'io_closed'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'}
        }

        with pytest.raises(ValueError) as exc_info:
            check_approval(agent)

        assert "Connection closed" in str(exc_info.value)


class TestRejectSoft:
    """Test reject_soft mode (skip tool, loop continues)."""

    def test_reject_soft_raises_with_ask_user_hint(self):
        """reject_soft should raise ValueError with system-reminder to call ask_user."""
        io = FakeIO(responses=[{'approved': False, 'mode': 'reject_soft'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'},
            'id': 'call_1',
        }

        with pytest.raises(ValueError) as exc_info:
            check_approval(agent)

        msg = str(exc_info.value)
        assert "User rejected tool 'bash'" in msg
        assert "<system-reminder>" in msg
        assert "ask_user" in msg
        assert "options" in msg
        assert "Do not retry" in msg

    def test_reject_soft_does_not_set_hard_flag(self):
        """reject_soft should NOT set tool_rejected_hard in session."""
        io = FakeIO(responses=[{'approved': False, 'mode': 'reject_soft'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'},
            'id': 'call_1',
        }

        with pytest.raises(ValueError):
            check_approval(agent)

        assert 'tool_rejected_hard' not in agent.current_session

    def test_reject_soft_with_feedback(self):
        """reject_soft with feedback should include feedback in error."""
        io = FakeIO(responses=[{'approved': False, 'mode': 'reject_soft', 'feedback': 'Use yarn'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'},
            'id': 'call_1',
        }

        with pytest.raises(ValueError) as exc_info:
            check_approval(agent)

        assert "Use yarn" in str(exc_info.value)


class TestRejectHard:
    """Test reject_hard mode (stop batch and loop)."""

    def test_reject_hard_sets_session_flag(self):
        """reject_hard should set tool_rejected_hard in session."""
        io = FakeIO(responses=[{'approved': False, 'mode': 'reject_hard'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'rm -rf /', 'description': 'Delete everything'},
            'id': 'call_1',
        }

        with pytest.raises(ValueError):
            check_approval(agent)

        assert 'tool_rejected_hard' in agent.current_session

    def test_reject_hard_is_default_mode(self):
        """No mode field should default to reject_hard."""
        io = FakeIO(responses=[{'approved': False}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'rm -rf /', 'description': 'Delete everything'},
            'id': 'call_1',
        }

        with pytest.raises(ValueError):
            check_approval(agent)

        assert 'tool_rejected_hard' in agent.current_session

    def test_reject_hard_blocks_subsequent_tools(self):
        """After reject_hard, next tool in batch should auto-reject."""
        agent = FakeAgent(io=FakeIO())
        agent.current_session['tool_rejected_hard'] = "User rejected."
        agent.current_session['pending_tool'] = {
            'name': 'write',
            'arguments': {'file_path': 'test.txt'},
            'id': 'call_2',
        }

        with pytest.raises(ValueError) as exc_info:
            check_approval(agent)

        assert "rejected this batch" in str(exc_info.value)


class TestBatchRemaining:
    """Test batch_remaining in approval_needed message."""

    def test_batch_remaining_included_when_more_tools(self):
        """approval_needed should include batch_remaining with resolved display names."""
        import json
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io)
        # Simulate assistant message with 3 tool_calls (added by tool_executor before loop)
        agent.current_session['messages'] = [{
            'role': 'assistant',
            'tool_calls': [
                {'id': 'call_1', 'type': 'function', 'function': {'name': 'bash', 'arguments': json.dumps({'command': 'npm install', 'description': 'Install dependencies'})}},
                {'id': 'call_2', 'type': 'function', 'function': {'name': 'write', 'arguments': json.dumps({'file_path': 'config.json'})}},
                {'id': 'call_3', 'type': 'function', 'function': {'name': 'bash', 'arguments': json.dumps({'command': 'npm build', 'description': 'Build project'})}},
            ]
        }]
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'},
            'id': 'call_1',
        }

        check_approval(agent)

        sent = io.sent[0]
        assert sent['type'] == 'approval_needed'
        assert sent['tool'] == 'bash:npm'
        assert 'batch_remaining' in sent
        assert len(sent['batch_remaining']) == 2
        assert sent['batch_remaining'][0]['tool'] == 'write'
        assert sent['batch_remaining'][1]['tool'] == 'bash:npm'

    def test_no_batch_remaining_for_last_tool(self):
        """approval_needed should NOT include batch_remaining for last tool in batch."""
        import json
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io)
        agent.current_session['messages'] = [{
            'role': 'assistant',
            'tool_calls': [
                {'id': 'call_1', 'type': 'function', 'function': {'name': 'bash', 'arguments': json.dumps({'command': 'npm install', 'description': 'Install dependencies'})}},
            ]
        }]
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'},
            'id': 'call_1',
        }

        check_approval(agent)

        sent = io.sent[0]
        assert 'batch_remaining' not in sent

    def test_get_batch_remaining_helper(self):
        """_get_batch_remaining should extract remaining tools with resolved names."""
        import json
        agent = FakeAgent()
        agent.current_session['messages'] = [{
            'role': 'assistant',
            'tool_calls': [
                {'id': 'c1', 'type': 'function', 'function': {'name': 'bash', 'arguments': json.dumps({'command': 'ls /tmp'})}},
                {'id': 'c2', 'type': 'function', 'function': {'name': 'write', 'arguments': '{}'}},
                {'id': 'c3', 'type': 'function', 'function': {'name': 'bash', 'arguments': json.dumps({'command': 'git status'})}},
            ]
        }]

        remaining = _get_batch_remaining(agent, 'c1')
        assert len(remaining) == 2
        assert remaining[0]['tool'] == 'write'
        assert remaining[1]['tool'] == 'bash:git'

        remaining = _get_batch_remaining(agent, 'c3')
        assert len(remaining) == 0


class TestDescription:
    """Test description field in approval messages."""

    def test_description_included_in_approval_message(self):
        """approval_needed should include description from tool args."""
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm run build', 'description': 'Build the project'},
        }

        check_approval(agent)

        assert io.sent[0]['description'] == 'Build the project'

    def test_description_empty_when_not_provided(self):
        """approval_needed should have empty description when not in args."""
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'ls'},
        }

        check_approval(agent)

        assert io.sent[0]['description'] == ''


class TestApprovalKey:
    """Test _get_approval_key for command-level granularity."""

    def test_bash_uses_command_name(self):
        """Bash tools use 'bash:command' as approval key."""
        assert _get_approval_key('bash', {'command': 'ls /tmp'}) == 'bash:ls'
        assert _get_approval_key('bash', {'command': 'npm install'}) == 'bash:npm'
        assert _get_approval_key('bash', {'command': 'git status'}) == 'bash:git'

    def test_all_command_tools_use_command_name(self):
        """All COMMAND_TOOLS use command-level keys."""
        for tool in COMMAND_TOOLS:
            key = _get_approval_key(tool, {'command': 'ls -la'})
            assert key == f'{tool}:ls'

    def test_non_command_tool_uses_tool_name(self):
        """Non-command tools use tool name as key."""
        assert _get_approval_key('write', {'file_path': 'test.txt'}) == 'write'
        assert _get_approval_key('edit', {'file_path': 'test.txt'}) == 'edit'

    def test_empty_command_falls_back_to_tool_name(self):
        """Empty command falls back to tool name."""
        assert _get_approval_key('bash', {'command': ''}) == 'bash'
        assert _get_approval_key('bash', {}) == 'bash'


class TestUnknownTools:
    """Test unknown tools behavior."""

    def test_unknown_tool_skips_approval(self):
        """Unknown tools (not in SAFE or DANGEROUS) should skip approval."""
        io = FakeIO()
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'my_custom_tool',
            'arguments': {}
        }

        check_approval(agent)

        # No approval request sent
        assert len(io.sent) == 0


class TestSessionState:
    """Test session state helpers."""

    def test_init_approval_state(self):
        """_init_approval_state creates proper structure."""
        session = {}
        _init_approval_state(session)

        assert 'approval' in session
        assert 'approved_tools' in session['approval']

    def test_is_approved_for_session(self):
        """_is_approved_for_session checks correctly."""
        session = {
            'approval': {
                'approved_tools': {'bash': 'session'}
            }
        }

        assert _is_approved_for_session(session, 'bash') is True
        assert _is_approved_for_session(session, 'write') is False

    def test_save_session_approval(self):
        """_save_session_approval saves correctly."""
        session = {}
        _save_session_approval(session, 'bash')

        assert session['approval']['approved_tools']['bash'] == 'session'


class TestPluginExport:
    """Test plugin is properly exported."""

    def test_tool_approval_is_list(self):
        """tool_approval should be a list of handlers."""
        assert isinstance(tool_approval, list)
        assert len(tool_approval) == 1

    def test_handler_has_event_type(self):
        """Handler should have correct event type."""
        handler = tool_approval[0]
        assert hasattr(handler, '_event_type')
        assert handler._event_type == 'before_each_tool'

    def test_plugin_integrates_with_agent(self):
        """Plugin should integrate with Agent without errors."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

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
            plugins=[tool_approval],
            log=False,
        )

        assert 'before_each_tool' in agent.events
