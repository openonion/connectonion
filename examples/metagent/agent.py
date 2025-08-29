"""Meta-Agent - Your ConnectOnion development assistant with documentation expertise"""

from connectonion import Agent
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def answer_connectonion_question(question: str) -> str:
    """Answer questions about ConnectOnion based on the embedded documentation.
    
    This is your primary tool for helping users understand ConnectOnion.
    Reads from the comprehensive docs in .co/docs/connectonion.md
    
    Args:
        question: Question about ConnectOnion (e.g., 'How do tools work?', 'What is xray?')
    """
    docs_path = ".co/docs/connectonion.md"
    
    try:
        with open(docs_path, 'r', encoding='utf-8') as f:
            docs = f.read()
    except FileNotFoundError:
        return "ConnectOnion documentation not found. Try running 'co init' again."
    
    # Search for relevant content in the documentation
    lines = docs.split('\n')
    
    # Look for the most relevant section
    relevant_sections = []
    current_section = []
    in_relevant_section = False
    
    keywords = question.lower().split()
    
    for i, line in enumerate(lines):
        # Check if this line contains relevant keywords
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in keywords if len(keyword) > 3):
            in_relevant_section = True
            # Include context before
            start = max(0, i - 3)
            for j in range(start, i):
                if lines[j] not in current_section:
                    current_section.append(lines[j])
        
        if in_relevant_section:
            current_section.append(line)
            
            # Stop at next major section or after collecting enough
            if len(current_section) > 40 or (line.startswith('##') and len(current_section) > 10):
                relevant_sections.append('\n'.join(current_section))
                current_section = []
                in_relevant_section = False
    
    # Add any remaining section
    if current_section:
        relevant_sections.append('\n'.join(current_section))
    
    if relevant_sections:
        doc_response = "Based on the ConnectOnion documentation:\n\n"
        doc_response += '\n\n---\n\n'.join(relevant_sections[:2])  # Return top 2 most relevant sections
        return doc_response
    else:
        # Provide overview if no specific match
        overview = '\n'.join(lines[:50])
        return f"Here's an overview of ConnectOnion:\n\n{overview}\n\n💡 Try asking about specific topics like 'tools', 'agents', 'xray', or 'system prompts'."


def create_agent_from_template(agent_name: str, template: str = "basic", description: str = "") -> str:
    """Create a new ConnectOnion agent from a template.
    
    Helps users quickly scaffold new agents for their projects.
    
    Args:
        agent_name: Name for the new agent (e.g., 'web_scraper', 'data_processor')
        template: Template type ('basic', 'tool', 'multi-tool')
        description: What this agent should do
    """
    templates = {
        "basic": '''from connectonion import Agent

def main_task(input: str) -> str:
    """Process the main task."""
    return f"Processing: {input}"

agent = Agent(
    name="{name}",
    system_prompt="You are a helpful {description} assistant.",
    tools=[main_task]
)

if __name__ == "__main__":
    result = agent.input("Hello!")
    print(result)
''',
        "tool": '''from connectonion import Agent

def {name}_tool(data: str) -> str:
    """{description}"""
    # Your implementation here
    result = f"Processed {data}"
    return result

agent = Agent(
    name="{name}",
    system_prompt="prompt.md",
    tools=[{name}_tool]
)
''',
        "multi-tool": '''from connectonion import Agent
from typing import List, Dict

def analyze(data: str) -> str:
    """Analyze the input data."""
    return f"Analysis complete: {data}"

def process(data: str, mode: str = "standard") -> str:
    """Process data with specified mode."""
    return f"Processed in {mode} mode: {data}"

def report(results: str, format: str = "text") -> str:
    """Generate a report from results."""
    return f"Report ({format}): {results}"

agent = Agent(
    name="{name}",
    system_prompt="prompt.md",
    tools=[analyze, process, report],
    max_iterations=15
)
'''
    }
    
    if template not in templates:
        return f"Unknown template '{template}'. Available: basic, tool, multi-tool"
    
    code = templates[template].format(
        name=agent_name.replace('-', '_').lower(),
        description=description or agent_name
    )
    
    filename = f"{agent_name.lower()}_agent.py"
    
    return f"📝 Agent template created:\n\nFilename: {filename}\n\n```python\n{code}\n```\n\nSave this code to {filename} and customize as needed."


def generate_tool_code(tool_name: str, parameters: str, description: str) -> str:
    """Generate ConnectOnion tool function code.
    
    Helps users create properly formatted tool functions.
    
    Args:
        tool_name: Name of the tool function
        parameters: Comma-separated parameters (e.g., 'url: str, timeout: int = 30')
        description: What this tool does
    """
    # Clean up the tool name
    clean_name = tool_name.replace('-', '_').replace(' ', '_').lower()
    
    # Parse parameters
    if not parameters:
        parameters = ""
    
    code = f'''def {clean_name}({parameters}) -> str:
    """{description}
    
    Args:
        # Add parameter descriptions here
    """
    # TODO: Implement your tool logic here
    
    # Example implementation:
    result = "Tool executed successfully"
    
    return result


# Add this tool to your agent:
# agent = Agent(
#     name="my_agent",
#     tools=[{clean_name}, ...other_tools]
# )'''
    
    return f"🔧 Tool function generated:\n\n```python\n{code}\n```\n\nThis tool follows ConnectOnion best practices:\n- ✅ Type hints on parameters\n- ✅ Returns string\n- ✅ Descriptive docstring\n- ✅ Ready to use with Agent"


def create_test_for_agent(agent_file: str = "agent.py") -> str:
    """Generate test code for a ConnectOnion agent.
    
    Creates pytest-compatible test cases.
    
    Args:
        agent_file: Path to the agent file to test
    """
    test_code = f'''"""Tests for {agent_file}"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from {agent_file.replace('.py', '')} import agent


class TestAgent:
    """Test suite for the agent."""
    
    def test_agent_initialization(self):
        """Test that agent initializes correctly."""
        assert agent.name is not None
        assert len(agent.tools) > 0
        assert agent.system_prompt is not None
    
    def test_agent_has_required_tools(self):
        """Test that agent has all required tools."""
        tool_names = agent.list_tools()
        assert len(tool_names) > 0
        # Add specific tool checks here
    
    @patch.dict(os.environ, {{"OPENAI_API_KEY": "test-key"}})
    def test_agent_input(self):
        """Test agent input processing."""
        with patch.object(agent.llm, 'call') as mock_call:
            # Mock the LLM response
            mock_call.return_value = "Test response"
            
            result = agent.input("Test query")
            assert result == "Test response"
            mock_call.assert_called_once()
    
    def test_tool_execution(self):
        """Test that tools execute correctly."""
        # Get first tool
        if agent.tools:
            tool = agent.tools[0]
            # Test tool execution
            # Adjust based on your tool's parameters
            try:
                result = tool.run()
                assert result is not None
            except TypeError:
                # Tool requires parameters
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
'''
    
    filename = f"test_{agent_file.replace('.py', '')}.py"
    
    return f"🧪 Test file generated:\n\nFilename: {filename}\n\n```python\n{test_code}\n```\n\nRun tests with: `pytest {filename}`"


def think(context: str = "current situation") -> str:
    """Reflect on the current task progress and determine next steps.
    
    This meta-cognitive tool helps analyze whether tasks are complete.
    
    Args:
        context: What to think about (e.g., 'task completion', 'next steps', 'current progress')
    """
    return f"Reflecting on {context}: Evaluating task progress and determining if additional steps are needed."


def generate_todo_list(task_description: str, priority: str = "normal") -> str:
    """Generate a structured to-do list for a given task.
    
    Breaks down complex tasks into actionable items.
    Uses GPT-4o-mini model for efficient list generation.
    
    Args:
        task_description: The task or project to create a to-do list for
        priority: Priority level ('high', 'normal', 'low')
    """
    # This would call GPT-4o-mini in production
    # For template, we provide a structured example
    
    todo_template = {
        "task": task_description,
        "priority": priority,
        "steps": [
            "1. Understand requirements",
            "2. Design the solution",
            "3. Implement core functionality",
            "4. Add error handling",
            "5. Write tests",
            "6. Document the code",
            "7. Review and refactor"
        ],
        "model_note": "Using gpt-4o-mini for efficient task breakdown"
    }
    
    return f"📝 To-Do List for '{task_description}':\n" + json.dumps(todo_template, indent=2)


def suggest_project_structure(project_type: str = "agent") -> str:
    """Suggest a project structure for ConnectOnion projects.
    
    Args:
        project_type: Type of project ('agent', 'multi-agent', 'tool-library', 'api')
    """
    structures = {
        "agent": """
📁 Suggested ConnectOnion Agent Project Structure:
```
my-agent/
├── agent.py           # Main agent implementation
├── prompt.md          # System prompt
├── tools/
│   ├── __init__.py
│   ├── core_tools.py  # Core tool implementations
│   └── helpers.py     # Helper utilities
├── tests/
│   ├── test_agent.py
│   └── test_tools.py
├── .env.example       # Environment template
├── .co/               # ConnectOnion metadata
│   └── docs/
├── requirements.txt   # Dependencies
└── README.md          # Project documentation
```
""",
        "multi-agent": """
📁 Multi-Agent System Structure:
```
multi-agent-system/
├── agents/
│   ├── __init__.py
│   ├── coordinator.py    # Main coordinator agent
│   ├── researcher.py     # Research agent
│   ├── analyzer.py       # Analysis agent
│   └── reporter.py       # Reporting agent
├── shared/
│   ├── tools.py         # Shared tools
│   └── prompts/         # Prompt templates
├── orchestrator.py      # Agent orchestration logic
├── tests/
└── .co/
```
""",
        "tool-library": """
📁 Tool Library Structure:
```
connectonion-tools/
├── tools/
│   ├── __init__.py
│   ├── web.py          # Web-related tools
│   ├── data.py         # Data processing tools
│   ├── file.py         # File operation tools
│   └── api.py          # API integration tools
├── examples/
│   └── example_agent.py
├── tests/
└── setup.py            # For distribution
```
""",
        "api": """
📁 API-Based Agent Structure:
```
api-agent/
├── app.py              # FastAPI/Flask app
├── agent.py            # ConnectOnion agent
├── api/
│   ├── routes.py       # API endpoints
│   └── models.py       # Request/response models
├── tools/
├── tests/
└── Dockerfile          # Container deployment
```
"""
    }
    
    return structures.get(project_type, structures["agent"]) + "\n💡 Use this structure as a starting point and adapt to your needs."


# Create the meta-agent with comprehensive ConnectOnion knowledge
agent = Agent(
    name="meta_agent",
    system_prompt="prompt.md",
    tools=[
        answer_connectonion_question,  # Primary documentation tool
        create_agent_from_template,     # Agent generation
        generate_tool_code,             # Tool code generation
        create_test_for_agent,          # Test generation
        think,                          # Self-reflection
        generate_todo_list,             # Task planning
        suggest_project_structure       # Project structure
    ],
    model="o4-mini",
    max_iterations=15  # More iterations for complex assistance
)


if __name__ == "__main__":
    print("🤖 ConnectOnion Meta-Agent initialized!")
    print("Your AI assistant for ConnectOnion development\n")
    print("Available capabilities:")
    print("📚 Documentation expert - Ask any question about ConnectOnion")
    print("🔧 Code generation - Create agents, tools, and tests")
    print("📝 Task planning - Break down complex projects")
    print("🏗️ Project structure - Get architecture recommendations")
    print("\nTry: 'How do tools work in ConnectOnion?'")
    print("     'Create a web scraper agent'")
    print("     'Generate a tool for sending emails'")

    # Interactive loop
    print("\nType 'exit' or 'quit' to end the conversation.")
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        if not user_input:
            continue
        assistant_reply = agent.input(user_input)
        print(f"\nAssistant: {assistant_reply}")