# ConnectOnion

> **🚧 Private Beta** - ConnectOnion is currently in private beta. [Join our waitlist](https://connectonion.com) to get early access!

A simple Python framework for creating AI agents that can use tools and track their behavior.

## ✨ What's New

- **🎯 Function-Based Tools**: Just write regular Python functions - no classes needed!
- **🎭 System Prompts**: Define your agent's personality and role  
- **🔄 Automatic Conversion**: Functions become OpenAI-compatible tools automatically
- **📝 Smart Schema Generation**: Type hints become function schemas

## 🚀 Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Basic Usage

```python
import os  
from connectonion import Agent

# Set your OpenAI API key
os.environ["OPENAI_API_KEY"] = "your-api-key-here"

# 1. Define tools as simple functions
def search(query: str) -> str:
    """Search for information."""
    return f"Found information about {query}"

def calculate(expression: str) -> float:
    """Perform mathematical calculations."""
    return eval(expression)  # Use safely in production

# 2. Create an agent with tools and personality
agent = Agent(
    name="my_assistant",
    system_prompt="You are a helpful and friendly assistant.",
    tools=[search, calculate]
)

# 3. Use the agent
result = agent.input("What is 25 * 4?")
print(result)  # Agent will use the calculate function

result = agent.input("Search for Python tutorials") 
print(result)  # Agent will use the search function

# 4. View behavior history (automatic!)
print(agent.history.summary())
```

## 🔧 Core Concepts

### Agent
The main class that orchestrates LLM calls and tool usage. Each agent:
- Has a unique name for tracking purposes
- Can be given a custom personality via `system_prompt`
- Automatically converts functions to tools
- Records all behavior to JSON files

### Function-Based Tools
**NEW**: Just write regular Python functions! ConnectOnion automatically converts them to tools:

```python
def my_tool(param: str, optional_param: int = 10) -> str:
    """This docstring becomes the tool description."""
    return f"Processed {param} with value {optional_param}"

# Use it directly - no wrapping needed!
agent = Agent("assistant", tools=[my_tool])
```

Key features:
- **Automatic Schema Generation**: Type hints become OpenAI function schemas
- **Docstring Integration**: First line becomes tool description  
- **Parameter Handling**: Supports required and optional parameters
- **Type Conversion**: Handles different return types automatically

### System Prompts
Define your agent's personality and behavior with flexible input options:

```python
# 1. Direct string prompt
agent = Agent(
    name="helpful_tutor",
    system_prompt="You are an enthusiastic teacher who loves to educate.",
    tools=[my_tools]
)

# 2. Load from file (any text file, no extension restrictions)
agent = Agent(
    name="support_agent",
    system_prompt="prompts/customer_support.md"  # Automatically loads file content
)

# 3. Using Path object
from pathlib import Path
agent = Agent(
    name="coder",
    system_prompt=Path("prompts") / "senior_developer.txt"
)

# 4. None for default prompt
agent = Agent("basic_agent")  # Uses default: "You are a helpful assistant..."
```

Example prompt file (`prompts/customer_support.md`):
```markdown
# Customer Support Agent

You are a senior customer support specialist with expertise in:
- Empathetic communication
- Problem-solving
- Technical troubleshooting

## Guidelines
- Always acknowledge the customer's concern first
- Look for root causes, not just symptoms
- Provide clear, actionable solutions
```

### History
Automatic tracking of all agent behaviors including:
- Tasks executed
- Tools called with parameters and results
- Agent responses and execution time
- Persistent storage in `~/.connectonion/agents/{name}/behavior.json`

## 🎯 Example Tools

You can still use the traditional Tool class approach, but the new functional approach is much simpler:

### Traditional Tool Classes (Still Supported)
```python
from connectonion.tools import Calculator, CurrentTime, ReadFile

agent = Agent("assistant", tools=[Calculator(), CurrentTime(), ReadFile()])
```

### New Function-Based Approach (Recommended)
```python
def calculate(expression: str) -> float:
    """Perform mathematical calculations."""
    return eval(expression)  # Use safely in production

def get_time(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get current date and time."""
    from datetime import datetime
    return datetime.now().strftime(format)

def read_file(filepath: str) -> str:
    """Read contents of a text file."""
    with open(filepath, 'r') as f:
        return f.read()

# Use them directly!
agent = Agent("assistant", tools=[calculate, get_time, read_file])
```

The function-based approach is simpler, more Pythonic, and easier to test!

## 🔨 Creating Custom Tools

```python
from connectonion.tools import Tool

class WeatherTool(Tool):
    def __init__(self):
        super().__init__(
            name="weather",
            description="Get current weather for a city"
        )
    
    def run(self, city: str) -> str:
        # Your weather API logic here
        return f"Weather in {city}: Sunny, 22°C"
    
    def get_parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Name of the city"
                }
            },
            "required": ["city"]
        }

# Use with agent
agent = Agent(name="weather_agent", tools=[WeatherTool()])
```

## 📁 Project Structure

```
connectonion/
├── connectonion/
│   ├── __init__.py     # Main exports
│   ├── agent.py        # Agent class
│   ├── tools.py        # Tool interface and built-ins
│   ├── llm.py          # LLM interface and OpenAI implementation
│   └── history.py      # Behavior tracking
├── examples/
│   └── basic_example.py
├── tests/
│   └── test_agent.py
└── requirements.txt
```

## 🧪 Running Tests

```bash
python -m pytest tests/
```

Or run individual test files:

```bash
python -m unittest tests.test_agent
```

## 📊 Behavior Tracking

All agent behaviors are automatically tracked and saved to:
```
~/.connectonion/agents/{agent_name}/behavior.json
```

Each record includes:
- Timestamp
- Task description
- Tool calls with parameters and results
- Final result
- Execution duration

View behavior summary:
```python
print(agent.history.summary())
# Agent: my_assistant
# Total tasks completed: 5
# Total tool calls: 8
# Total execution time: 12.34 seconds
# History file: ~/.connectonion/agents/my_assistant/behavior.json
# 
# Tool usage:
#   calculator: 5 calls
#   current_time: 3 calls
```

## 🔑 Configuration

### OpenAI API Key
Set your API key via environment variable:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

Or pass directly to agent:
```python
agent = Agent(name="test", api_key="your-api-key-here")
```

### Model Selection
```python
agent = Agent(name="test", model="gpt-5")  # Default: gpt-5-mini
```

## 🛠️ Advanced Usage

### Multiple Tool Calls
Agents can chain multiple tool calls automatically:
```python
result = agent.input(
    "Calculate 15 * 8, then tell me what time you did this calculation"
)
# Agent will use calculator first, then current_time tool
```

### Custom LLM Providers
```python
from connectonion.llm import LLM

class CustomLLM(LLM):
    def complete(self, messages, tools=None):
        # Your custom LLM implementation
        pass

agent = Agent(name="test", llm=CustomLLM())
```

## 🚧 Current Limitations (MVP)

This is an MVP version with intentional limitations:
- Single LLM provider (OpenAI)
- Synchronous execution only
- JSON file storage only
- Basic error handling
- No multi-agent collaboration

## 🗺️ Future Roadmap

- Multiple LLM provider support (Anthropic, Local models)
- Async/await support
- Database storage options
- Advanced memory systems
- Multi-agent collaboration
- Web interface for behavior monitoring
- Plugin system for tools

## 📄 License

MIT License - see LICENSE file for details.

## 🤝 Contributing

This is an MVP. For the full version roadmap:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📞 Support

For issues and questions:
- Create an issue on GitHub
- Check the examples/ directory for usage patterns
- Review the test files for implementation details