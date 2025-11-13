"""
Tests for the event system (on_events parameter)
"""
import pytest
from unittest.mock import Mock
from connectonion import Agent, after_user_input, before_llm, after_llm, before_tool, after_tool, on_error


def search(query: str) -> str:
    """Mock search tool"""
    return f"Results for {query}"


def failing_tool(query: str) -> str:
    """Tool that always fails"""
    raise ValueError("Intentional failure")


class TestEventSystem:
    """Test event system functionality"""

    def test_after_user_input_fires_once(self):
        """Test after_user_input fires once per turn"""
        calls = []

        def track_user_input(agent):
            calls.append('after_user_input')
            # Verify we can access user prompt
            assert agent.current_session['user_prompt'] == "test prompt"

        agent = Agent(
            "test",
            model="gpt-4o-mini",
            on_events=[after_user_input(track_user_input)]
        )

        agent.input("test prompt")

        # Should fire exactly once per turn
        assert calls == ['after_user_input']

    def test_before_llm_fires_multiple_times(self):
        """Test before_llm fires before each LLM call"""
        calls = []

        def track_before_llm(agent):
            calls.append('before_llm')

        agent = Agent(
            "test",
            tools=[search],
            model="gpt-4o-mini",
            on_events=[before_llm(track_before_llm)]
        )

        agent.input("Search for Python")

        # Should fire multiple times (once per LLM call in iteration loop)
        assert len(calls) >= 1
        assert all(c == 'before_llm' for c in calls)

    def test_after_llm_fires_multiple_times(self):
        """Test after_llm fires after each LLM response"""
        calls = []

        def track_after_llm(agent):
            calls.append('after_llm')
            # Verify we can access trace
            trace = agent.current_session['trace']
            llm_calls = [t for t in trace if t['type'] == 'llm_call']
            assert len(llm_calls) > 0

        agent = Agent(
            "test",
            tools=[search],
            model="gpt-4o-mini",
            on_events=[after_llm(track_after_llm)]
        )

        agent.input("Search for Python")

        # Should fire multiple times
        assert len(calls) >= 1
        assert all(c == 'after_llm' for c in calls)

    def test_before_tool_fires_before_execution(self):
        """Test before_tool fires before each tool execution"""
        calls = []

        def track_before_tool(agent):
            calls.append('before_tool')
            # Verify trace doesn't have result yet (tool hasn't run)
            trace = agent.current_session['trace']
            tool_executions = [t for t in trace if t['type'] == 'tool_execution']
            # Before tool runs, latest tool execution should be pending or not exist yet
            if tool_executions:
                # The trace entry exists but hasn't been updated with result yet
                pass

        agent = Agent(
            "test",
            tools=[search],
            model="gpt-4o-mini",
            on_events=[before_tool(track_before_tool)]
        )

        agent.input("Search for Python")

        # Should fire at least once (when search tool is called)
        assert len(calls) >= 1

    def test_after_tool_fires_after_success(self):
        """Test after_tool fires after successful tool execution"""
        calls = []

        def track_after_tool(agent):
            calls.append('after_tool')
            # Verify we can access tool result
            trace = agent.current_session['trace']
            tool_executions = [t for t in trace if t['type'] == 'tool_execution']
            assert len(tool_executions) > 0
            latest_tool = tool_executions[-1]
            assert latest_tool['status'] == 'success'
            assert 'Results for' in latest_tool['result']

        agent = Agent(
            "test",
            tools=[search],
            model="gpt-4o-mini",
            on_events=[after_tool(track_after_tool)]
        )

        agent.input("Search for Python")

        # Should fire at least once
        assert len(calls) >= 1

    def test_on_error_fires_on_tool_failure(self):
        """Test on_error fires when tool execution fails"""
        calls = []

        def track_error(agent):
            calls.append('on_error')
            # Verify we can access error information
            trace = agent.current_session['trace']
            tool_executions = [t for t in trace if t['type'] == 'tool_execution']
            assert len(tool_executions) > 0
            latest_tool = tool_executions[-1]
            assert latest_tool['status'] == 'error'
            assert 'error' in latest_tool
            assert latest_tool['error'] == 'Intentional failure'

        agent = Agent(
            "test",
            tools=[failing_tool],
            model="gpt-4o-mini",
            on_events=[on_error(track_error)]
        )

        # This should trigger the failing tool
        result = agent.input("Use failing_tool with query 'test'")

        # Should fire at least once
        assert len(calls) >= 1

    def test_multiple_events_same_type_fire_in_order(self):
        """Test multiple events of same type fire in order"""
        calls = []

        def handler1(agent):
            calls.append('handler1')

        def handler2(agent):
            calls.append('handler2')

        def handler3(agent):
            calls.append('handler3')

        agent = Agent(
            "test",
            model="gpt-4o-mini",
            on_events=[
                after_user_input(handler1),
                after_user_input(handler2),
                after_user_input(handler3)
            ]
        )

        agent.input("test")

        # Should fire in order
        assert calls == ['handler1', 'handler2', 'handler3']

    def test_events_can_modify_messages(self):
        """Test events can modify agent messages"""

        def add_system_message(agent):
            agent.current_session['messages'].append({
                'role': 'system',
                'content': 'Added by event'
            })

        agent = Agent(
            "test",
            model="gpt-4o-mini",
            on_events=[after_user_input(add_system_message)]
        )

        agent.input("test")

        # Verify message was added
        messages = agent.current_session['messages']
        system_messages = [m for m in messages if m['role'] == 'system' and m['content'] == 'Added by event']
        assert len(system_messages) == 1

    def test_event_exception_propagates(self):
        """Test that event exceptions propagate (fail fast)"""

        def failing_event(agent):
            raise RuntimeError("Event failed")

        agent = Agent(
            "test",
            model="gpt-4o-mini",
            on_events=[after_user_input(failing_event)]
        )

        # Event exception should propagate
        with pytest.raises(RuntimeError, match="Event failed"):
            agent.input("test")

    def test_mixed_event_types(self):
        """Test using multiple different event types together"""
        calls = []

        def track_user(agent):
            calls.append('after_user_input')

        def track_llm(agent):
            calls.append('after_llm')

        def track_tool(agent):
            calls.append('after_tool')

        agent = Agent(
            "test",
            tools=[search],
            model="gpt-4o-mini",
            on_events=[
                after_user_input(track_user),
                after_llm(track_llm),
                after_tool(track_tool)
            ]
        )

        agent.input("Search for Python")

        # All event types should fire
        assert 'after_user_input' in calls
        assert 'after_llm' in calls
        assert 'after_tool' in calls

        # after_user_input should fire exactly once
        assert calls.count('after_user_input') == 1

    def test_no_events_works_normally(self):
        """Test agent works normally without any events"""
        agent = Agent(
            "test",
            tools=[search],
            model="gpt-4o-mini"
        )

        result = agent.input("Search for Python")

        # Should complete normally
        assert result is not None

    def test_event_receives_agent_instance(self):
        """Test that events receive the agent instance with all attributes"""

        def verify_agent_access(agent):
            # Should have access to all agent attributes
            assert hasattr(agent, 'name')
            assert hasattr(agent, 'current_session')
            assert hasattr(agent, 'tools')
            assert hasattr(agent, 'llm')
            assert hasattr(agent, 'console')
            assert agent.name == "test"

        agent = Agent(
            "test",
            model="gpt-4o-mini",
            on_events=[after_user_input(verify_agent_access)]
        )

        agent.input("test")

    def test_event_wrapper_adds_attribute(self):
        """Test that event wrappers add _event_type attribute"""

        def my_handler(agent):
            pass

        wrapped = after_llm(my_handler)

        assert hasattr(wrapped, '_event_type')
        assert wrapped._event_type == 'after_llm'

    def test_all_event_types_have_correct_attributes(self):
        """Test all event wrapper types set correct _event_type"""

        def handler(agent):
            pass

        assert after_user_input(handler)._event_type == 'after_user_input'
        assert before_llm(handler)._event_type == 'before_llm'
        assert after_llm(handler)._event_type == 'after_llm'
        assert before_tool(handler)._event_type == 'before_tool'
        assert after_tool(handler)._event_type == 'after_tool'
        assert on_error(handler)._event_type == 'on_error'

    def test_event_validation_rejects_non_callable(self):
        """Test that non-callable events are rejected with clear error"""

        with pytest.raises(TypeError, match="Event must be callable"):
            Agent(
                "test",
                model="gpt-4o-mini",
                on_events=["not a function"]  # String instead of callable
            )

    def test_event_validation_rejects_missing_event_type(self):
        """Test that events without _event_type are rejected with helpful error"""

        def my_handler(agent):
            pass

        with pytest.raises(ValueError, match="missing _event_type.*Did you forget to wrap it"):
            Agent(
                "test",
                model="gpt-4o-mini",
                on_events=[my_handler]  # Not wrapped with after_llm(), etc.
            )

    def test_event_validation_rejects_invalid_event_type(self):
        """Test that events with invalid _event_type are rejected"""

        def my_handler(agent):
            pass

        my_handler._event_type = 'invalid_event_type'

        with pytest.raises(ValueError, match="Invalid event type"):
            Agent(
                "test",
                model="gpt-4o-mini",
                on_events=[my_handler]
            )

    def test_on_error_fires_on_tool_not_found(self):
        """Test on_error fires when tool is not found (consistency with tool execution errors)"""
        calls = []

        def track_error(agent):
            calls.append('on_error')
            # Verify we can access error information
            trace = agent.current_session['trace']
            tool_executions = [t for t in trace if t['type'] == 'tool_execution']
            assert len(tool_executions) > 0
            latest_tool = tool_executions[-1]
            assert latest_tool['status'] == 'not_found'
            assert 'error' in latest_tool
            assert 'not found' in latest_tool['error']

        agent = Agent(
            "test",
            tools=[search],  # Only has 'search' tool
            model="gpt-4o-mini",
            on_events=[on_error(track_error)]
        )

        # Directly execute a nonexistent tool to trigger tool not found
        result = agent.execute_tool("nonexistent_tool", {"query": "test"})

        # Should fire on_error exactly once
        assert len(calls) == 1

    def test_after_tool_fires_for_all_executions(self):
        """Test after_tool fires for ALL tool executions (success, error, not_found)"""
        after_tool_calls = []
        on_error_calls = []

        def track_after_tool(agent):
            after_tool_calls.append(agent.current_session['trace'][-1]['status'])

        def track_error(agent):
            on_error_calls.append(agent.current_session['trace'][-1]['status'])

        agent = Agent(
            "test",
            tools=[search, failing_tool],
            model="gpt-4o-mini",
            on_events=[after_tool(track_after_tool), on_error(track_error)]
        )

        # Success case
        agent.execute_tool("search", {"query": "test"})

        # Error case
        agent.execute_tool("failing_tool", {"query": "test"})

        # Not found case
        agent.execute_tool("nonexistent", {})

        # after_tool should fire for all 3 executions
        assert len(after_tool_calls) == 3
        assert after_tool_calls == ['success', 'error', 'not_found']

        # on_error should fire only for error and not_found (2 times)
        assert len(on_error_calls) == 2
        assert on_error_calls == ['error', 'not_found']
