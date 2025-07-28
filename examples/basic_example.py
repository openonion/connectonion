"""Basic example of using ConnectOnion Agent."""

import os
from connectonion import Agent
from connectonion.tools import Calculator, CurrentTime, ReadFile


def main():
    # Make sure to set your OpenAI API key
    # export OPENAI_API_KEY="your-api-key"
    
    # Create an agent with built-in tools
    agent = Agent(
        name="assistant",
        tools=[Calculator(), CurrentTime(), ReadFile()]
    )
    
    print("ConnectOnion Agent Example")
    print("=" * 50)
    
    # Example 1: Simple task without tools
    print("\n1. Simple greeting:")
    result = agent.run("Say hello and introduce yourself briefly")
    print(f"Result: {result}")
    
    # Example 2: Math calculation using Calculator tool
    print("\n2. Math calculation:")
    result = agent.run("What is 25 * 4 + 10?")
    print(f"Result: {result}")
    
    # Example 3: Getting current time
    print("\n3. Current time:")
    result = agent.run("What time is it right now?")
    print(f"Result: {result}")
    
    # Example 4: Complex task with multiple tool calls
    print("\n4. Complex calculation:")
    result = agent.run("Calculate the sum of 123 + 456, then multiply by 2, and tell me what time you did this calculation")
    print(f"Result: {result}")
    
    # Example 5: File reading (create a test file first)
    test_file = "test_file.txt"
    with open(test_file, "w") as f:
        f.write("Hello from ConnectOnion!\nThis is a test file.")
    
    print("\n5. File reading:")
    result = agent.run(f"Read the contents of {test_file} and tell me what it says")
    print(f"Result: {result}")
    
    # Clean up test file
    os.remove(test_file)
    
    # Show behavior summary
    print("\n" + "=" * 50)
    print("Behavior Summary:")
    print(agent.history.summary())
    
    # Show recent behaviors
    print("\nRecent behaviors:")
    for i, record in enumerate(agent.history.get_recent(3), 1):
        print(f"\n{i}. Task: {record.task}")
        print(f"   Time: {record.timestamp}")
        print(f"   Duration: {record.duration_seconds:.2f}s")
        if record.tool_calls:
            print(f"   Tools used: {[tc['name'] for tc in record.tool_calls]}")


if __name__ == "__main__":
    main()