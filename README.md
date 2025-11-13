# 🧅 ConnectOnion

<div align="center">

[![Production Ready](https://img.shields.io/badge/Status-Production_Ready-success?style=flat-square)](https://connectonion.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue?style=flat-square&logo=python)](https://python.org)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/connectonion?period=total&units=international_system&left_color=black&right_color=green&left_text=downloads)](https://pepy.tech/projects/connectonion)
[![Discord](https://img.shields.io/badge/Discord-Join-7289DA?style=flat-square&logo=discord)](https://discord.gg/4xfD9k8AUF)
[![Documentation](https://img.shields.io/badge/Docs-docs.connectonion.com-blue?style=flat-square)](http://docs.connectonion.com)

**A simple, elegant open-source framework for production-ready AI agents**

[📚 Documentation](http://docs.connectonion.com) • [💬 Discord](https://discord.gg/4xfD9k8AUF) • [⭐ Star Us](https://github.com/openonion/connectonion)

</div>

---

> ## 🌟 Philosophy: "Keep simple things simple, make complicated things possible"
> 
> This is the core principle that drives every design decision in ConnectOnion.

## 🎯 Living Our Philosophy

```python
# Simple thing (2 lines) - Just works!
from connectonion import Agent
agent = Agent("assistant").input("Hello!")

# Complicated thing (still possible) - Production ready!
agent = Agent("production",
              model="gpt-5",                    # Latest models
              tools=[search, analyze, execute], # Your functions as tools
              system_prompt=company_prompt,     # Custom behavior
              max_iterations=10,                # Safety controls
              trust="prompt")                    # Multi-agent ready
```

## ✨ What Makes ConnectOnion Special

- **🎯 Simple API**: Just one `Agent` class and your functions as tools
- **🔌 Plugin System**: Add reflection & reasoning to any agent in one line
- **🔍 Interactive Debugging**: Pause at breakpoints with `@xray`, inspect state, modify variables on-the-fly
- **🚀 Production Ready**: Battle-tested with GPT-5, Gemini 2.5, Claude Opus 4.1
- **🌍 Open Source**: MIT licensed, community-driven development
- **⚡ No Boilerplate**: Start building in 2 lines, not 200
- **🔧 Extensible**: Scale from prototypes to production systems

## 🚀 Quick Start

### Installation

```bash
pip install connectonion
```

### Quickest Start - Use the CLI

```bash
# Create a new agent project with one command
co create my-agent

# Navigate and run
cd my-agent
python agent.py
```

*The CLI guides you through API key setup automatically. No manual `.env` editing needed!*

### Manual Usage

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
    # max_iterations=10 is the default - agent will try up to 10 tool calls per task
)

# 3. Use the agent
result = agent.input("What is 25 * 4?")
print(result)  # Agent will use the calculate function

result = agent.input("Search for Python tutorials") 
print(result)  # Agent will use the search function

# 4. View behavior history (automatic!)
print(agent.history.summary())
```

### 🔍 Interactive Debugging with `@xray`

Debug your agents like you debug code - pause at breakpoints, inspect variables, and test edge cases:

```python
from connectonion import Agent
from connectonion.decorators import xray

# Mark tools you want to debug with @xray
@xray
def search_database(query: str) -> str:
    """Search for information."""
    return f"Found 3 results for '{query}'"

@xray
def send_email(to: str, subject: str) -> str:
    """Send an email."""
    return f"Email sent to {to}"

# Create agent with @xray tools
agent = Agent(
    name="debug_demo",
    tools=[search_database, send_email]
)

# Launch interactive debugging session
agent.auto_debug()

# Or debug a specific task
agent.auto_debug("Search for Python tutorials and email the results")
```

**What happens at each `@xray` breakpoint:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@xray BREAKPOINT: search_database

Local Variables:
  query = "Python tutorials"
  result = "Found 3 results for 'Python tutorials'"

What do you want to do?
  → Continue execution 🚀       [c or Enter]
    Edit values 🔍             [e]
    Quit debugging 🚫          [q]

💡 Use arrow keys to navigate or type shortcuts
>
```

**Key features:**
- **Pause at breakpoints**: Tools decorated with `@xray` pause execution
- **Inspect state**: See all local variables and execution context
- **Edit variables**: Modify results to test "what if" scenarios
- **Full Python REPL**: Run any code to explore agent behavior
- **See next action**: Preview what the LLM plans to do next

Perfect for:
- Understanding why agents make certain decisions
- Testing edge cases without modifying code
- Exploring agent behavior interactively
- Debugging complex multi-tool workflows

[Learn more in the auto_debug guide](docs/auto_debug.md)

### 🔌 Plugin System

Package reusable capabilities as plugins and use them across multiple agents:

```python
from connectonion import Agent, after_tool, llm_do

# Define a reflection plugin
def add_reflection(agent):
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        result = trace['result']
        reflection = llm_do(
            f"Result: {result[:200]}\n\nWhat did we learn?",
            system_prompt="Be concise.",
            temperature=0.3
        )
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"🤔 {reflection}"
        })

# Plugin is just a list of event handlers
reflection = [after_tool(add_reflection)]

# Use across multiple agents
researcher = Agent("researcher", tools=[search], plugins=[reflection])
analyst = Agent("analyst", tools=[analyze], plugins=[reflection])
```

**What plugins provide:**
- **Reusable capabilities**: Package event handlers into bundles
- **Simple pattern**: A plugin is just a list of event handlers
- **Easy composition**: Combine multiple plugins together
- **Built-in examples**: Reflection, logging, todo tracking, and more

[Learn more about plugins](docs/plugin.md)

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

### Logging
Automatic logging of all agent activities including:
- User inputs and agent responses
- LLM calls with timing
- Tool executions with parameters and results
- Default storage in `.co/logs/{name}.log` (human-readable format)

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

## 🎨 CLI Templates

ConnectOnion CLI provides templates to get you started quickly:

```bash
# Create a minimal agent (default)
co create my-agent

# Create with specific template
co create my-playwright-bot --template playwright

# Initialize in existing directory
co init  # Adds .co folder only
co init --template playwright  # Adds full template
```

**Available Templates:**
- `minimal` (default) - Simple agent starter
- `playwright` - Web automation with browser tools

Each template includes:
- Pre-configured agent ready to run
- Automatic API key setup
- Embedded ConnectOnion documentation
- Git-ready `.gitignore`

Learn more in the [CLI Documentation](docs/cli.md) and [Templates Guide](docs/templates.md).

## 🔨 Creating Custom Tools

The simplest way is to use functions (recommended):

```python
def weather(city: str) -> str:
    """Get current weather for a city."""
    # Your weather API logic here
    return f"Weather in {city}: Sunny, 22°C"

# That's it! Use it directly
agent = Agent(name="weather_agent", tools=[weather])
```

Or use the Tool class for more control:

```python
from connectonion.tools import Tool

class WeatherTool(Tool):
    def __init__(self):
        super().__init__(
            name="weather",
            description="Get current weather for a city"
        )
    
    def run(self, city: str) -> str:
        return f"Weather in {city}: Sunny, 22°C"
    
    def get_parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }

agent = Agent(name="weather_agent", tools=[WeatherTool()])
```

## 📁 Project Structure

```
connectonion/
├── connectonion/
│   ├── __init__.py         # Main exports
│   ├── agent.py            # Agent class
│   ├── tools.py            # Tool interface and built-ins
│   ├── llm.py              # LLM interface and OpenAI implementation
│   ├── console.py          # Terminal output and logging
│   └── cli/                # CLI module
│       ├── main.py         # CLI commands
│       ├── docs.md         # Embedded documentation
│       └── templates/      # Agent templates
│           ├── basic_agent.py
│           ├── chat_agent.py
│           ├── data_agent.py
│           └── *.md        # Prompt templates
├── docs/                   # Documentation
│   ├── getting-started.md
│   ├── cli.md
│   ├── templates.md
│   └── ...
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

## 📊 Automatic Logging

All agent activities are automatically logged to:
```
.co/logs/{agent_name}.log  # Default location
```

Each log entry includes:
- Timestamp
- User input
- LLM calls with timing
- Tool executions with parameters and results
- Final responses

Control logging behavior:
```python
# Default: logs to .co/logs/assistant.log
agent = Agent("assistant")

# Log to current directory
agent = Agent("assistant", log=True)  # → assistant.log

# Disable logging
agent = Agent("assistant", log=False)

# Custom log file
agent = Agent("assistant", log="my_logs/custom.log")
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

### Iteration Control
Control how many tool calling iterations an agent can perform:

```python
# Default: 10 iterations (good for most tasks)
agent = Agent(name="assistant", tools=[...])

# Complex tasks may need more iterations
research_agent = Agent(
    name="researcher", 
    tools=[search, analyze, summarize, write_file],
    max_iterations=25  # Allow more steps for complex workflows
)

# Simple agents can use fewer iterations for safety
calculator = Agent(
    name="calc", 
    tools=[calculate],
    max_iterations=5  # Prevent runaway calculations
)

# Per-request override for specific complex tasks
result = agent.input(
    "Analyze all project files and generate comprehensive report",
    max_iterations=50  # Override for this specific task
)
```

When an agent reaches its iteration limit, it returns:
```
"Task incomplete: Maximum iterations (10) reached."
```

**Choosing the Right Limit:**
- **Simple tasks (1-3 tools)**: 5-10 iterations
- **Standard workflows**: 10-15 iterations (default: 10)
- **Complex analysis**: 20-30 iterations  
- **Research/multi-step**: 30+ iterations

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

## 🔗 Connect With Us

<div align="center">

[![Discord](https://img.shields.io/badge/Discord-Join_Community-5865F2?style=for-the-badge&logo=discord)](https://discord.gg/4xfD9k8AUF)
[![GitHub](https://img.shields.io/badge/GitHub-Star_Us-black?style=for-the-badge&logo=github)](https://github.com/openonion/connectonion)
[![Documentation](https://img.shields.io/badge/Docs-Learn_More-blue?style=for-the-badge)](http://docs.connectonion.com)

</div>

- **💬 Discord**: [Join our community](https://discord.gg/4xfD9k8AUF) - Get help, share ideas, meet other developers
- **📚 Documentation**: [docs.connectonion.com](http://docs.connectonion.com) - Comprehensive guides and examples
- **⭐ GitHub**: [Star the repo](https://github.com/openonion/connectonion) - Show your support
- **🐛 Issues**: [Report bugs](https://github.com/openonion/connectonion/issues) - We respond quickly

## 🤝 Contributing

We welcome contributions! ConnectOnion is open source and community-driven.

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

See our [Contributing Guide](http://docs.connectonion.com/website-maintenance) for more details.

## 📄 License

MIT License - Use it anywhere, even commercially. See [LICENSE](LICENSE) file for details.

---

<div align="center">

### 💫 Remember

## **"Keep simple things simple, make complicated things possible"**

*Built with ❤️ by the open-source community*

[⬆ Back to top](#-connectonion)

</div>