"""
Purpose: Minimal agent template demonstrating basic ConnectOnion usage with a calculator tool
LLM-Note:
  Dependencies: imports from [connectonion.Agent] | template file copied by [cli/commands/init.py, cli/commands/create.py] | default template for 'co create' and 'co init'
  Data flow: user query → Agent.input() → calculator tool called if math expression → eval() computes result → returns answer
  State/Effects: no persistent state | single Agent.input() call | uses co/gemini-2.5-pro model (OpenOnion hosted)
  Integration: template for 'co create --template minimal' | demonstrates function-as-tool pattern | shows system_prompt and model configuration
  Performance: single LLM call | eval() is fast
  Errors: ⚠️ Security: uses eval() - for demo only, not production safe

Minimal ConnectOnion agent with a simple calculator tool.
"""

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
    model="co/gemini-2.5-pro" # co/gemini-2.5-pro is hosted by OpenOnion, you can use your own API key by setting OPENAI_API_KEY in .env
)

# Run the agent
result = agent.input("what is the result of 5*5")
print(result)
