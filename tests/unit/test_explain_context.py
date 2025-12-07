"""Unit tests for connectonion/debug_explainer/explain_context.py

Tests cover:
- RootCauseAnalysis: Pydantic model for structured analysis
- RuntimeContext: Experimental debugger for fixing unwanted tool calls
  - test_with_different_system_prompt
  - test_stability_with_current_prompt
  - test_with_different_result
  - analyze_why_this_tool
  - analyze_root_cause
"""

import pytest
from unittest.mock import patch, Mock, MagicMock


class TestRootCauseAnalysisModel:
    """Tests for RootCauseAnalysis Pydantic model."""

    def test_root_cause_analysis_creation(self):
        """Test creating RootCauseAnalysis with all fields."""
        from connectonion.debug_explainer.explain_context import RootCauseAnalysis

        analysis = RootCauseAnalysis(
            primary_cause_source="system_prompt",
            influential_text="You should always search first",
            explanation="The system prompt instructs to search before answering",
            is_correct_choice=True,
            suggested_fix="No fix needed - this is expected behavior"
        )

        assert analysis.primary_cause_source == "system_prompt"
        assert "search" in analysis.influential_text
        assert analysis.is_correct_choice is True

    def test_root_cause_analysis_fields(self):
        """Test RootCauseAnalysis has all required fields."""
        from connectonion.debug_explainer.explain_context import RootCauseAnalysis

        assert 'primary_cause_source' in RootCauseAnalysis.__annotations__
        assert 'influential_text' in RootCauseAnalysis.__annotations__
        assert 'explanation' in RootCauseAnalysis.__annotations__
        assert 'is_correct_choice' in RootCauseAnalysis.__annotations__
        assert 'suggested_fix' in RootCauseAnalysis.__annotations__


class TestRuntimeContextInit:
    """Tests for RuntimeContext initialization."""

    def test_runtime_context_init(self):
        """Test RuntimeContext stores breakpoint and agent."""
        from connectonion.debug_explainer.explain_context import RuntimeContext

        mock_bp = Mock()
        mock_bp.tool_name = "search"
        mock_agent = Mock()

        ctx = RuntimeContext(mock_bp, mock_agent)

        assert ctx.bp_ctx == mock_bp
        assert ctx.agent == mock_agent


class TestRuntimeContextSystemPrompt:
    """Tests for test_with_different_system_prompt method."""

    def test_system_prompt_modification(self):
        """Test testing with different system prompt."""
        from connectonion.debug_explainer.explain_context import RuntimeContext

        # Set up mocks
        mock_bp = Mock()
        mock_bp.tool_name = "search"
        mock_bp.tool_args = {"query": "test"}

        mock_agent = Mock()
        mock_agent.system_prompt = "You are a helpful assistant"
        mock_agent.current_session = {
            'messages': [
                {'role': 'system', 'content': 'You are a helpful assistant'},
                {'role': 'user', 'content': 'Find something'},
                {'role': 'assistant', 'content': '', 'tool_calls': []}
            ]
        }
        mock_agent.tools = []

        mock_response = Mock()
        mock_response.tool_calls = None
        mock_agent.llm.complete.return_value = mock_response

        ctx = RuntimeContext(mock_bp, mock_agent)
        result = ctx.test_with_different_system_prompt("You must never search")

        assert "Current system prompt" in result
        assert "New system prompt" in result
        assert mock_agent.llm.complete.called

    def test_system_prompt_still_calls_tool(self):
        """Test when new prompt still calls the same tool."""
        from connectonion.debug_explainer.explain_context import RuntimeContext

        mock_bp = Mock()
        mock_bp.tool_name = "search"
        mock_bp.tool_args = {}

        mock_agent = Mock()
        mock_agent.system_prompt = "Helper"
        mock_agent.current_session = {'messages': []}
        mock_agent.tools = []

        mock_tool_call = Mock()
        mock_tool_call.name = "search"
        mock_tool_call.arguments = {}
        mock_response = Mock()
        mock_response.tool_calls = [mock_tool_call]
        mock_agent.llm.complete.return_value = mock_response

        ctx = RuntimeContext(mock_bp, mock_agent)
        result = ctx.test_with_different_system_prompt("New prompt")

        assert "Still calls the same tool" in result


class TestRuntimeContextStability:
    """Tests for test_stability_with_current_prompt method."""

    def test_stability_stable_decision(self):
        """Test stability check with consistent decisions."""
        from connectonion.debug_explainer.explain_context import RuntimeContext

        mock_bp = Mock()
        mock_agent = Mock()
        mock_agent.current_session = {'messages': []}
        mock_agent.tools = []

        mock_tool_call = Mock()
        mock_tool_call.name = "search"
        mock_response = Mock()
        mock_response.tool_calls = [mock_tool_call]
        mock_agent.llm.complete.return_value = mock_response

        ctx = RuntimeContext(mock_bp, mock_agent)
        result = ctx.test_stability_with_current_prompt(num_trials=3)

        assert "STABLE" in result
        assert "Tested 3 times" in result

    def test_stability_unstable_decision(self):
        """Test stability check with varying decisions."""
        from connectonion.debug_explainer.explain_context import RuntimeContext

        mock_bp = Mock()
        mock_agent = Mock()
        mock_agent.current_session = {'messages': []}
        mock_agent.tools = []

        # Return different tools on each call
        responses = []
        for name in ["search", "calculate", "search"]:
            mock_tool_call = Mock()
            mock_tool_call.name = name
            mock_response = Mock()
            mock_response.tool_calls = [mock_tool_call]
            responses.append(mock_response)

        mock_agent.llm.complete.side_effect = responses

        ctx = RuntimeContext(mock_bp, mock_agent)
        result = ctx.test_stability_with_current_prompt(num_trials=3)

        assert "UNSTABLE" in result


class TestRuntimeContextDifferentResult:
    """Tests for test_with_different_result method."""

    def test_different_result(self):
        """Test with hypothetical different result."""
        from connectonion.debug_explainer.explain_context import RuntimeContext

        mock_bp = Mock()
        mock_bp.tool_name = "search"
        mock_bp.next_actions = [{'name': 'save', 'args': {}}]
        mock_bp.trace_entry = {'result': 'Original result'}

        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [
                {'role': 'assistant', 'tool_calls': [
                    {'id': 'call_1', 'function': {'name': 'search'}}
                ]}
            ]
        }
        mock_agent.tools = []

        mock_response = Mock()
        mock_response.tool_calls = None
        mock_agent.llm.complete.return_value = mock_response

        ctx = RuntimeContext(mock_bp, mock_agent)
        result = ctx.test_with_different_result("Different result")

        assert "Current result" in result
        assert "If result was" in result


class TestRuntimeContextAnalyzeWhy:
    """Tests for analyze_why_this_tool method."""

    def test_analyze_why(self):
        """Test asking agent why it chose the tool."""
        from connectonion.debug_explainer.explain_context import RuntimeContext

        mock_bp = Mock()
        mock_bp.tool_name = "search"
        mock_bp.tool_args = {"query": "test"}

        mock_agent = Mock()
        mock_agent.current_session = {'messages': []}

        mock_response = Mock()
        mock_response.content = "I chose search because the user asked to find something"
        mock_agent.llm.complete.return_value = mock_response

        ctx = RuntimeContext(mock_bp, mock_agent)
        result = ctx.analyze_why_this_tool()

        assert result == "I chose search because the user asked to find something"
        mock_agent.llm.complete.assert_called_once()


class TestRuntimeContextRootCause:
    """Tests for analyze_root_cause method."""

    @patch('connectonion.debug_explainer.explain_context.llm_do')
    def test_analyze_root_cause(self, mock_llm_do):
        """Test root cause analysis."""
        from connectonion.debug_explainer.explain_context import RuntimeContext, RootCauseAnalysis

        mock_llm_do.return_value = RootCauseAnalysis(
            primary_cause_source="system_prompt",
            influential_text="Always search first",
            explanation="The system prompt directs to search",
            is_correct_choice=True,
            suggested_fix="None needed"
        )

        mock_bp = Mock()
        mock_bp.user_prompt = "Find something"
        mock_bp.tool_name = "search"
        mock_bp.tool_args = {}
        mock_bp.previous_tools = []

        mock_tool = Mock()
        mock_tool.name = "search"
        mock_agent = Mock()
        mock_agent.system_prompt = "Always search first"
        mock_agent.tools = [mock_tool]
        mock_agent.llm = Mock()
        mock_agent.llm.model = "gpt-4"

        ctx = RuntimeContext(mock_bp, mock_agent)
        result = ctx.analyze_root_cause()

        assert result.primary_cause_source == "system_prompt"
        assert mock_llm_do.called

    @patch('connectonion.debug_explainer.explain_context.llm_do')
    def test_analyze_root_cause_uses_agent_model(self, mock_llm_do):
        """Test root cause analysis uses agent's model."""
        from connectonion.debug_explainer.explain_context import RuntimeContext, RootCauseAnalysis

        mock_llm_do.return_value = RootCauseAnalysis(
            primary_cause_source="user_message",
            influential_text="Find",
            explanation="User asked to find",
            is_correct_choice=True,
            suggested_fix="None"
        )

        mock_bp = Mock()
        mock_bp.user_prompt = "Find"
        mock_bp.tool_name = "search"
        mock_bp.tool_args = {}
        mock_bp.previous_tools = []

        mock_agent = Mock()
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = []
        mock_agent.llm = Mock()
        mock_agent.llm.model = "claude-3-sonnet"

        ctx = RuntimeContext(mock_bp, mock_agent)
        result = ctx.analyze_root_cause()

        # Verify model was passed
        call_kwargs = mock_llm_do.call_args.kwargs
        assert call_kwargs.get('model') == "claude-3-sonnet"

