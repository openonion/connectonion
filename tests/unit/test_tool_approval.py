"""Unit tests for connectonion/useful_plugins/tool_approval.py

Tests cover:
- Explicitly permitted safe tools skip approval
- Dangerous tools require approval
- Unclassified tools require approval when live IO is present
- Session-level approval memory
- reject_soft: skip tool, loop continues, system reminder to call ask_user with options
- reject_hard: skip tool + remaining batch, loop stops
- batch_remaining: approval_needed includes upcoming tools
- No IO = skip (not web mode)

LLM-Note: Tests for tool approval

What it tests:
- Tool Approval functionality

Components under test:
- Module: tool_approval
"""

from unittest.mock import Mock

import pytest

from connectonion.useful_plugins.tool_approval import (
    VALID_PERMISSION_MODES,
    check_approval,
    poll_interrupt,
    poll_mode_changes,
    tool_approval,
)
from connectonion.useful_plugins.tool_approval.approval import (
    _get_approval_key,
    _get_batch_remaining,
    _init_approval_state,
    _is_approved_for_session,
    _save_session_approval,
)
from connectonion.useful_plugins.tool_approval.constants import (
    COMMAND_TOOLS,
    DANGEROUS_TOOLS,
)


class FakeIO:
    """Fake IO for testing."""

    def __init__(self, responses=None, pending_signals=None):
        self.responses = responses or []
        self.pending_signals = pending_signals or []
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

    def receive_all(self, msg_type=None):
        """Get all pending signals, optionally filtered by type."""
        if msg_type is None:
            result = self.pending_signals[:]
            self.pending_signals = []
            return result
        result = [m for m in self.pending_signals if m.get('type') == msg_type]
        self.pending_signals = [m for m in self.pending_signals if m.get('type') != msg_type]
        return result


class FakeStorage:
    """Fake storage for testing."""

    def __init__(self):
        self.checkpoints = []

    def checkpoint(self, session):
        self.checkpoints.append(session.copy())


class FakeAgent:
    """Fake agent for testing."""

    def __init__(self, io=None, storage=None):
        self.io = io
        self.storage = storage
        self.current_session = {
            'messages': [],
            'trace': [],
            'pending_tool': None,
        }


@pytest.fixture(autouse=True)
def _isolate_project_lookup(tmp_path, monkeypatch):
    """Keep permission tests independent from any parent project config."""

    monkeypatch.chdir(tmp_path)


class TestToolClassification:
    """Test tool classification - DANGEROUS tools need approval."""

    def test_public_modes_stay_small(self):
        assert VALID_PERMISSION_MODES == {'read-only', 'auto'}

    def test_dangerous_tools_defined(self):
        """DANGEROUS_TOOLS should contain write/execute tools."""
        assert 'bash' in DANGEROUS_TOOLS
        assert 'write' in DANGEROUS_TOOLS
        assert 'edit' in DANGEROUS_TOOLS
        assert 'run_background' in DANGEROUS_TOOLS

    def test_command_tools_defined(self):
        """COMMAND_TOOLS should contain bash-like tools."""
        assert 'bash' in COMMAND_TOOLS
        assert 'shell' in COMMAND_TOOLS
        assert 'run' in COMMAND_TOOLS


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
        """Template-style safe permissions should not trigger approval."""
        io = FakeIO()
        agent = FakeAgent(io=io)
        agent.current_session['permissions'] = {
            tool_name: {
                'allowed': True,
                'source': 'safe',
                'reason': 'read-only operation',
            }
        }
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

        # Approval request was sent with tool name (no more :npm suffix)
        assert len(io.sent) == 1
        assert io.sent[0]['type'] == 'approval_needed'
        assert io.sent[0]['tool'] == 'bash'  # Changed: no more :npm suffix
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

        # Saved to permissions (tool-level, no 'when' field for user approvals)
        assert 'bash' in agent.current_session['permissions']
        assert agent.current_session['permissions']['bash']['source'] == 'user'
        assert agent.current_session['permissions']['bash']['allowed'] is True
        assert agent.current_session['permissions']['bash']['expires'] == {'type': 'session_end'}

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

    def test_session_approved_bash_approves_all_commands(self):
        """Session approval for 'bash' approves ALL bash commands."""
        io = FakeIO(responses=[
            {'approved': True, 'scope': 'session'},
        ])
        agent = FakeAgent(io=io)

        # First call - approve bash for session
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'}
        }
        check_approval(agent)
        assert len(io.sent) == 1

        # Second call with different command - should NOT require approval
        # (bash was approved for session, which covers all bash commands)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'git status', 'description': 'Check git status'}
        }
        check_approval(agent)
        assert len(io.sent) == 1  # No new approval request

    def test_non_command_tool_session_approval_uses_tool_name(self):
        """Non-command tools (write, edit) use tool name as approval key."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'session'}])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'read-only'

        agent.current_session['pending_tool'] = {
            'name': 'write',
            'arguments': {'file_path': 'test.txt', 'content': 'hello'}
        }
        check_approval(agent)

        # Saved with tool name only (not command-level) in unified permissions
        assert 'write' in agent.current_session['permissions']
        assert agent.current_session['permissions']['write']['source'] == 'user'


class TestCheckpoint:
    """Test checkpoint before blocking."""

    def test_checkpoint_called_before_approval_request(self):
        """checkpoint() is called before sending approval_needed."""
        storage = FakeStorage()
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io, storage=storage)
        agent.current_session['session_id'] = 'test-session'
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install'},
        }

        check_approval(agent)

        assert len(storage.checkpoints) == 1
        assert storage.checkpoints[0]['session_id'] == 'test-session'

    def test_no_checkpoint_without_storage(self):
        """No error when storage is None."""
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io, storage=None)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install'},
        }

        # Should not raise
        check_approval(agent)

    def test_no_checkpoint_for_explicitly_permitted_tools(self):
        """checkpoint() is not called for explicitly permitted tools."""
        storage = FakeStorage()
        io = FakeIO()
        agent = FakeAgent(io=io, storage=storage)
        agent.current_session['permissions'] = {
            'read': {
                'allowed': True,
                'source': 'safe',
                'reason': 'read-only operation',
            }
        }
        agent.current_session['pending_tool'] = {
            'name': 'read',
            'arguments': {},
        }

        check_approval(agent)

        assert len(storage.checkpoints) == 0


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

    def test_interrupt_sets_stop_signal_while_waiting_for_approval(self):
        from connectonion.core.interrupt import UserInterrupt

        io = FakeIO(responses=[{'type': 'INTERRUPT'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'rm output.txt'},
            'id': 'call_1',
        }

        with pytest.raises(UserInterrupt):
            check_approval(agent)

        assert agent.current_session['stop_signal'] == 'Interrupted by user'


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
        """reject_soft should NOT set stop_signal in session."""
        io = FakeIO(responses=[{'approved': False, 'mode': 'reject_soft'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'npm install', 'description': 'Install dependencies'},
            'id': 'call_1',
        }

        with pytest.raises(ValueError):
            check_approval(agent)

        assert 'stop_signal' not in agent.current_session

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
        """reject_hard should set stop_signal in session."""
        io = FakeIO(responses=[{'approved': False, 'mode': 'reject_hard'}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = {
            'name': 'bash',
            'arguments': {'command': 'rm -rf /', 'description': 'Delete everything'},
            'id': 'call_1',
        }

        with pytest.raises(ValueError):
            check_approval(agent)

        assert 'stop_signal' in agent.current_session

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

        assert 'stop_signal' in agent.current_session

    def test_reject_hard_blocks_subsequent_tools(self):
        """After reject_hard, next tool in batch should auto-reject."""
        agent = FakeAgent(io=FakeIO())
        agent.current_session['stop_signal'] = "User rejected."
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
        assert sent['tool'] == 'bash'  # No more :npm suffix
        assert 'batch_remaining' in sent
        assert len(sent['batch_remaining']) == 2
        assert sent['batch_remaining'][0]['tool'] == 'write'
        assert sent['batch_remaining'][1]['tool'] == 'bash'  # No more :npm suffix

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
        assert remaining[1]['tool'] == 'bash'  # No more :git suffix

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

    def test_bash_uses_tool_name_only(self):
        """Bash tools return just tool name (command stored in 'when' field)."""
        assert _get_approval_key('bash', {'command': 'ls /tmp'}) == 'bash'
        assert _get_approval_key('bash', {'command': 'npm install'}) == 'bash'
        assert _get_approval_key('bash', {'command': 'git status'}) == 'bash'

    def test_all_command_tools_use_tool_name_only(self):
        """All COMMAND_TOOLS return just tool name."""
        for tool in COMMAND_TOOLS:
            key = _get_approval_key(tool, {'command': 'ls -la'})
            assert key == tool  # Just tool name

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

    @pytest.mark.parametrize("mode", ['read-only', 'auto'])
    def test_unknown_tool_requests_approval(self, mode):
        """Live unclassified tools require explicit approval in both modes."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'once'}])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = mode
        agent.current_session['pending_tool'] = {
            'name': 'my_custom_tool',
            'arguments': {'value': 'example'},
        }

        check_approval(agent)

        assert len(io.sent) == 1
        assert io.sent[0]['type'] == 'approval_needed'
        assert io.sent[0]['tool'] == 'my_custom_tool'
        assert io.sent[0]['arguments'] == {'value': 'example'}
        assert io.sent[0]['description'] == ''

    def test_explicit_permission_allows_an_unknown_tool(self):
        """The allowlist stays extensible for custom and plugin tools."""
        io = FakeIO()
        agent = FakeAgent(io=io)
        agent.current_session['permissions'] = {
            'my_custom_tool': {
                'allowed': True,
                'source': 'config',
                'reason': 'operator configured',
            }
        }
        agent.current_session['pending_tool'] = {
            'name': 'my_custom_tool',
            'arguments': {},
        }

        check_approval(agent)

        assert io.sent == []

    def test_unknown_tool_without_io_remains_noninteractive(self):
        """Local library use has no approval channel and keeps existing behavior."""
        agent = FakeAgent(io=None)
        agent.current_session['pending_tool'] = {
            'name': 'my_custom_tool',
            'arguments': {},
        }

        check_approval(agent)

    def test_unknown_tool_in_full_access_uses_explicit_bypass(self):
        """Full access remains an explicit authority decision made by another plugin."""
        io = FakeIO()
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'full-access'
        agent.current_session['turns_left'] = 4
        agent.current_session['pending_tool'] = {
            'name': 'my_custom_tool',
            'arguments': {},
        }

        check_approval(agent)

        assert io.sent == []

    def test_malformed_full_access_state_needs_explicit_approval(self):
        """A mode label without its bounded grant is presentation, not authority."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'once'}])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'full-access'
        agent.current_session['pending_tool'] = {
            'name': 'my_custom_tool',
            'arguments': {},
        }

        check_approval(agent)

        assert [event['type'] for event in io.sent] == ['approval_needed']

    def test_workspace_profile_still_allows_named_file_edits(self):
        """The fail-closed fallback must not redefine the workspace profile."""
        io = FakeIO()
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'auto'
        agent.current_session['pending_tool'] = {
            'name': 'edit',
            'arguments': {'file_path': 'README.md'},
        }

        check_approval(agent)

        assert io.sent == []

    @pytest.mark.parametrize(
        ('mode', 'tool_name', 'arguments'),
        [
            ('full-access', 'third_party_tool', {}),
            ('auto', 'write', {'file_path': 'owned.txt', 'content': 'no'}),
        ],
    )
    def test_contact_uses_the_same_mode_as_every_participant(
        self, mode, tool_name, arguments
    ):
        """Participant identity does not silently reduce a canonical mode."""
        io = FakeIO(responses=[{'approved': True, 'scope': 'once'}])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = mode
        if mode == 'full-access':
            agent.current_session['turns_left'] = 2
        agent.current_session['requester'] = {
            'address': '0x' + 'e' * 64,
            'level': 'contact',
        }
        agent.current_session['pending_tool'] = {
            'name': tool_name,
            'arguments': arguments,
        }

        check_approval(agent)

        assert io.sent == []


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
        """_save_session_approval saves to unified permissions with 'when' field."""
        session = {}
        _save_session_approval(session, 'bash', {'command': 'npm install'})

        assert 'bash' in session['permissions']
        assert session['permissions']['bash']['allowed'] is True
        assert session['permissions']['bash']['source'] == 'user'
        # User approvals are tool-level (no 'when' field)
        assert 'when' not in session['permissions']['bash']
        assert session['permissions']['bash']['expires'] == {'type': 'session_end'}


class TestPollModeChanges:
    """Test poll_mode_changes before_iteration handler."""

    def test_poll_mode_changes_no_io_skips(self):
        """poll_mode_changes should skip when no IO."""
        agent = FakeAgent(io=None)

        # Should not raise
        poll_mode_changes(agent)

    def test_poll_mode_changes_handles_read_only(self):
        io = FakeIO(pending_signals=[{'type': 'mode_change', 'mode': 'read-only'}])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'auto'

        poll_mode_changes(agent)

        assert agent.current_session['mode'] == 'read-only'

    def test_poll_mode_changes_rejects_removed_plan_mode(self):
        io = FakeIO(pending_signals=[{'type': 'mode_change', 'mode': 'plan'}])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'auto'

        poll_mode_changes(agent)

        assert agent.current_session['mode'] == 'auto'
        assert io.sent == []

    def test_unknown_stored_mode_is_discarded_to_auto_on_a_valid_change(self):
        io = FakeIO(pending_signals=[{'type': 'mode_change', 'mode': 'read-only'}])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = ':workspace'

        poll_mode_changes(agent)

        assert agent.current_session['mode'] == 'read-only'
        assert io.sent == [
            {'type': 'mode_changed', 'mode': 'read-only', 'triggered_by': 'agent'}
        ]

    def test_poll_mode_changes_handles_auto(self):
        io = FakeIO(pending_signals=[{'type': 'mode_change', 'mode': 'auto'}])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'read-only'

        poll_mode_changes(agent)

        assert agent.current_session['mode'] == 'auto'

    def test_poll_mode_changes_handles_bounded_full_access(self):
        io = FakeIO(pending_signals=[{
            'type': 'mode_change', 'mode': 'full-access', 'turns_left': 50,
        }])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'read-only'

        poll_mode_changes(agent)

        assert agent.current_session['mode'] == 'full-access'
        assert agent.current_session['turns_left'] == 50

    def test_contact_can_activate_host_offered_full_access(self):
        io = FakeIO(pending_signals=[
            {'type': 'mode_change', 'mode': 'full-access', 'turns_left': 50},
        ])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'read-only'
        agent.current_session['requester'] = {
            'address': '0x' + 'e' * 64,
            'level': 'contact',
        }

        poll_mode_changes(agent)
        agent.current_session['pending_tool'] = {
            'name': 'third_party_tool',
            'arguments': {},
        }

        check_approval(agent)

        assert agent.current_session['mode'] == 'full-access'
        assert agent.current_session['turns_left'] == 50
        assert not any(msg['type'] == 'approval_needed' for msg in io.sent)

    def test_contact_can_select_auto(self):
        io = FakeIO(pending_signals=[
            {'type': 'mode_change', 'mode': 'auto'},
        ])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'read-only'
        agent.current_session['requester'] = {
            'address': '0x' + 'e' * 64,
            'level': 'contact',
        }

        poll_mode_changes(agent)
        agent.current_session['pending_tool'] = {
            'name': 'write',
            'arguments': {'file_path': 'owned.txt', 'content': 'no'},
        }

        check_approval(agent)

        assert agent.current_session['mode'] == 'auto'
        assert not any(msg['type'] == 'approval_needed' for msg in io.sent)

    def test_poll_mode_changes_handles_multiple_signals(self):
        """poll_mode_changes should process multiple mode_change signals."""
        io = FakeIO(pending_signals=[
            {'type': 'mode_change', 'mode': 'read-only'},
            {'type': 'mode_change', 'mode': 'auto'},
        ])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'auto'

        poll_mode_changes(agent)

        assert agent.current_session['mode'] == 'auto'

    def test_poll_mode_changes_ignores_other_message_types(self):
        """poll_mode_changes should only process mode_change messages."""
        io = FakeIO(pending_signals=[
            {'type': 'other_signal', 'data': 123},
            {'type': 'mode_change', 'mode': 'read-only'},
        ])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'auto'

        poll_mode_changes(agent)

        assert agent.current_session['mode'] == 'read-only'
        # Other signal should still be in pending
        assert len(io.pending_signals) == 1
        assert io.pending_signals[0]['type'] == 'other_signal'

    def test_poll_mode_changes_ignores_invalid_modes(self):
        """poll_mode_changes should ignore invalid mode values."""
        io = FakeIO(pending_signals=[{'type': 'mode_change', 'mode': 'invalid_mode'}])
        agent = FakeAgent(io=io)
        agent.current_session['mode'] = 'read-only'

        poll_mode_changes(agent)

        # Mode unchanged
        assert agent.current_session['mode'] == 'read-only'


class TestPluginExport:
    """Test plugin is properly exported."""

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
        assert 'before_iteration' in agent.events


class TestPollInterrupt:
    """Test poll_interrupt before_iteration handler (stop button)."""

    def test_poll_interrupt_no_io_skips(self):
        """poll_interrupt should skip when no IO (local execution)."""
        agent = FakeAgent(io=None)

        poll_interrupt(agent)  # should not raise

        assert 'stop_signal' not in agent.current_session

    def test_poll_interrupt_sets_stop_signal(self):
        """An INTERRUPT message sets stop_signal so the loop exits at the boundary."""
        io = FakeIO(pending_signals=[{'type': 'INTERRUPT'}])
        agent = FakeAgent(io=io)

        poll_interrupt(agent)

        assert agent.current_session['stop_signal'] == 'user_interrupt'

    def test_poll_interrupt_no_message_leaves_signal_unset(self):
        """Without an INTERRUPT, poll_interrupt must not stop the loop."""
        io = FakeIO(pending_signals=[{'type': 'mode_change', 'mode': 'read-only'}])
        agent = FakeAgent(io=io)

        poll_interrupt(agent)

        assert 'stop_signal' not in agent.current_session
