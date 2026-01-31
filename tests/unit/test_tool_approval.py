"""Unit tests for connectonion/useful_plugins/tool_approval.py

Tests cover:
- Safe tools skip approval
- Dangerous tools require approval
- Session-level approval memory
- Rejection stops execution with feedback
- No IO = skip (not web mode)
"""

import pytest
from unittest.mock import Mock

from connectonion.useful_plugins.tool_approval import (
    check_approval,
    tool_approval,
    SAFE_TOOLS,
    DANGEROUS_TOOLS,
    _is_approved_for_session,
    _save_session_approval,
    _init_approval_state,
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
            'arguments': {'command': 'rm -rf /'}
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
        """Dangerous tool should send approval_needed event."""
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install'}
        }

        check_approval(agent)

        # Approval request was sent
        assert len(io.sent) == 1
        assert io.sent[0]['type'] == 'approval_needed'
        assert io.sent[0]['tool'] == 'bash'
        assert io.sent[0]['arguments'] == {'command': 'npm install'}

    def test_approved_once_continues(self):
        """Approved with scope=once should continue without saving."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'once'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install'}
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
            'arguments': {'command': 'npm install'}
        }

        check_approval(agent)

        # Saved to session
        assert agent.current_session['approval']['approved_tools']['bash'] == 'session'

    def test_session_approved_tool_skips_second_approval(self):
        """Tool approved for session should skip approval on second call."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'session'}])
        agent = FakeAgent(io=io)

        # First call - requires approval
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install'}
        }
        check_approval(agent)
        assert len(io.sent) == 1

        # Second call - should skip (already approved)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm run build'}
        }
        check_approval(agent)
        assert len(io.sent) == 1  # Still 1, no new request


class TestRejection:
    """Test rejection behavior."""

    def test_rejected_raises_value_error(self):
        """Rejected tool should raise ValueError."""
        io = FakeIO(responses=[{'approved': False}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'rm -rf /'}
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
            'arguments': {'command': 'npm install'}
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
            'arguments': {'command': 'npm install'}
        }

        with pytest.raises(ValueError) as exc_info:
            check_approval(agent)

        assert "Connection closed" in str(exc_info.value)


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
