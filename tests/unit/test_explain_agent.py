"""Unit tests for connectonion/debug_explainer/explain_agent.py

Tests cover:
- explain_tool_choice: Creates explainer agent to explain tool decisions
"""

import pytest
from unittest.mock import patch, Mock, MagicMock


class TestExplainToolChoice:
    """Tests for explain_tool_choice function."""

    @patch('connectonion.agent.Agent')
    def test_explain_tool_choice_basic(self, mock_agent_class):
        """Test basic explain_tool_choice call."""
        from connectonion.debug_explainer.explain_agent import explain_tool_choice

        # Mock the explainer agent
        mock_explainer = Mock()
        mock_explainer.input.return_value = "The tool was chosen because..."
        mock_agent_class.return_value = mock_explainer

        # Create mock breakpoint context
        mock_bp = Mock()
        mock_bp.tool_name = "search"
        mock_bp.tool_args = {"query": "test"}
        mock_bp.user_prompt = "Find something"
        mock_bp.trace_entry = {'result': 'Found it', 'status': 'success'}
        mock_bp.previous_tools = []
        mock_bp.iteration = 1
        mock_bp.next_actions = []

        # Create mock agent being debugged
        mock_tool = Mock()
        mock_tool.name = "search"
        mock_tool.run = lambda x: x

        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_agent.system_prompt = "You are a helpful assistant"
        mock_agent.tools = Mock()
        mock_agent.tools.get.return_value = mock_tool
        mock_agent.tools.__iter__ = Mock(return_value=iter([mock_tool]))
        mock_agent.current_session = {'messages': []}

        result = explain_tool_choice(mock_bp, mock_agent, model="gpt-4")

        assert result == "The tool was chosen because..."
        mock_agent_class.assert_called_once()
        mock_explainer.input.assert_called_once()

    @patch('connectonion.agent.Agent')
    def test_explain_tool_choice_creates_explainer_agent(self, mock_agent_class):
        """Test that explain_tool_choice creates an explainer agent with correct params."""
        from connectonion.debug_explainer.explain_agent import explain_tool_choice

        mock_explainer = Mock()
        mock_explainer.input.return_value = "Explanation"
        mock_agent_class.return_value = mock_explainer

        mock_bp = Mock()
        mock_bp.tool_name = "search"
        mock_bp.tool_args = {}
        mock_bp.user_prompt = "Find"
        mock_bp.trace_entry = {'result': 'OK', 'status': 'success'}
        mock_bp.previous_tools = []
        mock_bp.iteration = 1
        mock_bp.next_actions = []

        mock_tool = Mock()
        mock_tool.name = "search"
        mock_tool.run = lambda: None

        mock_agent = Mock()
        mock_agent.name = "agent"
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = Mock()
        mock_agent.tools.get.return_value = mock_tool
        mock_agent.tools.__iter__ = Mock(return_value=iter([mock_tool]))
        mock_agent.current_session = {'messages': []}

        explain_tool_choice(mock_bp, mock_agent, model="co/gpt-5")

        # Verify Agent was created with correct parameters
        call_kwargs = mock_agent_class.call_args.kwargs
        assert call_kwargs['name'] == "tool_choice_explainer"
        assert call_kwargs['model'] == "co/gpt-5"
        assert call_kwargs['max_iterations'] == 5
        assert call_kwargs['log'] is False

    @patch('connectonion.agent.Agent')
    def test_explain_tool_choice_includes_context(self, mock_agent_class):
        """Test that explain_tool_choice includes all context in prompt."""
        from connectonion.debug_explainer.explain_agent import explain_tool_choice

        mock_explainer = Mock()
        mock_explainer.input.return_value = "Explanation"
        mock_agent_class.return_value = mock_explainer

        mock_bp = Mock()
        mock_bp.tool_name = "calculate"
        mock_bp.tool_args = {"a": 1, "b": 2}
        mock_bp.user_prompt = "Add 1 and 2"
        mock_bp.trace_entry = {'result': '3', 'status': 'success'}
        mock_bp.previous_tools = ["validate"]
        mock_bp.iteration = 2
        mock_bp.next_actions = [{'name': 'format', 'args': {}}]

        mock_tool = Mock()
        mock_tool.name = "calculate"
        mock_tool.run = lambda a, b: a + b

        mock_agent = Mock()
        mock_agent.name = "math-agent"
        mock_agent.system_prompt = "You are a math helper"
        mock_agent.tools = Mock()
        mock_agent.tools.get.return_value = mock_tool
        mock_agent.tools.__iter__ = Mock(return_value=iter([mock_tool]))
        mock_agent.current_session = {'messages': [
            {'role': 'user', 'content': 'Add 1 and 2'}
        ]}

        explain_tool_choice(mock_bp, mock_agent)

        # Get the prompt that was passed to the explainer
        input_call = mock_explainer.input.call_args[0][0]

        # Verify context is included
        assert "Add 1 and 2" in input_call
        assert "calculate" in input_call
        assert "math-agent" in input_call
        assert "You are a math helper" in input_call

    @patch('connectonion.agent.Agent')
    def test_explain_tool_choice_no_system_prompt(self, mock_agent_class):
        """Test explain_tool_choice when agent has no system prompt."""
        from connectonion.debug_explainer.explain_agent import explain_tool_choice

        mock_explainer = Mock()
        mock_explainer.input.return_value = "Explanation"
        mock_agent_class.return_value = mock_explainer

        mock_bp = Mock()
        mock_bp.tool_name = "search"
        mock_bp.tool_args = {}
        mock_bp.user_prompt = "Find"
        mock_bp.trace_entry = {'result': 'OK', 'status': 'success'}
        mock_bp.previous_tools = []
        mock_bp.iteration = 1
        mock_bp.next_actions = []

        mock_tool = Mock()
        mock_tool.name = "search"
        mock_tool.run = lambda: None

        mock_agent = Mock()
        mock_agent.name = "agent"
        mock_agent.system_prompt = None  # No system prompt
        mock_agent.tools = Mock()
        mock_agent.tools.get.return_value = mock_tool
        mock_agent.tools.__iter__ = Mock(return_value=iter([mock_tool]))
        mock_agent.current_session = {'messages': []}

        result = explain_tool_choice(mock_bp, mock_agent)

        # Should handle None system prompt
        input_call = mock_explainer.input.call_args[0][0]
        assert "No system prompt" in input_call

    @patch('connectonion.agent.Agent')
    def test_explain_tool_choice_empty_tools(self, mock_agent_class):
        """Test explain_tool_choice when agent has empty tools."""
        from connectonion.debug_explainer.explain_agent import explain_tool_choice

        mock_explainer = Mock()
        mock_explainer.input.return_value = "Explanation"
        mock_agent_class.return_value = mock_explainer

        mock_bp = Mock()
        mock_bp.tool_name = "search"
        mock_bp.tool_args = {}
        mock_bp.user_prompt = "Find"
        mock_bp.trace_entry = {'result': 'OK', 'status': 'success'}
        mock_bp.previous_tools = []
        mock_bp.iteration = 1
        mock_bp.next_actions = []

        # Mock agent with empty tools (not None, since code does tools.get())
        mock_tools = Mock()
        mock_tools.get.return_value = None  # Tool not found
        mock_tools.__iter__ = Mock(return_value=iter([]))  # Empty tools list
        mock_tools.__bool__ = Mock(return_value=False)  # Empty/falsy

        mock_agent = Mock()
        mock_agent.name = "agent"
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = mock_tools
        mock_agent.current_session = {'messages': []}

        result = explain_tool_choice(mock_bp, mock_agent)

        # Should handle empty tools
        input_call = mock_explainer.input.call_args[0][0]
        assert "Available tools: []" in input_call

    @patch('connectonion.agent.Agent')
    def test_explain_tool_choice_with_previous_tools(self, mock_agent_class):
        """Test explain_tool_choice shows previous tools called."""
        from connectonion.debug_explainer.explain_agent import explain_tool_choice

        mock_explainer = Mock()
        mock_explainer.input.return_value = "Explanation"
        mock_agent_class.return_value = mock_explainer

        mock_bp = Mock()
        mock_bp.tool_name = "save"
        mock_bp.tool_args = {}
        mock_bp.user_prompt = "Find and save"
        mock_bp.trace_entry = {'result': 'Saved', 'status': 'success'}
        mock_bp.previous_tools = ["search", "validate"]
        mock_bp.iteration = 3
        mock_bp.next_actions = []

        mock_tool = Mock()
        mock_tool.name = "save"
        mock_tool.run = lambda: None

        mock_agent = Mock()
        mock_agent.name = "agent"
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = Mock()
        mock_agent.tools.get.return_value = mock_tool
        mock_agent.tools.__iter__ = Mock(return_value=iter([mock_tool]))
        mock_agent.current_session = {'messages': []}

        result = explain_tool_choice(mock_bp, mock_agent)

        # Should include previous tools
        input_call = mock_explainer.input.call_args[0][0]
        assert "search" in input_call
        assert "validate" in input_call

