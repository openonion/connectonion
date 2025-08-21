"""Basic ConnectOnion Agent Template"""

from connectonion import Agent


def hello(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}! Welcome to ConnectOnion."


def calculate(expression: str) -> str:
    """Perform basic mathematical calculations."""
    try:
        # Only allow safe mathematical operations
        allowed_chars = "0123456789+-*/(). "
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Calculation result: {result}"
        else:
            return "Error: Invalid characters in expression"
    except Exception as e:
        return f"Math error: {str(e)}"


def get_time() -> str:
    """Get the current time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Create your agent
agent = Agent(
    name="my_agent",
    system_prompt="prompt.md",  # Load system prompt from markdown file
    tools=[hello, calculate, get_time]
)


if __name__ == "__main__":
    # Example usage
    print("🤖 ConnectOnion Agent initialized!")
    print("Available tools:", agent.list_tools())
    
    # Interactive example
    result = agent.input("Say hello to the world and tell me what time it is")
    print("\nAgent response:", result)