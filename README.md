# ConnectOnion

A simple Python framework for creating AI agents that can use tools and track their behavior.

## 🚀 Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Basic Usage

```python
import os
from connectonion import Agent
from connectonion.tools import Calculator, CurrentTime

# Set your OpenAI API key
os.environ["OPENAI_API_KEY"] = "your-api-key-here"

# Create an agent with tools
agent = Agent(
    name="my_assistant",
    tools=[Calculator(), CurrentTime()]
)

# Run tasks
result = agent.run("What is 25 * 4?")
print(result)  # The agent will use the calculator tool

result = agent.run("What time is it?")
print(result)  # The agent will use the current time tool

# View behavior history
print(agent.history.summary())
```

## 🔧 Core Concepts

### Agent
The main class that orchestrates LLM calls and tool usage. Each agent:
- Has a unique name for tracking purposes
- Can use multiple tools
- Automatically records all behavior to JSON files

### Tools
Self-contained functions that agents can call. Built-in tools include:
- **Calculator**: Perform mathematical calculations
- **CurrentTime**: Get current date and time
- **ReadFile**: Read file contents

### History
Automatic tracking of all agent behaviors including:
- Tasks executed
- Tools called with parameters
- Results returned
- Execution time
- Persistent storage in `~/.connectonion/agents/{name}/behavior.json`

## 📦 Built-in Tools

### Calculator
```python
from connectonion.tools import Calculator

calc = Calculator()
result = calc.run(expression="2 + 2 * 3")  # Returns: "Result: 8"
```

### CurrentTime
```python
from connectonion.tools import CurrentTime

timer = CurrentTime()
result = timer.run()  # Returns current timestamp
result = timer.run(format="%Y-%m-%d")  # Returns date only
```

### ReadFile
```python
from connectonion.tools import ReadFile

reader = ReadFile()
result = reader.run(filepath="./example.txt")  # Returns file contents
```

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
agent = Agent(name="test", model="gpt-4")  # Default: gpt-3.5-turbo
```

## 🛠️ Advanced Usage

### Multiple Tool Calls
Agents can chain multiple tool calls automatically:
```python
result = agent.run(
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