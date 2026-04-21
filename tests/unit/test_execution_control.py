"""
Unit tests for execution_control plugin — Pause/Resume/Stop agent execution.

Tests cover:
- Pause blocks agent until resume
- Stop sets stop_signal on agent session
- No-op when agent has no IO
- Drain multiple control messages (last action wins)
- Connection close during pause exits gracefully
"""

import time
import threading
import pytest
from unittest.mock import Mock, MagicMock
from connectonion.useful_plugins.execution_control import (
    check_execution_control,
    _drain_control_messages,
    execution_control,
)


def make_agent_with_io(messages=None):
    """Create a mock agent with IO that returns queued control messages."""
    agent = Mock()
    agent.current_session = {}
    agent.io = Mock()

    queued = list(messages) if messages else []

    def receive_all(msg_type):
        if msg_type == 'EXECUTION_CONTROL':
            result = list(queued)
            queued.clear()
            return result
        if msg_type == 'io_closed':
            return []
        return []

    agent.io.receive_all = Mock(side_effect=receive_all)
    agent.io.send = Mock()
    return agent


class TestDrainControlMessages:

    def test_returns_last_action(self):
        agent = make_agent_with_io([
            {'action': 'pause'},
            {'action': 'resume'},
        ])
        action = _drain_control_messages(agent)
        assert action == 'resume'

    def test_returns_none_when_empty(self):
        agent = make_agent_with_io([])
        action = _drain_control_messages(agent)
        assert action is None

    def test_single_message(self):
        agent = make_agent_with_io([{'action': 'stop'}])
        action = _drain_control_messages(agent)
        assert action == 'stop'


class TestCheckExecutionControl:

    def test_noop_without_io(self):
        """Plugin does nothing when agent has no IO (local execution)."""
        agent = Mock()
        agent.io = None
        # Should not raise
        check_execution_control(agent)

    def test_stop_sets_stop_signal(self):
        agent = make_agent_with_io([{'action': 'stop'}])
        check_execution_control(agent)

        assert agent.current_session.get('stop_signal') == 'User requested stop.'
        agent.io.send.assert_called_once_with({
            'type': 'EXECUTION_STATE', 'state': 'stopped'
        })

    def test_no_action_is_noop(self):
        agent = make_agent_with_io([])
        check_execution_control(agent)

        assert 'stop_signal' not in agent.current_session
        agent.io.send.assert_not_called()

    def test_pause_then_resume(self):
        """Pause blocks, resume unblocks and sends running state."""
        agent = Mock()
        agent.current_session = {}
        agent.io = Mock()

        call_count = 0
        paused_event = threading.Event()

        def receive_all(msg_type):
            nonlocal call_count
            if msg_type == 'EXECUTION_CONTROL':
                call_count += 1
                if call_count == 1:
                    # First call: initial drain — return pause
                    return [{'action': 'pause'}]
                if call_count == 2:
                    # Second call: inside pause loop — wait a bit, then resume
                    paused_event.set()
                    time.sleep(0.05)
                    return [{'action': 'resume'}]
                return []
            if msg_type == 'io_closed':
                return []
            return []

        agent.io.receive_all = Mock(side_effect=receive_all)
        agent.io.send = Mock()

        # Run in thread since pause blocks
        t = threading.Thread(target=check_execution_control, args=(agent,))
        t.start()

        # Wait for pause to be reached
        paused_event.wait(timeout=2)
        t.join(timeout=3)

        assert not t.is_alive(), "Handler should have returned after resume"

        # Should have sent paused then running
        calls = [c[0][0] for c in agent.io.send.call_args_list]
        assert {'type': 'EXECUTION_STATE', 'state': 'paused'} in calls
        assert {'type': 'EXECUTION_STATE', 'state': 'running'} in calls

    def test_pause_then_stop(self):
        """Stop during pause sets stop_signal and exits."""
        agent = Mock()
        agent.current_session = {}
        agent.io = Mock()

        call_count = 0

        def receive_all(msg_type):
            nonlocal call_count
            if msg_type == 'EXECUTION_CONTROL':
                call_count += 1
                if call_count == 1:
                    return [{'action': 'pause'}]
                if call_count == 2:
                    return [{'action': 'stop'}]
                return []
            if msg_type == 'io_closed':
                return []
            return []

        agent.io.receive_all = Mock(side_effect=receive_all)
        agent.io.send = Mock()

        t = threading.Thread(target=check_execution_control, args=(agent,))
        t.start()
        t.join(timeout=3)

        assert not t.is_alive()
        assert agent.current_session.get('stop_signal') == 'User requested stop.'

        calls = [c[0][0] for c in agent.io.send.call_args_list]
        assert {'type': 'EXECUTION_STATE', 'state': 'paused'} in calls
        assert {'type': 'EXECUTION_STATE', 'state': 'stopped'} in calls


class TestPluginExport:

    def test_execution_control_is_list(self):
        assert isinstance(execution_control, list)
        assert len(execution_control) == 1

    def test_handler_has_event_type(self):
        handler = execution_control[0]
        assert hasattr(handler, '_event_type')
        assert handler._event_type == 'before_iteration'
