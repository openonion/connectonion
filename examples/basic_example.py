"""Basic example of using ConnectOnion Agent with simple function-based tools."""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path to import connectonion
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectonion import Agent


# 1. Define tools as simple functions
def search(query: str) -> str:
    """Search for information on the web."""
    # Simulate a search result
    return f"Found information about '{query}': This is a simulated search result with relevant details."

def calculate(expression: str) -> float:
    """Perform mathematical calculations safely."""
    try:
        # Only allow safe mathematical operations
        allowed_chars = "0123456789+-*/(). "
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Calculation result: {result}"
        else:
            return "Error: Invalid characters in expression. Only numbers and basic math operators allowed."
    except Exception as e:
        return f"Error: {str(e)}"

def current_time(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get the current date and time."""
    return datetime.now().strftime(format)

def write_file(filepath: str, content: str) -> str:
    """Write content to a text file."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote content to {filepath}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def main():
    # Make sure to set your OpenAI API key
    # export OPENAI_API_KEY="your-api-key"
    
    # 2. Create agent with simple function list - that's it!
    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant that can use tools to complete tasks.",
        tools=[search, calculate, current_time, write_file],
        max_iterations=8  # Standard for general purpose tasks
    )
    
    print("ConnectOnion Agent Example - Simple Function-Based Tools")
    print("=" * 60)
    
    # Example 1: Simple task without tools
    print("\n1. Simple greeting:")
    result = agent.input("Say hello and introduce yourself briefly")
    print(f"Result: {result}")
    
    # Example 2: Math calculation using calculate function
    print("\n2. Math calculation:")
    result = agent.input("What is 25 * 4 + 10?")
    print(f"Result: {result}")
    
    # Example 3: Getting current time
    print("\n3. Current time:")
    result = agent.input("What time is it right now?")
    print(f"Result: {result}")
    
    # Example 4: Search simulation
    print("\n4. Search example:")
    result = agent.input("Search for Python programming tutorials")
    print(f"Result: {result}")
    
    # Example 5: Complex task with multiple tool calls
    print("\n5. Complex task with multiple tools:")
    result = agent.input("Calculate the sum of 123 + 456, then multiply by 2, search for 'AI agents', and tell me what time you did this")
    print(f"Result: {result}")
    
    # Example 6: File operations
    test_file = "test_file.txt"
    print("\n6. File writing:")
    
    # Write a file
    result = agent.input(f"Write 'Hello from ConnectOnion!\\nThis is a test file with the current time.' to {test_file}")
    print(f"Write result: {result}")
    
    # Clean up test file
    if os.path.exists(test_file):
        os.remove(test_file)
    
    # Example 7: Adding tools dynamically
    print("\n7. Adding tools dynamically:")
    
    def random_number(min_val: int = 1, max_val: int = 100) -> str:
        """Generate a random number between min and max values."""
        import random
        num = random.randint(min_val, max_val)
        return f"Random number between {min_val} and {max_val}: {num}"
    
    # Add the new tool
    agent.add_tool(random_number)
    
    result = agent.input("Generate a random number between 1 and 50")
    print(f"Result: {result}")
    
    # Show behavior summary
    print("\n" + "=" * 60)
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