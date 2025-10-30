# ConnectOnion Agent Project

Welcome to your ConnectOnion agent project! This README will guide you through the project structure and how to get started.

## 🚀 Quick Start

1. **Add your OpenAI API key**:
   ```bash
   # Edit .env file (already created for you)
   # Replace 'sk-your-api-key-here' with your actual OpenAI API key
   nano .env  # or use any text editor
   ```

2. **Install dependencies**:
   ```bash
   pip install connectonion
   pip install python-dotenv  # For loading .env files
   ```

3. **Run your agent**:
   ```bash
   python agent.py
   ```

## 📁 Project Structure

```
your-project/
├── agent.py                    # Main agent implementation
├── prompts/                    # System prompts directory
│   ├── metagent.md            # Main system prompt
│   ├── docs_retrieve_prompt.md # Documentation retrieval prompt
│   ├── answer_prompt.md       # Answer generation prompt
│   └── think_prompt.md        # Reflection/thinking prompt
├── .env                       # Environment configuration (add your API key here)
├── .co/                       # ConnectOnion metadata
│   ├── config.toml           # Project configuration
│   ├── keys/                 # Agent cryptographic keys (git-ignored)
│   └── docs/
│       └── co-vibecoding-principles-docs-contexts-all-in-one.md  # Complete VibeCoding & framework docs
├── todo.md                    # To-do list (created by agent)
└── README.md                  # This file
```

## 🤖 About the Meta-Agent

The Meta-Agent is your AI assistant specialized in ConnectOnion development. It helps you:

- **Answer questions** about ConnectOnion using embedded documentation
- **Generate code** for agents, tools, and tests  
- **Plan projects** with structured to-do lists
- **Execute commands** cross-platform (bash/PowerShell)
- **Reflect and think** about task progress

## 🛠️ Available Tools

### Core Documentation Tools

- **`answer_connectonion_question(question)`** - Get expert answers about ConnectOnion
  - Uses `llm_do()` with intelligent document retrieval
  - Searches embedded documentation for relevant content
  - Provides accurate, context-aware responses

- **`extract_relevant_connectonion_text(question)`** - Extract relevant documentation
  - Internal helper for documentation retrieval
  - Uses GPT-4o-mini for intelligent extraction

### Task Management

- **`add_todo(task)`** - Add tasks to your to-do list
- **`delete_todo(task)`** - Remove completed tasks
- **`list_todos()`** - View current to-do list

### Reflection & Planning

- **`think(context)`** - AI reflection on current progress
  - Analyzes conversation history
  - Identifies accomplishments and blockers
  - Suggests next steps

### System Operations

- **`run_shell(command)`** - Execute shell commands
  - Cross-platform support (macOS/Linux/Windows)
  - Returns stdout, stderr, and exit codes
  - Configurable timeout (default: 120s)

## 🎯 How to Use the Agent

### Interactive Mode

Run the agent and interact via the command line:

```bash
python agent.py
```

Example interactions:
```
You: How do tools work in ConnectOnion?
Assistant: [Provides detailed explanation from documentation]

You: Create a to-do list for building a web scraper
Assistant: [Generates structured task list]

You: Run ls -la to see the files
Assistant: [Executes command and shows output]
```

### Programmatic Usage

Import and use the agent in your code:

```python
from agent import agent

# Ask a question
result = agent.input("How do I create custom tools?")
print(result)

# Execute multiple tasks
agent.input("Add todo: Research web scraping libraries")
agent.input("Add todo: Create prototype scraper")
todos = agent.input("List all todos")
print(todos)
```

## 📖 VibeCoding Documentation

The `.co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md` file contains complete VibeCoding principles and ConnectOnion framework documentation. This comprehensive guide includes:

- **Framework Overview**: Core concepts and architecture
- **Agent Development**: Building intelligent agents with tools
- **LLM Integration**: Using `llm_do()` for AI-powered functionality
- **Tool System**: Creating and using custom tools
- **Best Practices**: Design patterns and coding guidelines
- **API Reference**: Complete API documentation

### 🤖 Using with AI Coding Assistants

If you're using AI-powered coding assistants like **Cursor**, **Claude Code**, or **GitHub Copilot**, you can leverage the Vibe Coding documentation for better assistance:

1. **Point your AI assistant to the doc**: Reference `.co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md` when asking questions about ConnectOnion
2. **Get framework-specific help**: The documentation helps AI assistants understand ConnectOnion's patterns and best practices
3. **Consistent coding style**: AI assistants will follow the framework's conventions when generating code

Example prompt for your AI assistant:
```
Please read .co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md to understand 
the ConnectOnion framework and VibeCoding principles, then help me create a custom tool for [your task]
```

This documentation is embedded locally in your project for offline access. The Meta-Agent can also answer questions about ConnectOnion by referencing this documentation.

## 📚 Understanding the Architecture

### LLM Function (`llm_do`)

The Meta-Agent uses ConnectOnion's `llm_do()` function for intelligent operations:

```python
from connectonion import llm_do

# Simple usage
answer = llm_do("What's 2+2?")

# With structured output
from pydantic import BaseModel

class Analysis(BaseModel):
    sentiment: str
    confidence: float

result = llm_do(
    "I love this product!",
    output=Analysis
)
```

### System Prompts

Prompts are stored as markdown files for better maintainability:

- **`metagent.md`** - Main personality and capabilities
- **`docs_retrieve_prompt.md`** - Instructions for document extraction
- **`answer_prompt.md`** - Guidelines for answering questions
- **`think_prompt.md`** - Framework for reflection

### The Agent Loop

1. User provides input
2. Agent processes with LLM (GPT-4o-mini by default)
3. LLM decides which tools to call
4. Tools execute and return results
5. Process repeats up to `max_iterations` (15 for Meta-Agent)
6. Final response returned to user

## 🔧 Customization

### Modify Tools

Edit `agent.py` to add your own tools:

```python
def my_custom_tool(param: str) -> str:
    """Description for the LLM."""
    return f"Processed: {param}"

# Add to agent
agent = Agent(
    name="meta_agent",
    tools=[
        answer_connectonion_question,
        think,
        my_custom_tool,  # Your new tool
        # ... other tools
    ]
)
```

### Adjust Behavior

Modify system prompts in the `prompts/` directory to change agent personality and behavior.

### Change Models

Update the model parameter:

```python
agent = Agent(
    name="meta_agent",
    model="gpt-4",  # Use GPT-4 instead of GPT-4o-mini
    # ...
)
```

## 📖 Documentation Access

The embedded ConnectOnion documentation is available at:
`.co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md`

This comprehensive reference includes:
- Framework overview and concepts
- API reference
- Code examples
- Best practices
- Troubleshooting guide

The Meta-Agent automatically searches this documentation to answer your questions.

## 🐛 Debugging

Use the `@xray` decorator for debugging tools:

```python
from connectonion import xray

@xray
def debug_tool(text: str) -> str:
    print(f"Agent: {xray.agent.name}")
    print(f"Task: {xray.task}")
    print(f"Iteration: {xray.iteration}")
    return "Done"
```

## 🔗 Resources

- **GitHub**: https://github.com/openonion/connectonion
- **Documentation**: https://connectonion.com/docs
- **PyPI**: https://pypi.org/project/connectonion/
- **Discord**: https://discord.gg/4xfD9k8AUF

## 💡 Tips

1. **Start Simple**: Test basic commands before complex workflows
2. **Check Documentation**: Use `answer_connectonion_question()` for framework questions
3. **Track Progress**: Use the to-do tools to manage tasks
4. **Review Prompts**: Customize prompts for your specific needs
5. **Monitor Iterations**: Increase `max_iterations` for complex tasks

## 🤝 Contributing

Feel free to extend this agent with your own tools and improvements. Share your creations with the ConnectOnion community!

## 📝 License

This project uses ConnectOnion, which is open source. Check the main repository for license details.