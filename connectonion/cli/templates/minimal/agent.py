"""Minimal ConnectOnion agent with a simple calculator tool."""

from connectonion import Agent


def calculator(expression: str) -> float:
    """Simple calculator that evaluates arithmetic expressions.

    Args:
        expression: A mathematical expression (e.g., "5*5", "10+20")

    Returns:
        The result of the calculation
    """
    # Note: eval() is used for simplicity. For production, use a safer parser.
    return eval(expression)


# Create agent with calculator tool
agent = Agent(
    name="calculator-agent", 
    system_prompt="pls use the calculator tool to answer math questions", # you can also pass a markdown file like system_prompt="path/to/your_markdown_file.md"
    tools=[calculator], # tools can be python classes or functions
    model="co/gpt-5" # co/gpt-5 is hosted by OpenOnion, you can write your api key to .env file and change this to "gpt-5"
)

# Run the agent
result = agent.input("what is the result of 5*5")
print(result)
