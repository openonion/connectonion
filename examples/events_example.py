"""
Example demonstrating the event system (on_events parameter).

This example shows all 6 event types:
1. after_user_input - fires once per turn
2. before_llm - fires before each LLM call
3. after_llm - fires after each LLM response
4. before_tool - fires before each tool execution
5. after_tool - fires after successful tool execution
6. on_error - fires when tool execution fails

Run with:
    python examples/events_example.py
"""

from connectonion import Agent, after_user_input, before_llm, after_llm, before_tool, after_tool, on_error, llm_do
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


# Example 2: AI-powered reflection after LLM completes tool calling
def add_reflection(agent: Agent) -> None:
    """Use llm_do to generate reflection after tools are executed (fires after_llm)"""
    # Check if the last LLM call resulted in tool executions
    trace = agent.current_session['trace']

    # Find recent tool executions (skip the current LLM call at the end)
    recent_tools = []
    llm_count = 0
    for entry in reversed(trace):
        if entry.get('type') == 'llm_call':
            llm_count += 1
            if llm_count >= 2:
                # Stop at the second LLM call (before current one)
                break
        elif entry.get('type') == 'tool_execution' and entry.get('status') == 'success':
            recent_tools.append(entry)

    # If tools were executed between the last two LLM calls, add reflection
    if recent_tools:
        # Get the most recent tool result
        latest_tool = recent_tools[0]
        result_preview = str(latest_tool['result'])[:200]

        # Use llm_do to generate a quick reflection
        reflection = llm_do(
            f"In 1 sentence, reflect on this tool result: {result_preview}",
            model="gpt-4o-mini"
        )

        # Inject as ASSISTANT message AFTER all tool results are added
        # (after_llm fires after LLM response, tool execution, and tool result messages)
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
            after_tool(monitor_tool_performance)
        ]
    )

    result1 = agent1.input("Search for 'Python' and analyze the results")
    print(f"\nResult: {result1}\n")


    print("\n" + "="*60)
    print("Example 2: AI-Powered Reflection")
    print("="*60 + "\n")

    # Create agent with reflection (use after_llm to inject after tools are complete)
    agent2 = Agent(
        name="reflective_agent",
        tools=[search],
        model="gpt-4o-mini",
        on_events=[
            after_llm(add_reflection)
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
    print("Example 4: Multiple Events Combined")
    print("="*60 + "\n")

    # Create agent with multiple event types
    agent4 = Agent(
        name="full_featured_agent",
        tools=[search, slow_analysis, failing_tool],
        model="gpt-4o-mini",
        on_events=[
            after_user_input(log_user_input),
            after_llm(track_llm_calls),
            after_tool(monitor_tool_performance),
            on_error(handle_errors)
        ]
    )

    result4 = agent4.input("Search for 'machine learning', analyze it, then process 'success'")
    print(f"\nResult: {result4}\n")

    print("\n" + "="*60)
    print("All examples completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
