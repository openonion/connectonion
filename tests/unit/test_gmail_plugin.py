"""Unit tests for connectonion/useful_plugins/gmail_plugin.py

Tests cover:
- check_email_approval: approval workflow for send/reply
- sync_crm_after_send: CRM update after successful sends
- Plugin registration with correct events
"""

import pytest
import importlib
from unittest.mock import Mock, patch, MagicMock

# Import the module directly to avoid __init__.py shadowing
gmail_plugin_module = importlib.import_module('connectonion.useful_plugins.gmail_plugin')
check_email_approval = gmail_plugin_module.check_email_approval
sync_crm_after_send = gmail_plugin_module.sync_crm_after_send
gmail_plugin = gmail_plugin_module.gmail_plugin
SEND_METHODS = gmail_plugin_module.SEND_METHODS


class FakeAgent:
    """Fake agent for testing plugins."""

    def __init__(self):
        self.current_session = {
            'messages': [],
            'trace': [],
            'pending_tool': None,
        }
        self.logger = Mock()
        self.tools = Mock()


class TestSendMethods:
    """Tests for SEND_METHODS constant."""

    def test_send_methods_contains_send(self):
        """Test that SEND_METHODS contains 'send'."""
        assert 'send' in SEND_METHODS

    def test_send_methods_contains_reply(self):
        """Test that SEND_METHODS contains 'reply'."""
        assert 'reply' in SEND_METHODS

    def test_send_methods_is_tuple(self):
        """Test that SEND_METHODS is a tuple."""
        assert isinstance(SEND_METHODS, tuple)


class TestCheckEmailApproval:
    """Tests for check_email_approval function - email approval workflow."""

    def test_no_pending_tool_does_nothing(self):
        """Test that no pending tool means no action."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = None

        # Should not raise
        check_email_approval(agent)

    def test_non_email_tool_skipped(self):
        """Test that non-email tools are skipped."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'search',
            'arguments': {'query': 'test'}
        }

        # Should not raise
        check_email_approval(agent)

    def test_read_operations_skipped(self):
        """Test that read operations don't trigger approval."""
        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'read_inbox',
            'arguments': {'limit': 10}
        }

        # Should not raise
        check_email_approval(agent)

    @patch.object(gmail_plugin_module, 'pick')
    @patch.object(gmail_plugin_module, '_console')
    def test_send_triggers_approval(self, mock_console, mock_pick):
        """Test that send operation triggers approval dialog."""
        mock_pick.return_value = "Yes, send it"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'send',
            'arguments': {
                'to': 'user@example.com',
                'subject': 'Test Subject',
                'body': 'Test body content'
            }
        }

        check_email_approval(agent)
        mock_pick.assert_called_once()

    @patch.object(gmail_plugin_module, 'pick')
    @patch.object(gmail_plugin_module, '_console')
    def test_reply_triggers_approval(self, mock_console, mock_pick):
        """Test that reply operation triggers approval dialog."""
        mock_pick.return_value = "Yes, send it"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'reply',
            'arguments': {
                'email_id': '123abc',
                'body': 'Reply content'
            }
        }

        check_email_approval(agent)
        mock_pick.assert_called_once()

    @patch.object(gmail_plugin_module, 'pick')
    @patch.object(gmail_plugin_module, '_console')
    def test_approval_yes_allows_send(self, mock_console, mock_pick):
        """Test that 'Yes, send it' allows email to be sent."""
        mock_pick.return_value = "Yes, send it"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'send',
            'arguments': {
                'to': 'user@example.com',
                'subject': 'Test',
                'body': 'Content'
            }
        }

        # Should not raise
        check_email_approval(agent)

    def test_approve_all_skips_approval(self):
        """Test that gmail_approve_all skips approval dialog."""
        agent = FakeAgent()
        agent.current_session['gmail_approve_all'] = True
        agent.current_session['pending_tool'] = {
            'name': 'send',
            'arguments': {
                'to': 'user@example.com',
                'subject': 'Test',
                'body': 'Content'
            }
        }

        # Should not raise or call pick
        with patch.object(gmail_plugin_module, 'pick') as mock_pick:
            check_email_approval(agent)
            mock_pick.assert_not_called()

    def test_approved_recipient_skips_approval(self):
        """Test that approved recipient skips approval dialog."""
        agent = FakeAgent()
        agent.current_session['gmail_approved_recipients'] = {'user@example.com'}
        agent.current_session['pending_tool'] = {
            'name': 'send',
            'arguments': {
                'to': 'user@example.com',
                'subject': 'Test',
                'body': 'Content'
            }
        }

        # Should not raise or call pick
        with patch.object(gmail_plugin_module, 'pick') as mock_pick:
            check_email_approval(agent)
            mock_pick.assert_not_called()

    def test_approve_replies_skips_reply_approval(self):
        """Test that gmail_approve_replies skips reply approval."""
        agent = FakeAgent()
        agent.current_session['gmail_approve_replies'] = True
        agent.current_session['pending_tool'] = {
            'name': 'reply',
            'arguments': {
                'email_id': '123',
                'body': 'Reply'
            }
        }

        # Should not raise or call pick
        with patch.object(gmail_plugin_module, 'pick') as mock_pick:
            check_email_approval(agent)
            mock_pick.assert_not_called()

    @patch.object(gmail_plugin_module, 'pick')
    @patch.object(gmail_plugin_module, '_console')
    def test_auto_approve_recipient_adds_to_session(self, mock_console, mock_pick):
        """Test that auto-approving recipient adds to session set."""
        mock_pick.return_value = "Auto approve emails to 'user@example.com'"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'send',
            'arguments': {
                'to': 'user@example.com',
                'subject': 'Test',
                'body': 'Content'
            }
        }

        check_email_approval(agent)

        assert 'gmail_approved_recipients' in agent.current_session
        assert 'user@example.com' in agent.current_session['gmail_approved_recipients']

    @patch.object(gmail_plugin_module, 'pick')
    @patch.object(gmail_plugin_module, '_console')
    def test_auto_approve_all_emails_sets_flag(self, mock_console, mock_pick):
        """Test that auto-approve all sets session flag."""
        mock_pick.return_value = "Auto approve all emails this session"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'send',
            'arguments': {
                'to': 'user@example.com',
                'subject': 'Test',
                'body': 'Content'
            }
        }

        check_email_approval(agent)

        assert agent.current_session.get('gmail_approve_all') is True

    @patch.object(gmail_plugin_module, 'pick')
    @patch.object(gmail_plugin_module, '_console')
    def test_auto_approve_replies_sets_flag(self, mock_console, mock_pick):
        """Test that auto-approve replies sets session flag."""
        mock_pick.return_value = "Auto approve all replies this session"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'reply',
            'arguments': {
                'email_id': '123',
                'body': 'Reply'
            }
        }

        check_email_approval(agent)

        assert agent.current_session.get('gmail_approve_replies') is True

    @patch.object(gmail_plugin_module, 'pick')
    @patch.object(gmail_plugin_module, '_console')
    def test_custom_feedback_raises_value_error(self, mock_console, mock_pick):
        """Test that custom feedback raises ValueError."""
        mock_pick.return_value = "Please use a more formal tone"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'send',
            'arguments': {
                'to': 'user@example.com',
                'subject': 'Test',
                'body': 'Content'
            }
        }

        with pytest.raises(ValueError) as exc_info:
            check_email_approval(agent)

        assert "User feedback: Please use a more formal tone" in str(exc_info.value)

    @patch.object(gmail_plugin_module, 'pick')
    @patch.object(gmail_plugin_module, '_console')
    def test_send_with_cc_bcc_shows_in_preview(self, mock_console, mock_pick):
        """Test that CC and BCC are shown in preview panel."""
        mock_pick.return_value = "Yes, send it"

        agent = FakeAgent()
        agent.current_session['pending_tool'] = {
            'name': 'send',
            'arguments': {
                'to': 'user@example.com',
                'subject': 'Test',
                'body': 'Content',
                'cc': 'cc@example.com',
                'bcc': 'bcc@example.com'
            }
        }

        check_email_approval(agent)

        # Verify Panel was created (shown in console)
        mock_console.print.assert_called()


class TestSyncCrmAfterSend:
    """Tests for sync_crm_after_send function - CRM update after sends."""

    def test_non_tool_execution_skipped(self):
        """Test that non-tool executions are skipped."""
        agent = FakeAgent()
        agent.current_session['trace'] = [{'type': 'llm_call'}]

        # Should not raise
        sync_crm_after_send(agent)

    def test_non_send_tool_skipped(self):
        """Test that non-send tools are skipped."""
        agent = FakeAgent()
        agent.current_session['trace'] = [{
            'type': 'tool_execution',
            'tool_name': 'read_inbox',
            'status': 'success',
            'arguments': {}
        }]

        # Should not raise or call update_contact
        sync_crm_after_send(agent)

    def test_failed_send_skipped(self):
        """Test that failed sends don't update CRM."""
        agent = FakeAgent()
        agent.current_session['trace'] = [{
            'type': 'tool_execution',
            'tool_name': 'send',
            'status': 'error',
            'arguments': {'to': 'user@example.com'}
        }]

        # Should not raise or call update_contact
        sync_crm_after_send(agent)

    def test_send_without_recipient_skipped(self):
        """Test that sends without recipient are skipped."""
        agent = FakeAgent()
        agent.current_session['trace'] = [{
            'type': 'tool_execution',
            'tool_name': 'send',
            'status': 'success',
            'arguments': {}
        }]

        # Should not raise
        sync_crm_after_send(agent)

    def test_successful_send_updates_crm(self):
        """Test that successful send updates CRM."""
        agent = FakeAgent()
        agent.current_session['trace'] = [{
            'type': 'tool_execution',
            'tool_name': 'send',
            'status': 'success',
            'arguments': {'to': 'user@example.com'}
        }]

        mock_gmail = Mock()
        mock_gmail.update_contact.return_value = "Updated contact"
        agent.tools.gmail = mock_gmail

        with patch.object(gmail_plugin_module, '_console'):
            sync_crm_after_send(agent)

        mock_gmail.update_contact.assert_called_once()
        call_args = mock_gmail.update_contact.call_args
        assert call_args[0][0] == 'user@example.com'
        assert 'last_contact' in call_args[1]
        assert call_args[1]['next_contact_date'] == ''

    def test_successful_reply_updates_crm(self):
        """Test that successful reply updates CRM."""
        agent = FakeAgent()
        agent.current_session['trace'] = [{
            'type': 'tool_execution',
            'tool_name': 'reply',
            'status': 'success',
            'arguments': {'to': 'user@example.com'}
        }]

        mock_gmail = Mock()
        mock_gmail.update_contact.return_value = "Updated contact"
        agent.tools.gmail = mock_gmail

        with patch.object(gmail_plugin_module, '_console'):
            sync_crm_after_send(agent)

        mock_gmail.update_contact.assert_called_once()


class TestGmailPlugin:
    """Tests for gmail_plugin plugin bundle."""

    def test_gmail_plugin_contains_two_handlers(self):
        """Test that gmail_plugin has two handlers."""
        assert len(gmail_plugin) == 2

    def test_handlers_have_correct_event_types(self):
        """Test that handlers are registered for correct events."""
        # check_email_approval should be before_each_tool
        assert hasattr(check_email_approval, '_event_type')
        assert check_email_approval._event_type == 'before_each_tool'

        # sync_crm_after_send should be after_each_tool
        assert hasattr(sync_crm_after_send, '_event_type')
        assert sync_crm_after_send._event_type == 'after_each_tool'

    def test_plugin_integrates_with_agent(self):
        """Test that plugin can be registered with agent."""
        from connectonion import Agent
        from connectonion.llm import LLMResponse
        from connectonion.usage import TokenUsage

        # Create mock LLM
        mock_llm = Mock()
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
            plugins=[gmail_plugin],
            log=False,
        )

        # Verify events are registered
        assert 'before_each_tool' in agent.events
        assert 'after_each_tool' in agent.events
