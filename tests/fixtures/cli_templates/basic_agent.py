"""Basic ConnectOnion Agent Template"""

from connectonion import Agent
import os


def explain_connectonion(topic: str = "overview") -> str:
    """Explain ConnectOnion concepts using the embedded documentation.
    
    Args:
        topic: What to explain (e.g., 'tools', 'agents', 'xray', 'prompts', 'overview')
    """
    # Read the embedded ConnectOnion documentation
    docs_path = ".co/docs/connectonion.md"
    
    try:
        with open(docs_path, 'r') as f:
            docs = f.read()
    except FileNotFoundError:
        return "ConnectOnion documentation not found. Try running 'co init' again."
    
    # If asking for overview, return the introduction
    if topic.lower() == "overview":
        lines = docs.split('\n')[:30]
        return '\n'.join(lines) + "\n\n💡 Ask me about specific topics like 'tools', 'agents', 'xray', or 'prompts'!"
    
    # Search for the topic in the documentation
    lines = docs.split('\n')
    relevant_lines = []
    capture = False
    
    for i, line in enumerate(lines):
        # Start capturing when we find the topic
        if topic.lower() in line.lower():
            capture = True
            # Include some context before
            start = max(0, i - 2)
            relevant_lines.extend(lines[start:i])
        
        if capture:
            relevant_lines.append(line)
            # Stop at next section or after 30 lines
            if len(relevant_lines) > 30 or (line.startswith('#') and len(relevant_lines) > 5):
                break
    
    if relevant_lines:
        return '\n'.join(relevant_lines)
    else:
        return f"I couldn't find information about '{topic}'. Try: tools, agents, prompts, xray, max_iterations, or debugging."


def get_time() -> str:
    """Get the current time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


# Create your agent
agent = Agent(
    name="my_agent",
    system_prompt="prompt.md",  # Load system prompt from markdown file
    tools=[explain_connectonion, get_time, calculate]
)


if __name__ == "__main__":
    # Example usage
    print("🤖 ConnectOnion Agent initialized!")
    print("Available tools:", agent.list_tools())
    
    # Interactive example
    result = agent.input("Tell me what time it is and explain what ConnectOnion is")
    print("\nAgent response:", result)