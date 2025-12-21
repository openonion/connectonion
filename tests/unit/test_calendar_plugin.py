"""Unit tests for connectonion/useful_plugins/calendar_plugin.py

Tests cover:
- check_calendar_approval: approval workflow for calendar modifications
- Plugin registration with correct events
"""

import pytest
import importlib
from unittest.mock import Mock, patch

# Import the module directly to avoid __init__.py shadowing
calendar_plugin_module = importlib.import_module('connectonion.useful_plugins.calendar_plugin')
check_calendar_approval = calendar_plugin_module.check_calendar_approval
calendar_plugin = calendar_plugin_module.calendar_plugin
WRITE_METHODS = calendar_plugin_module.WRITE_METHODS


class FakeAgent:
    """Fake agent for testing plugins."""

    def __init__(self):
        self.current_session = {
            'messages': [],
            'trace': [],
            'pending_tool': None,
        }
        self.logger = Mock()


class TestWriteMethods:
    """Tests for WRITE_METHODS constant."""

    def test_write_methods_contains_create_event(self):
        """Test that WRITE_METHODS contains 'create_event'."""
        assert 'create_event' in WRITE_METHODS

    def test_write_methods_contains_create_meet(self):
        """Test that WRITE_METHODS contains 'create_meet'."""
        assert 'create_meet' in WRITE_METHODS

    def test_write_methods_contains_update_event(self):
        """Test that WRITE_METHODS contains 'update_event'."""
        assert 'update_event' in WRITE_METHODS

    def test_write_methods_contains_delete_event(self):
        """Test that WRITE_METHODS contains 'delete_event'."""
        assert 'delete_event' in WRITE_METHODS

    def test_write_methods_is_tuple(self):
        """Test that WRITE_METHODS is a tuple."""
        assert isinstance(WRITE_METHODS, tuple)


class TestCheckCalendarApproval:
    """Tests for check_calendar_approval function - calendar approval workflow."""

    def test_no_pending_tool_does_nothing(self):
        """Test that no pending tool means no action."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = None

        # Should not raise
        check_calendar_approval(agent)

    def test_non_calendar_tool_skipped(self):
        """Test that non-calendar tools are skipped."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'search',
            'arguments': {'query': 'test'}
        }

        # Should not raise
        check_calendar_approval(agent)

    def test_read_operations_skipped(self):
        """Test that read operations don't trigger approval."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'list_events',
            'arguments': {}
        }

        # Should not raise
        check_calendar_approval(agent)

    @pytest.mark.parametrize("method", ['create_event', 'create_meet', 'update_event', 'delete_event'])
    @patch.object(calendar_plugin_module, 'pick')
    @patch.object(calendar_plugin_module, '_console')
    def test_write_methods_trigger_approval(self, mock_console, mock_pick, method):
        """Test that all write methods trigger approval dialog."""
        mock_pick.return_value = f"Yes, {method.replace('_', ' ')}"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': method,
            'arguments': {
                'title': 'Test Event',
                'start_time': '2024-01-15 10:00',
                'end_time': '2024-01-15 11:00',
                'event_id': 'abc123',
            }
        }

        check_calendar_approval(agent)
        mock_pick.assert_called_once()

    @patch.object(calendar_plugin_module, 'pick')
    @patch.object(calendar_plugin_module, '_console')
    def test_approval_yes_allows_action(self, mock_console, mock_pick):
        """Test that 'Yes' allows calendar action to proceed."""
        mock_pick.return_value = "Yes, create event"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'create_event',
            'arguments': {
                'title': 'Meeting',
                'start_time': '2024-01-15 10:00',
                'end_time': '2024-01-15 11:00'
            }
        }

        # Should not raise
        check_calendar_approval(agent)

    def test_approve_all_skips_approval(self):
        """Test that calendar_approve_all skips approval dialog."""
        agent = FakeAgent()
        agent.current_session['calendar_approve_all'] = True
        agent.current_session['pending_tool'] = {
            'name': 'create_event',
            'arguments': {
                'title': 'Meeting',
                'start_time': '2024-01-15 10:00',
                'end_time': '2024-01-15 11:00'
            }
        }

        # Should not raise or call pick
        with patch.object(calendar_plugin_module, 'pick') as mock_pick:
            check_calendar_approval(agent)
            mock_pick.assert_not_called()

    @patch.object(calendar_plugin_module, 'pick')
    @patch.object(calendar_plugin_module, '_console')
    def test_auto_approve_all_sets_flag(self, mock_console, mock_pick):
        """Test that auto-approve all sets session flag."""
        mock_pick.return_value = "Auto approve all calendar actions this session"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'create_event',
            'arguments': {
                'title': 'Meeting',
                'start_time': '2024-01-15 10:00',
                'end_time': '2024-01-15 11:00'
            }
        }

        check_calendar_approval(agent)

        assert agent.current_session.get('calendar_approve_all') is True

    @patch.object(calendar_plugin_module, 'pick')
    @patch.object(calendar_plugin_module, '_console')
    @patch('builtins.input', return_value='schedule for tomorrow instead')
    def test_rejection_raises_value_error(self, mock_input, mock_console, mock_pick):
        """Test that rejection raises ValueError with feedback."""
        mock_pick.return_value = "No, tell agent what I want"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'create_event',
            'arguments': {
                'title': 'Meeting',
                'start_time': '2024-01-15 10:00',
                'end_time': '2024-01-15 11:00'
            }
        }

        with pytest.raises(ValueError) as exc_info:
            check_calendar_approval(agent)

        assert "User feedback: schedule for tomorrow instead" in str(exc_info.value)

    @patch.object(calendar_plugin_module, 'pick')
    @patch.object(calendar_plugin_module, '_console')
    def test_create_event_shows_all_fields(self, mock_console, mock_pick):
        """Test that create_event shows all fields in preview."""
        mock_pick.return_value = "Yes, create event"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'create_event',
            'arguments': {
                'title': 'Team Meeting',
                'start_time': '2024-01-15 10:00',
                'end_time': '2024-01-15 11:00',
                'attendees': 'alice@example.com, bob@example.com',
                'location': 'Conference Room A',
                'description': 'Weekly team sync'
            }
        }

        check_calendar_approval(agent)

        # Verify Panel was created (shown in console)
        mock_console.print.assert_called()

    @patch.object(calendar_plugin_module, 'pick')
    @patch.object(calendar_plugin_module, '_console')
    def test_create_meet_shows_attendee_warning(self, mock_console, mock_pick):
        """Test that create_meet shows attendee notification warning."""
        mock_pick.return_value = "Yes, create meeting"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'create_meet',
            'arguments': {
                'title': 'Video Call',
                'start_time': '2024-01-15 10:00',
                'end_time': '2024-01-15 11:00',
                'attendees': 'user@example.com'
            }
        }

        check_calendar_approval(agent)
        mock_console.print.assert_called()

    @patch.object(calendar_plugin_module, 'pick')
    @patch.object(calendar_plugin_module, '_console')
    def test_update_event_shows_event_id(self, mock_console, mock_pick):
        """Test that update_event shows event ID."""
        mock_pick.return_value = "Yes, update event"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'update_event',
            'arguments': {
                'event_id': 'event123',
                'title': 'New Title',
                'start_time': '2024-01-16 10:00'
            }
        }

        check_calendar_approval(agent)
        mock_console.print.assert_called()

    @patch.object(calendar_plugin_module, 'pick')
    @patch.object(calendar_plugin_module, '_console')
    def test_delete_event_shows_warning(self, mock_console, mock_pick):
        """Test that delete_event shows permanent deletion warning."""
        mock_pick.return_value = "Yes, delete event"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'delete_event',
            'arguments': {
                'event_id': 'event123'
            }
        }

        check_calendar_approval(agent)
        mock_console.print.assert_called()


class TestCalendarPlugin:
    """Tests for calendar_plugin plugin bundle."""

    def test_calendar_plugin_contains_one_handler(self):
        """Test that calendar_plugin has one handler."""
        assert len(calendar_plugin) == 1

    def test_handler_has_correct_event_type(self):
        """Test that handler is registered for before_each_tool event."""
        assert hasattr(check_calendar_approval, '_event_type')
        assert check_calendar_approval._event_type == 'before_each_tool'

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
            plugins=[calendar_plugin],
            log=False,
        )

        # Verify event is registered
        assert 'before_each_tool' in agent.events
