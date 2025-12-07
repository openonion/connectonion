"""
Example demonstrating the event system (on_events parameter).

This example shows all event types:
1. after_user_input - fires once per turn
2. before_llm - fires before each LLM call
3. after_llm - fires after each LLM response
4. before_each_tool - fires before each tool execution
5. after_each_tool - fires after each tool execution (per-tool)
6. after_tools - fires once after ALL tools in a batch complete
7. on_error - fires when tool execution fails
8. on_complete - fires once after agent completes task

Note: Use after_tools (not after_each_tool) when adding messages to ensure
compatibility with all LLM providers (Anthropic Claude requires tool results to
immediately follow tool_calls).

Run with:
    python examples/events_example.py
"""

from connectonion import Agent, after_user_input, before_llm, after_llm, before_each_tool, after_each_tool, after_tools, on_error, on_complete, llm_do
from datetime import datetime


# Example 1: Simple event handlers for logging and monitoring
def log_user_input(agent: Agent) -> None:
    """Add timestamp when user provides input"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # System messages are for instructions/context from the system
    agent.current_session['messages'].append({
        'role': 'system',
        'content': f'Current timestamp: {timestamp}'
    })
    print(f"📝 Logged user input at {timestamp}")


def track_llm_calls(agent: Agent) -> None:
    """Track LLM performance"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'llm_call':
        duration = trace['duration_ms']
        print(f"⚡ LLM call completed in {duration:.0f}ms")


def monitor_tool_performance(agent: Agent) -> None:
    """Log slow tool executions"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        timing = trace['timing']
        if timing > 1000:  # Over 1 second
            print(f"⚠️  Slow tool detected: {trace['tool_name']} took {timing/1000:.1f}s")


def handle_errors(agent: Agent) -> None:
    """Custom error handling and recovery"""
    trace = agent.current_session['trace'][-1]
    if trace.get('status') in ('error', 'not_found'):
        error_msg = trace.get('error', 'Unknown error')
        print(f"❌ Error occurred: {error_msg}")

        # Could implement retry logic here
        # Could log to external monitoring system
        # Could add recovery instructions to messages


def log_completion(agent: Agent) -> None:
    """Log task completion with summary statistics"""
    trace = agent.current_session['trace']

    llm_calls = sum(1 for t in trace if t['type'] == 'llm_call')
    tool_calls = sum(1 for t in trace if t['type'] == 'tool_execution')
    errors = sum(1 for t in trace if t.get('status') == 'error')

    print(f"✅ Task complete: {llm_calls} LLM calls, {tool_calls} tools, {errors} errors")


# Example 2: AI-powered reflection after tools batch
def add_reflection(agent: Agent) -> None:
    """Use llm_do to generate reflection after all tools complete (uses after_tools)"""
    # Get the last tool execution from trace
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        result_preview = str(trace['result'])[:200]

        # Use llm_do to generate a quick reflection
        reflection = llm_do(
            f"In 1 sentence, reflect on this tool result: {result_preview}",
            model="gpt-4o-mini"
        )

        # Add reflection as assistant message (fires after tool result message is added)
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"💭 Reflection: {reflection}"
        })

        print(f"💭 Reflection: {reflection}")


# Example tools for demonstration
def search(query: str) -> str:
    """Search for information"""
    import time
    time.sleep(0.5)  # Simulate API delay
    return f"Found results for: {query}"


def slow_analysis(data: str) -> str:
    """Analyze data (slow operation)"""
    import time
    time.sleep(1.5)  # Simulate slow analysis
    return f"Analysis complete for: {data}"


def failing_tool(input: str) -> str:
    """Tool that sometimes fails"""
    if "error" in input.lower():
        raise ValueError("Intentional failure for demonstration")
    return f"Processed: {input}"


def main():
    """Run examples demonstrating event system"""

    print("\n" + "="*60)
    print("Example 1: Basic Event Monitoring")
    print("="*60 + "\n")

    # Create agent with monitoring events
    agent1 = Agent(
        name="monitor_agent",
        tools=[search, slow_analysis],
        model="gpt-4o-mini",
        on_events=[
            after_user_input(log_user_input),
            after_llm(track_llm_calls),
            after_each_tool(monitor_tool_performance)  # per-tool monitoring
        ]
    )

    result1 = agent1.input("Search for 'Python' and analyze the results")
    print(f"\nResult: {result1}\n")


    print("\n" + "="*60)
    print("Example 2: AI-Powered Reflection")
    print("="*60 + "\n")

    # Create agent with reflection (use after_tools to add messages safely)
    # Using after_tools ensures compatibility with all LLM providers
    agent2 = Agent(
        name="reflective_agent",
        tools=[search],
        model="gpt-4o-mini",
        on_events=[
            after_tools(add_reflection)  # batch event - safe to add messages
        ]
    )

    result2 = agent2.input("Search for 'artificial intelligence'")
    print(f"\nResult: {result2}\n")


    print("\n" + "="*60)
    print("Example 3: Error Handling")
    print("="*60 + "\n")

    # Create agent with error handling
    agent3 = Agent(
        name="error_handler_agent",
        tools=[failing_tool],
        model="gpt-4o-mini",
        on_events=[
            on_error(handle_errors)
        ]
    )

    result3 = agent3.input("Use failing_tool with input 'this will cause error'")
    print(f"\nResult: {result3}\n")


    print("\n" + "="*60)
    print("Example 4: Combining Per-Tool and Batch Events")
    print("="*60 + "\n")

    # Combine per-tool events (after_each_tool) with batch events (after_tools)
    # - after_each_tool: fires for EACH tool (good for monitoring)
    # - after_tools: fires ONCE after all tools (good for adding messages)
    agent4 = Agent(
        name="full_featured_agent",
        tools=[search, slow_analysis, failing_tool],
        model="gpt-4o-mini",
        on_events=[
            after_user_input(log_user_input),
            after_llm(track_llm_calls),
            after_each_tool(monitor_tool_performance),  # per-tool monitoring
            after_tools(add_reflection),                # batch reflection (adds message)
            on_error(handle_errors)
        ]
    )

    result4 = agent4.input("Search for 'machine learning', analyze it, then process 'success'")
    print(f"\nResult: {result4}\n")


    print("\n" + "="*60)
    print("Example 5: Task Completion with on_complete")
    print("="*60 + "\n")

    # Create agent with completion handler
    agent5 = Agent(
        name="completion_agent",
        tools=[search],
        model="gpt-4o-mini",
        on_events=[
            on_complete(log_completion)
        ]
    )

    result5 = agent5.input("Search for 'Python programming'")
    print(f"\nResult: {result5}\n")

    print("\n" + "="*60)
    print("All examples completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
