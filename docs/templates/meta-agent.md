# Meta-Agent Template

Development assistant that knows ConnectOnion. Query docs, run commands, manage tasks.

## Quick Start

```bash
co create dev-helper --template meta-agent
cd dev-helper
python agent.py
```

## What You Get

```
dev-helper/
├── agent.py            # Meta-agent with 7 tools
├── prompts/
│   ├── metagent.md           # Main system prompt
│   ├── answer_prompt.md      # Answer generation rules
│   ├── docs_retrieve_prompt.md  # Doc extraction prompt
│   └── think_prompt.md       # Reflection strategy
├── .env                # API keys
├── .co/
│   └── docs/           # ConnectOnion documentation
└── README.md           # Project docs
```

## Tools Included

| Tool | Description |
|------|-------------|
| `answer_connectonion_question(question)` | Search docs and answer ConnectOnion questions |
| `think(context)` | Self-reflection on current progress |
| `add_todo(task)` | Add task to todo.md |
| `delete_todo(task)` | Remove task from todo.md |
| `list_todos()` | View current todo list |
| `run_shell(command, timeout, cwd)` | Execute shell commands |

## Example Usage

```python
# Ask about ConnectOnion
result = agent.input("How do I add tools to an agent?")

# Get project planning help
result = agent.input("Create a todo list for building an email automation agent")

# Run shell commands
result = agent.input("Run 'pip list' to show installed packages")

# Reflect on progress
result = agent.input("Think about what we've accomplished so far")
```

Interactive mode:

```
You: How do events work in ConnectOnion?
Agent: [Searches embedded documentation]
       Events are lifecycle hooks that trigger at specific points...

You: Add a todo to implement the search feature
Agent: Added "Implement the search feature" to todo.md

You: Run pytest to check our tests
Agent: [Executes: pytest]
       All tests passed!
```

## Use Cases

- Learning ConnectOnion framework
- Development assistance
- Project planning with todos
- Running shell commands
- Code generation guidance
- Architecture questions

## Dependencies

- `connectonion`
- `python-dotenv`

## How It Works

### Documentation Search

The agent searches `.co/docs/connectonion.md` to answer framework questions:

1. Extracts relevant sections from docs
2. Uses LLM to formulate answer
3. Returns comprehensive response

### Todo Management

Tasks are stored in `todo.md`:

```markdown
# Todo

- [ ] Implement search feature
- [ ] Add unit tests
- [x] Setup project structure
```

### Shell Execution

Cross-platform shell commands:
- macOS/Linux: Uses bash
- Windows: Uses PowerShell

## Customization

### Add Project-Specific Knowledge

Add documentation to `.co/docs/` folder:

```
.co/docs/
├── connectonion.md     # Framework docs
├── project-guide.md    # Your project docs
└── api-reference.md    # Your API docs
```

### Modify System Prompts

Edit files in `prompts/` folder to customize behavior:

- `metagent.md` - Main personality and capabilities
- `answer_prompt.md` - How to answer questions
- `think_prompt.md` - Reflection strategy

### Add Custom Tools

```python
def deploy(environment: str = "staging") -> str:
    """Deploy the application."""
    # Your deployment logic
    return f"Deployed to {environment}"

agent = Agent(
    "meta-agent",
    tools=[..., deploy]
)
```

## Next Steps

- [Tools](../concepts/tools.md) - Add custom tools
- [Prompts](../concepts/prompts.md) - Customize agent behavior
- [XRay Debugging](../debug/xray.md) - Debug with @xray decorator
