"""Unit tests for connectonion/interactive_debugger.py

Tests cover:
- InteractiveDebugger initialization
- start_debug_session: Single prompt and interactive modes
- _execute_debug_task: Task execution with debugging
- _attach_debugger_to_tool_execution: Monkey-patching tool executor
- _detach_debugger_from_tool_execution: Restoring original function
- _show_breakpoint_ui_and_wait_for_continue: Breakpoint handling
- _get_llm_next_action_preview: LLM preview functionality

SAFETY: Uses fixture to restore global state after tests that modify tool_executor
"""

import pytest
from unittest.mock import patch, Mock, MagicMock


@pytest.fixture
def restore_tool_executor():
    """Fixture to save and restore tool_executor.execute_single_tool.

    This prevents test pollution when tests modify global state.
    """
    from connectonion import tool_executor
    original = tool_executor.execute_single_tool
    yield original
    tool_executor.execute_single_tool = original


class TestInteractiveDebuggerInit:
    """Tests for InteractiveDebugger initialization."""

    def test_init_with_agent(self):
        """Test initializing with an agent creates default UI."""
        from connectonion.interactive_debugger import InteractiveDebugger

        mock_agent = Mock()
        debugger = InteractiveDebugger(mock_agent)

        assert debugger.agent == mock_agent
        assert debugger.ui is not None
        assert debugger.original_execute_single_tool is None

    def test_init_with_custom_ui(self):
        """Test initializing with custom UI."""
        from connectonion.interactive_debugger import InteractiveDebugger
        from connectonion.debugger_ui import DebuggerUI

        mock_agent = Mock()
        mock_ui = Mock(spec=DebuggerUI)

        debugger = InteractiveDebugger(mock_agent, ui=mock_ui)

        assert debugger.ui == mock_ui


class TestStartDebugSession:
    """Tests for start_debug_session method."""

    def test_start_debug_session_single_prompt(self):
        """Test start_debug_session with single prompt executes once."""
        from connectonion.interactive_debugger import InteractiveDebugger

        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_ui = Mock()

        debugger = InteractiveDebugger(mock_agent, ui=mock_ui)
        debugger._execute_debug_task = Mock()

        debugger.start_debug_session("Find something")

        mock_ui.show_welcome.assert_called_once_with("test-agent")
        debugger._execute_debug_task.assert_called_once_with("Find something")

    def test_start_debug_session_interactive_mode(self):
        """Test start_debug_session interactive mode loops until quit."""
        from connectonion.interactive_debugger import InteractiveDebugger

        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_ui = Mock()
        # Return prompt, then None to quit
        mock_ui.get_user_prompt.side_effect = ["First task", None]

        debugger = InteractiveDebugger(mock_agent, ui=mock_ui)
        debugger._execute_debug_task = Mock()

        debugger.start_debug_session()  # No prompt = interactive mode

        assert debugger._execute_debug_task.call_count == 1
        debugger._execute_debug_task.assert_called_with("First task")


class TestExecuteDebugTask:
    """Tests for _execute_debug_task method."""

    def test_execute_debug_task_attaches_and_detaches(self):
        """Test _execute_debug_task attaches and detaches debugger."""
        from connectonion.interactive_debugger import InteractiveDebugger

        mock_agent = Mock()
        mock_agent.input.return_value = "Result"
        mock_agent.current_session = {'trace': []}
        mock_agent.max_iterations = 10
        mock_ui = Mock()

        debugger = InteractiveDebugger(mock_agent, ui=mock_ui)
        debugger._attach_debugger_to_tool_execution = Mock()
        debugger._detach_debugger_from_tool_execution = Mock()
        debugger._show_execution_analysis = Mock()

        debugger._execute_debug_task("Find something")

        debugger._attach_debugger_to_tool_execution.assert_called_once()
        debugger._detach_debugger_from_tool_execution.assert_called_once()
        mock_agent.input.assert_called_once_with("Find something")
        mock_ui.show_result.assert_called_once_with("Result")

    def test_execute_debug_task_handles_keyboard_interrupt(self):
        """Test _execute_debug_task handles KeyboardInterrupt gracefully."""
        from connectonion.interactive_debugger import InteractiveDebugger

        mock_agent = Mock()
        mock_agent.input.side_effect = KeyboardInterrupt
        mock_ui = Mock()

        debugger = InteractiveDebugger(mock_agent, ui=mock_ui)
        debugger._attach_debugger_to_tool_execution = Mock()
        debugger._detach_debugger_from_tool_execution = Mock()

        debugger._execute_debug_task("Find something")

        mock_ui.show_interrupted.assert_called_once()
        # Should still detach
        debugger._detach_debugger_from_tool_execution.assert_called_once()


class TestAttachDebugger:
    """Tests for _attach_debugger_to_tool_execution method."""

    def test_attach_stores_original_function(self, restore_tool_executor):
        """Test attaching stores original execute_single_tool."""
        from connectonion.interactive_debugger import InteractiveDebugger

        original_func = restore_tool_executor

        mock_agent = Mock()
        debugger = InteractiveDebugger(mock_agent)
        debugger._attach_debugger_to_tool_execution()

        assert debugger.original_execute_single_tool == original_func

    def test_attach_replaces_function(self, restore_tool_executor):
        """Test attaching replaces execute_single_tool."""
        from connectonion.interactive_debugger import InteractiveDebugger
        from connectonion import tool_executor

        original_func = restore_tool_executor

        mock_agent = Mock()
        debugger = InteractiveDebugger(mock_agent)
        debugger._attach_debugger_to_tool_execution()

        assert tool_executor.execute_single_tool != original_func


class TestDetachDebugger:
    """Tests for _detach_debugger_from_tool_execution method."""

    def test_detach_restores_original_function(self, restore_tool_executor):
        """Test detaching restores original execute_single_tool."""
        from connectonion.interactive_debugger import InteractiveDebugger
        from connectonion import tool_executor

        original_func = restore_tool_executor

        mock_agent = Mock()
        debugger = InteractiveDebugger(mock_agent)
        debugger._attach_debugger_to_tool_execution()
        debugger._detach_debugger_from_tool_execution()

        assert tool_executor.execute_single_tool == original_func

    def test_detach_does_nothing_when_not_attached(self, restore_tool_executor):
        """Test detaching when not attached does nothing."""
        from connectonion.interactive_debugger import InteractiveDebugger

        mock_agent = Mock()
        debugger = InteractiveDebugger(mock_agent)

        # Should not raise
        debugger._detach_debugger_from_tool_execution()


class TestShowBreakpointUI:
    """Tests for _show_breakpoint_ui_and_wait_for_continue method."""

    def test_breakpoint_ui_continue_action(self):
        """Test breakpoint UI returns on CONTINUE action."""
        from connectonion.interactive_debugger import InteractiveDebugger
        from connectonion.debugger_ui import BreakpointAction

        mock_agent = Mock()
        mock_agent.current_session = {'trace': [], 'user_prompt': 'Find'}
        mock_agent.max_iterations = 10
        mock_agent.tools = Mock()
        mock_agent.tools.get.return_value = None

        mock_ui = Mock()
        mock_ui.show_breakpoint.return_value = BreakpointAction.CONTINUE

        debugger = InteractiveDebugger(mock_agent, ui=mock_ui)
        debugger._get_llm_next_action_preview = Mock(return_value=[])

        # Should not raise, just return
        debugger._show_breakpoint_ui_and_wait_for_continue(
            "search", {"query": "test"}, {"result": "Found"}
        )

        mock_ui.show_breakpoint.assert_called_once()

    def test_breakpoint_ui_quit_raises_interrupt(self):
        """Test breakpoint UI raises KeyboardInterrupt on QUIT."""
        from connectonion.interactive_debugger import InteractiveDebugger
        from connectonion.debugger_ui import BreakpointAction

        mock_agent = Mock()
        mock_agent.current_session = {'trace': [], 'user_prompt': 'Find'}
        mock_agent.max_iterations = 10
        mock_agent.tools = Mock()
        mock_agent.tools.get.return_value = None

        mock_ui = Mock()
        mock_ui.show_breakpoint.return_value = BreakpointAction.QUIT

        debugger = InteractiveDebugger(mock_agent, ui=mock_ui)
        debugger._get_llm_next_action_preview = Mock(return_value=[])

        with pytest.raises(KeyboardInterrupt):
            debugger._show_breakpoint_ui_and_wait_for_continue(
                "search", {"query": "test"}, {"result": "Found"}
            )

    def test_breakpoint_ui_edit_applies_modifications(self):
        """Test breakpoint UI applies modifications from EDIT."""
        from connectonion.interactive_debugger import InteractiveDebugger
        from connectonion.debugger_ui import BreakpointAction

        mock_agent = Mock()
        mock_agent.current_session = {'trace': [], 'user_prompt': 'Find'}
        mock_agent.max_iterations = 10
        mock_agent.tools = Mock()
        mock_agent.tools.get.return_value = None

        mock_ui = Mock()
        # First EDIT, then CONTINUE
        mock_ui.show_breakpoint.side_effect = [
            BreakpointAction.EDIT,
            BreakpointAction.CONTINUE
        ]
        mock_ui.edit_value.return_value = {'result': 'Modified result'}

        debugger = InteractiveDebugger(mock_agent, ui=mock_ui)
        debugger._get_llm_next_action_preview = Mock(return_value=[])

        trace_entry = {"result": "Original"}
        debugger._show_breakpoint_ui_and_wait_for_continue(
            "search", {"query": "test"}, trace_entry
        )

        # Result should be modified
        assert trace_entry['result'] == 'Modified result'


class TestGetLLMNextActionPreview:
    """Tests for _get_llm_next_action_preview method."""

    def test_preview_returns_tool_calls(self):
        """Test preview returns next planned tool calls."""
        from connectonion.interactive_debugger import InteractiveDebugger

        mock_tool_call = Mock()
        mock_tool_call.name = "save"
        mock_tool_call.arguments = {"data": "result"}

        mock_response = Mock()
        mock_response.tool_calls = [mock_tool_call]

        mock_llm = Mock()
        mock_llm.complete.return_value = mock_response

        mock_tool = Mock()
        mock_tool.to_function_schema.return_value = {}

        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [
                {'role': 'user', 'content': 'Find and save'},
                {'role': 'assistant', 'tool_calls': [
                    {'id': 'call_1', 'function': {'name': 'search'}}
                ]}
            ]
        }
        mock_agent.llm = mock_llm
        mock_agent.tools = [mock_tool]

        debugger = InteractiveDebugger(mock_agent)
        result = debugger._get_llm_next_action_preview(
            "search", {"result": "Found data"}
        )

        assert len(result) == 1
        assert result[0]['name'] == "save"
        assert result[0]['args'] == {"data": "result"}

    def test_preview_returns_empty_list_when_no_tools(self):
        """Test preview returns empty list when no tools planned."""
        from connectonion.interactive_debugger import InteractiveDebugger

        mock_response = Mock()
        mock_response.tool_calls = None

        mock_llm = Mock()
        mock_llm.complete.return_value = mock_response

        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [
                {'role': 'user', 'content': 'Find'},
                {'role': 'assistant', 'tool_calls': [
                    {'id': 'call_1', 'function': {'name': 'search'}}
                ]}
            ]
        }
        mock_agent.llm = mock_llm
        mock_agent.tools = []

        debugger = InteractiveDebugger(mock_agent)
        result = debugger._get_llm_next_action_preview(
            "search", {"result": "Found"}
        )

        assert result == []

    def test_preview_returns_none_on_error(self):
        """Test preview returns None on error."""
        from connectonion.interactive_debugger import InteractiveDebugger

        mock_llm = Mock()
        mock_llm.complete.side_effect = Exception("LLM error")

        mock_agent = Mock()
        mock_agent.current_session = {'messages': []}
        mock_agent.llm = mock_llm
        mock_agent.tools = []

        debugger = InteractiveDebugger(mock_agent)
        result = debugger._get_llm_next_action_preview(
            "search", {"result": "Found"}
        )

        assert result is None


class TestShowExecutionAnalysis:
    """Tests for _show_execution_analysis method."""

    @patch('connectonion.execution_analyzer.execution_analysis.llm_do')
    @patch('rich.console.Console')
    def test_show_execution_analysis_calls_ui(self, mock_console_class, mock_llm_do):
        """Test _show_execution_analysis calls display_execution_analysis on UI."""
        from connectonion.interactive_debugger import InteractiveDebugger
        from connectonion.execution_analyzer.execution_analysis import ExecutionAnalysis

        # Mock llm_do to return an ExecutionAnalysis
        mock_llm_do.return_value = ExecutionAnalysis(
            task_completed=True,
            completion_explanation="Done",
            problems_identified=[],
            system_prompt_suggestions=[],
            overall_quality="good",
            key_insights=[]
        )

        # Mock console with status context manager
        mock_status = MagicMock()
        mock_status.__enter__ = Mock(return_value=mock_status)
        mock_status.__exit__ = Mock(return_value=False)

        mock_console = Mock()
        mock_console.status.return_value = mock_status
        mock_console_class.return_value = mock_console

        mock_agent = Mock()
        mock_agent.current_session = {'trace': [], 'iteration': 5}
        mock_agent.max_iterations = 10
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = []
        mock_agent.llm = Mock()
        mock_agent.llm.model = "gpt-4"

        mock_ui = Mock()
        debugger = InteractiveDebugger(mock_agent, ui=mock_ui)

        debugger._show_execution_analysis("Find something", "Found it!")

        mock_ui.display_execution_analysis.assert_called_once()


class TestInterceptorOnlyAffectsOwnAgent:
    """Tests for ensuring interceptor only affects its own agent."""

    def test_interceptor_returns_trace_entry_for_other_agents(self, restore_tool_executor):
        """Test interceptor returns trace entry for other agents without pausing."""
        from connectonion.interactive_debugger import InteractiveDebugger
        from connectonion import tool_executor

        # Create two agents
        agent1 = Mock()
        agent2 = Mock()

        debugger = InteractiveDebugger(agent1)
        debugger._attach_debugger_to_tool_execution()

        # Store the interceptor's original_execute to mock it
        expected_trace = {'status': 'success', 'result': 'test'}
        debugger.original_execute_single_tool = Mock(return_value=expected_trace)

        # Call interceptor with agent2 (not agent1)
        mock_tools = Mock()
        mock_tools.get.return_value = Mock()

        result = tool_executor.execute_single_tool(
            "search", {}, "call_1", mock_tools, agent2, Mock()
        )

        # Should return the trace entry directly (agent check skips debugging)
        assert result == expected_trace

    def test_interceptor_identity_check(self):
        """Test that debugger has identity check for agent."""
        from connectonion.interactive_debugger import InteractiveDebugger

        agent1 = Mock()
        agent2 = Mock()

        # Different agent instances should not be equal
        debugger = InteractiveDebugger(agent1)

        # The debugger should only debug agent1, not agent2
        assert debugger.agent is agent1
        assert debugger.agent is not agent2
