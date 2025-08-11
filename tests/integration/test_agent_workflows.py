"""Integration tests for agent workflows."""

import pytest
from unittest.mock import Mock, patch
from connectonion import Agent
from tests.fixtures.test_tools import Calculator, CurrentTime, ReadFile
from tests.utils.mock_helpers import (
    LLMResponseBuilder, 
    AgentWorkflowMocker,
    OpenAIMockBuilder
)


@pytest.mark.integration
class TestAgentWorkflows:
    """Test complete agent workflows end-to-end."""
    
    def test_simple_conversation_workflow(self, temp_dir):
        """Test agent handling simple conversation without tools."""
        # Mock LLM
        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponseBuilder.text_response(
            "Hello! I'm ConnectOnion, ready to help you with various tasks."
        )
        
        # Create agent
        agent = Agent(name="conversation_test", llm=mock_llm)
        agent.history.save_dir = temp_dir
        
        # Run task
        result = agent.input("Hello, introduce yourself")
        
        # Verify response
        assert "ConnectOnion" in result
        assert len(agent.history.records) == 1
        assert agent.history.records[0].user_prompt == "Hello, introduce yourself"
        assert len(agent.history.records[0].tool_calls) == 0
    
    def test_single_tool_workflow(self, temp_dir):
        """Test agent using a single tool."""
        # Mock LLM responses
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            LLMResponseBuilder.tool_call_response("calculator", {"expression": "25 * 4"}),
            LLMResponseBuilder.text_response("The result of 25 × 4 is 100.")
        ]
        
        # Create agent with calculator
        agent = Agent(name="single_tool_test", llm=mock_llm, tools=[Calculator()])
        agent.history.save_dir = temp_dir
        
        # Run calculation task
        result = agent.input("What is 25 times 4?")
        
        # Verify response
        assert "100" in result
        assert len(agent.history.records) == 1
        assert len(agent.history.records[0].tool_calls) == 1
        assert agent.history.records[0].tool_calls[0]["name"] == "calculator"
        assert agent.history.records[0].tool_calls[0]["status"] == "success"
    
    def test_multi_tool_chaining_workflow(self, temp_dir):
        """Test agent chaining multiple tools in sequence."""
        # Mock LLM responses
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            LLMResponseBuilder.tool_call_response("calculator", {"expression": "100 / 4"}),
            LLMResponseBuilder.tool_call_response("current_time", {}),
            LLMResponseBuilder.text_response("The result is 25.0, calculated at the current time.")
        ]
        
        # Create agent with multiple tools
        tools = [Calculator(), CurrentTime()]
        agent = Agent(name="multi_tool_test", llm=mock_llm, tools=tools)
        agent.history.save_dir = temp_dir
        
        # Run complex task
        result = agent.input("Calculate 100 divided by 4, then tell me what time you did this")
        
        # Verify response
        assert "25.0" in result
        assert len(agent.history.records) == 1
        assert len(agent.history.records[0].tool_calls) == 2
        
        # Verify tool call sequence
        tool_calls = agent.history.records[0].tool_calls
        assert tool_calls[0]["name"] == "calculator"
        assert tool_calls[1]["name"] == "current_time"
        assert all(call["status"] == "success" for call in tool_calls)
    
    def test_file_reading_workflow(self, temp_dir, test_files):
        """Test agent reading and processing files."""
        # Mock LLM responses
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            LLMResponseBuilder.tool_call_response("read_file", {"filepath": test_files["normal"]}),
            LLMResponseBuilder.text_response("The file contains a greeting: 'Hello, ConnectOnion!'")
        ]
        
        # Create agent with file reading capability
        agent = Agent(name="file_test", llm=mock_llm, tools=[ReadFile()])
        agent.history.save_dir = temp_dir
        
        # Run file reading task
        result = agent.input(f"Read the file {test_files['normal']} and tell me what it says")
        
        # Verify response
        assert "Hello, ConnectOnion!" in result
        assert len(agent.history.records) == 1
        assert agent.history.records[0].tool_calls[0]["result"] == "Hello, ConnectOnion!"
    
    def test_complex_multi_step_workflow(self, temp_dir, test_files):
        """Test complex workflow involving multiple tools and steps."""
        # Create a test file with numbers
        import os
        numbers_file = os.path.join(temp_dir, "numbers.txt")
        with open(numbers_file, "w") as f:
            f.write("First number: 15\nSecond number: 8")
        
        # Mock LLM responses for complex workflow
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            # Step 1: Read the file
            LLMResponseBuilder.tool_call_response("read_file", {"filepath": numbers_file}),
            # Step 2: Extract and calculate
            LLMResponseBuilder.tool_call_response("calculator", {"expression": "15 + 8"}),
            # Step 3: Get timestamp
            LLMResponseBuilder.tool_call_response("current_time", {}),
            # Step 4: Final response
            LLMResponseBuilder.text_response(
                "I read the file and found two numbers (15 and 8). "
                "Their sum is 23, calculated at the current time."
            )
        ]
        
        # Create agent with all tools
        tools = [ReadFile(), Calculator(), CurrentTime()]
        agent = Agent(name="complex_test", llm=mock_llm, tools=tools)
        agent.history.save_dir = temp_dir
        
        # Run complex task
        result = agent.input(
            f"Read the numbers from {numbers_file}, add them together, "
            "and tell me when you completed the calculation"
        )
        
        # Verify response
        assert "23" in result
        assert len(agent.history.records) == 1
        assert len(agent.history.records[0].tool_calls) == 3
        
        # Verify tool sequence
        tool_names = [call["name"] for call in agent.history.records[0].tool_calls]
        assert "read_file" in tool_names
        assert "calculator" in tool_names
        assert "current_time" in tool_names
    
    def test_iteration_limit_protection(self, temp_dir):
        """Test that agent doesn't get stuck in infinite tool calling loops."""
        # Mock LLM that keeps requesting the same tool
        mock_llm = Mock()
        # Create 15 identical tool call responses (more than the limit of 10)
        responses = [
            LLMResponseBuilder.tool_call_response("calculator", {"expression": "1 + 1"})
            for _ in range(15)
        ]
        mock_llm.complete.side_effect = responses
        
        # Create agent
        agent = Agent(name="iteration_test", llm=mock_llm, tools=[Calculator()])
        agent.history.save_dir = temp_dir
        
        # Run task
        result = agent.input("Keep calculating 1 + 1")
        
        # Should stop at max iterations
        assert "Maximum iterations reached" in result
        assert len(agent.history.records) == 1
        # Should have stopped at max iterations (10), not continue to 15
        assert len(agent.history.records[0].tool_calls) <= 10


@pytest.mark.integration
class TestErrorRecoveryWorkflows:
    """Test agent behavior during error scenarios."""
    
    def test_tool_execution_error_recovery(self, temp_dir):
        """Test agent handling tool execution errors gracefully."""
        # Mock LLM responses
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            # First: request invalid calculation
            LLMResponseBuilder.tool_call_response("calculator", {"expression": "invalid_expr"}),
            # Second: acknowledge error and try again
            LLMResponseBuilder.tool_call_response("calculator", {"expression": "2 + 2"}),
            # Third: provide final answer
            LLMResponseBuilder.text_response("After the error, I calculated 2 + 2 = 4.")
        ]
        
        # Create agent
        agent = Agent(name="error_recovery_test", llm=mock_llm, tools=[Calculator()])
        agent.history.save_dir = temp_dir
        
        # Run task
        result = agent.input("Calculate something")
        
        # Verify error recovery
        assert "4" in result
        assert len(agent.history.records) == 1
        assert len(agent.history.records[0].tool_calls) == 2
        
        # First call should have error status
        assert agent.history.records[0].tool_calls[0]["status"] == "error"
        # Second call should succeed
        assert agent.history.records[0].tool_calls[1]["status"] == "success"
    
    def test_unknown_tool_handling(self, temp_dir):
        """Test agent handling requests for unknown tools."""
        # Mock LLM requesting non-existent tool
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            LLMResponseBuilder.tool_call_response("unknown_tool", {"param": "value"}),
            LLMResponseBuilder.text_response("I apologize, that tool is not available.")
        ]
        
        # Create agent with limited tools
        agent = Agent(name="unknown_tool_test", llm=mock_llm, tools=[Calculator()])
        agent.history.save_dir = temp_dir
        
        # Run task
        result = agent.input("Use a special tool")
        
        # Verify unknown tool handling
        assert "not available" in result
        assert len(agent.history.records) == 1
        assert len(agent.history.records[0].tool_calls) == 1
        assert agent.history.records[0].tool_calls[0]["status"] == "not_found"
    
    def test_file_not_found_recovery(self, temp_dir):
        """Test agent handling file not found errors."""
        # Mock LLM responses
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            # Request to read non-existent file
            LLMResponseBuilder.tool_call_response("read_file", {"filepath": "/nonexistent/file.txt"}),
            # Acknowledge the error
            LLMResponseBuilder.text_response("I cannot read that file as it doesn't exist.")
        ]
        
        # Create agent
        agent = Agent(name="file_error_test", llm=mock_llm, tools=[ReadFile()])
        agent.history.save_dir = temp_dir
        
        # Run task
        result = agent.input("Read a file")
        
        # Verify error handling
        assert "doesn't exist" in result
        assert len(agent.history.records) == 1
        assert agent.history.records[0].tool_calls[0]["status"] == "error"
        assert "not found" in agent.history.records[0].tool_calls[0]["result"].lower()


@pytest.mark.integration
class TestConcurrentAgentOperations:
    """Test concurrent agent operations."""
    
    def test_multiple_agents_different_histories(self, temp_dir):
        """Test that multiple agents maintain separate histories."""
        import threading
        import time
        
        # Mock LLM
        mock_llm1 = Mock()
        mock_llm1.complete.return_value = LLMResponseBuilder.text_response("Agent 1 response")
        
        mock_llm2 = Mock()
        mock_llm2.complete.return_value = LLMResponseBuilder.text_response("Agent 2 response")
        
        # Create two agents
        agent1 = Agent(name="concurrent_agent_1", llm=mock_llm1)
        agent1.history.save_dir = temp_dir
        
        agent2 = Agent(name="concurrent_agent_2", llm=mock_llm2)
        agent2.history.save_dir = temp_dir
        
        # Results storage
        results = {}
        
        def run_agent(agent, task_id):
            result = agent.input(f"Task {task_id}")
            results[agent.name] = result
        
        # Run agents concurrently
        thread1 = threading.Thread(target=run_agent, args=(agent1, "A"))
        thread2 = threading.Thread(target=run_agent, args=(agent2, "B"))
        
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
        
        # Verify separate histories
        assert len(agent1.history.records) == 1
        assert len(agent2.history.records) == 1
        assert agent1.history.records[0].user_prompt == "Task A"
        assert agent2.history.records[0].user_prompt == "Task B"
        assert results["concurrent_agent_1"] == "Agent 1 response"
        assert results["concurrent_agent_2"] == "Agent 2 response"


@pytest.mark.slow
@pytest.mark.integration  
class TestLongRunningWorkflows:
    """Test long-running and resource-intensive workflows."""
    
    def test_many_sequential_tasks(self, temp_dir):
        """Test agent handling many sequential tasks."""
        # Mock LLM for multiple tasks
        mock_llm = Mock()
        responses = [
            LLMResponseBuilder.text_response(f"Completed task {i}")
            for i in range(20)
        ]
        mock_llm.complete.side_effect = responses
        
        # Create agent
        agent = Agent(name="sequential_test", llm=mock_llm)
        agent.history.save_dir = temp_dir
        
        # Run multiple tasks
        for i in range(20):
            result = agent.input(f"Task {i}")
            assert f"Completed task {i}" in result
        
        # Verify all tasks recorded
        assert len(agent.history.records) == 20
        for i, record in enumerate(agent.history.records):
            assert record.user_prompt == f"Task {i}"
    
    def test_large_tool_output_handling(self, temp_dir):
        """Test agent handling tools that produce large outputs."""
        # Create large file
        import os
        large_file = os.path.join(temp_dir, "huge.txt")
        with open(large_file, "w") as f:
            for i in range(10000):
                f.write(f"This is line {i} with substantial content to make the file large.\n")
        
        # Mock LLM response
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            LLMResponseBuilder.tool_call_response("read_file", {"filepath": large_file}),
            LLMResponseBuilder.text_response("I've read the large file successfully.")
        ]
        
        # Create agent
        agent = Agent(name="large_output_test", llm=mock_llm, tools=[ReadFile()])
        agent.history.save_dir = temp_dir
        
        # Run task
        result = agent.input("Read the large file")
        
        # Verify handling
        assert "successfully" in result
        assert len(agent.history.records) == 1
        # Tool result should contain the large content
        tool_result = agent.history.records[0].tool_calls[0]["result"]
        assert len(tool_result) > 100000  # Should be substantial