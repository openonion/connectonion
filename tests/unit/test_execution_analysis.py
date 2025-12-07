"""Unit tests for connectonion/execution_analyzer/execution_analysis.py

Tests cover:
- ExecutionAnalysis: Pydantic model for structured output
- analyze_execution: Post-execution analysis with AI suggestions
"""

import pytest
from unittest.mock import patch, Mock, MagicMock


class TestExecutionAnalysisModel:
    """Tests for ExecutionAnalysis Pydantic model."""

    def test_execution_analysis_model_creation(self):
        """Test creating ExecutionAnalysis with all fields."""
        from connectonion.execution_analyzer.execution_analysis import ExecutionAnalysis

        analysis = ExecutionAnalysis(
            task_completed=True,
            completion_explanation="Task was completed successfully",
            problems_identified=["No problems found"],
            system_prompt_suggestions=["Consider adding more specific instructions"],
            overall_quality="excellent",
            key_insights=["Agent made efficient tool choices"]
        )

        assert analysis.task_completed is True
        assert analysis.completion_explanation == "Task was completed successfully"
        assert analysis.overall_quality == "excellent"
        assert len(analysis.problems_identified) == 1
        assert len(analysis.key_insights) == 1

    def test_execution_analysis_model_fields(self):
        """Test ExecutionAnalysis has all required fields."""
        from connectonion.execution_analyzer.execution_analysis import ExecutionAnalysis

        # Check field names exist
        assert 'task_completed' in ExecutionAnalysis.__annotations__
        assert 'completion_explanation' in ExecutionAnalysis.__annotations__
        assert 'problems_identified' in ExecutionAnalysis.__annotations__
        assert 'system_prompt_suggestions' in ExecutionAnalysis.__annotations__
        assert 'overall_quality' in ExecutionAnalysis.__annotations__
        assert 'key_insights' in ExecutionAnalysis.__annotations__

    def test_execution_analysis_with_empty_lists(self):
        """Test creating ExecutionAnalysis with empty lists."""
        from connectonion.execution_analyzer.execution_analysis import ExecutionAnalysis

        analysis = ExecutionAnalysis(
            task_completed=False,
            completion_explanation="Task failed due to missing data",
            problems_identified=[],
            system_prompt_suggestions=[],
            overall_quality="poor",
            key_insights=[]
        )

        assert analysis.task_completed is False
        assert analysis.problems_identified == []
        assert analysis.system_prompt_suggestions == []


class TestAnalyzeExecution:
    """Tests for analyze_execution function."""

    @patch('connectonion.execution_analyzer.execution_analysis.llm_do')
    def test_analyze_execution_basic(self, mock_llm_do):
        """Test analyze_execution with basic inputs."""
        from connectonion.execution_analyzer.execution_analysis import analyze_execution, ExecutionAnalysis

        # Mock the LLM response
        mock_llm_do.return_value = ExecutionAnalysis(
            task_completed=True,
            completion_explanation="Task completed",
            problems_identified=[],
            system_prompt_suggestions=[],
            overall_quality="good",
            key_insights=["Efficient execution"]
        )

        # Create mock agent
        mock_agent = Mock()
        mock_agent.system_prompt = "You are a helpful assistant"
        mock_agent.tools = []
        mock_agent.llm = Mock()
        mock_agent.llm.model = "gpt-4"

        result = analyze_execution(
            user_prompt="Hello world",
            agent_instance=mock_agent,
            final_result="Hello! How can I help?",
            execution_trace=[],
            max_iterations_reached=False
        )

        assert result.task_completed is True
        assert mock_llm_do.called

    @patch('connectonion.execution_analyzer.execution_analysis.llm_do')
    def test_analyze_execution_with_tool_trace(self, mock_llm_do):
        """Test analyze_execution with tool execution trace."""
        from connectonion.execution_analyzer.execution_analysis import analyze_execution, ExecutionAnalysis

        mock_llm_do.return_value = ExecutionAnalysis(
            task_completed=True,
            completion_explanation="Completed with tools",
            problems_identified=[],
            system_prompt_suggestions=[],
            overall_quality="excellent",
            key_insights=[]
        )

        mock_agent = Mock()
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = []
        mock_agent.llm = Mock()
        mock_agent.llm.model = "gpt-4"

        trace = [
            {'type': 'tool_execution', 'tool_name': 'search', 'args': {'q': 'test'}, 'result': 'Found', 'status': 'success'},
            {'type': 'tool_execution', 'tool_name': 'save', 'args': {'data': 'x'}, 'result': 'Saved', 'status': 'success'}
        ]

        result = analyze_execution(
            user_prompt="Search and save",
            agent_instance=mock_agent,
            final_result="Done",
            execution_trace=trace,
            max_iterations_reached=False
        )

        assert result.task_completed is True
        # Verify llm_do was called with trace info
        call_args = mock_llm_do.call_args
        assert call_args is not None

    @patch('connectonion.execution_analyzer.execution_analysis.llm_do')
    def test_analyze_execution_max_iterations_reached(self, mock_llm_do):
        """Test analyze_execution when max iterations reached."""
        from connectonion.execution_analyzer.execution_analysis import analyze_execution, ExecutionAnalysis

        mock_llm_do.return_value = ExecutionAnalysis(
            task_completed=False,
            completion_explanation="Hit iteration limit",
            problems_identified=["Max iterations reached"],
            system_prompt_suggestions=["Increase max_iterations"],
            overall_quality="fair",
            key_insights=[]
        )

        mock_agent = Mock()
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = []
        mock_agent.llm = Mock()
        mock_agent.llm.model = "gpt-4"

        result = analyze_execution(
            user_prompt="Complex task",
            agent_instance=mock_agent,
            final_result="Incomplete",
            execution_trace=[],
            max_iterations_reached=True
        )

        assert result.task_completed is False
        # llm_do was called with max_iterations_reached info
        call_args = mock_llm_do.call_args
        data_arg = call_args[0][0]
        assert 'Max iterations reached: True' in data_arg

    @patch('connectonion.execution_analyzer.execution_analysis.llm_do')
    def test_analyze_execution_with_tools_list(self, mock_llm_do):
        """Test analyze_execution includes available tools in prompt."""
        from connectonion.execution_analyzer.execution_analysis import analyze_execution, ExecutionAnalysis

        mock_llm_do.return_value = ExecutionAnalysis(
            task_completed=True,
            completion_explanation="Done",
            problems_identified=[],
            system_prompt_suggestions=[],
            overall_quality="good",
            key_insights=[]
        )

        # Create mock tools
        mock_tool1 = Mock()
        mock_tool1.name = "search"
        mock_tool2 = Mock()
        mock_tool2.name = "calculate"

        mock_agent = Mock()
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = [mock_tool1, mock_tool2]
        mock_agent.llm = Mock()
        mock_agent.llm.model = "gpt-4"

        result = analyze_execution(
            user_prompt="Do something",
            agent_instance=mock_agent,
            final_result="Done",
            execution_trace=[],
            max_iterations_reached=False
        )

        # Verify tools were included in the data
        call_args = mock_llm_do.call_args
        data_arg = call_args[0][0]
        assert 'search' in data_arg
        assert 'calculate' in data_arg

    @patch('connectonion.execution_analyzer.execution_analysis.llm_do')
    def test_analyze_execution_uses_agent_model(self, mock_llm_do):
        """Test analyze_execution uses the same model as the agent."""
        from connectonion.execution_analyzer.execution_analysis import analyze_execution, ExecutionAnalysis

        mock_llm_do.return_value = ExecutionAnalysis(
            task_completed=True,
            completion_explanation="Done",
            problems_identified=[],
            system_prompt_suggestions=[],
            overall_quality="good",
            key_insights=[]
        )

        mock_agent = Mock()
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = []
        mock_agent.llm = Mock()
        mock_agent.llm.model = "claude-3-sonnet"

        result = analyze_execution(
            user_prompt="Test",
            agent_instance=mock_agent,
            final_result="Done",
            execution_trace=[],
            max_iterations_reached=False
        )

        # Verify model was passed to llm_do
        call_args = mock_llm_do.call_args
        assert call_args.kwargs.get('model') == "claude-3-sonnet"

    @patch('connectonion.execution_analyzer.execution_analysis.llm_do')
    def test_analyze_execution_failed_tool(self, mock_llm_do):
        """Test analyze_execution with failed tool execution."""
        from connectonion.execution_analyzer.execution_analysis import analyze_execution, ExecutionAnalysis

        mock_llm_do.return_value = ExecutionAnalysis(
            task_completed=False,
            completion_explanation="Tool failed",
            problems_identified=["search tool returned error"],
            system_prompt_suggestions=[],
            overall_quality="poor",
            key_insights=[]
        )

        mock_agent = Mock()
        mock_agent.system_prompt = "Helper"
        mock_agent.tools = []
        mock_agent.llm = Mock()
        mock_agent.llm.model = "gpt-4"

        trace = [
            {'type': 'tool_execution', 'tool_name': 'search', 'args': {}, 'result': 'Error: timeout', 'status': 'error'}
        ]

        result = analyze_execution(
            user_prompt="Search something",
            agent_instance=mock_agent,
            final_result="Failed",
            execution_trace=trace,
            max_iterations_reached=False
        )

        # Should include the failed tool status
        call_args = mock_llm_do.call_args
        data_arg = call_args[0][0]
        assert '✗' in data_arg  # Failed tool indicator

