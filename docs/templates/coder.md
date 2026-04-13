# Coder Template

An agent with filesystem and shell access for coding tasks — read, edit, search, and run code.

## Quick Start

```bash
co create my-coder --template coder
cd my-coder
python agent.py
```

## What You Get

```
my-coder/
├── agent.py            # Coder agent with filesystem tools
├── prompt.md           # System prompt
├── .env                # API keys
└── .co/
    └── docs/           # ConnectOnion documentation
```

## Tools Included

| Tool | Description |
|------|-------------|
| `bash` | Run shell commands, install deps, run tests |
| `read_file` | Read file contents with line numbers |
| `edit` | Make precise edits to existing files |
| `write` | Create or overwrite files |
| `glob` | Find files by pattern |
| `grep` | Search file contents by regex |

## Template Code

```python
from connectonion import Agent, bash, read_file, edit, glob, grep, write

agent = Agent(
    name="coder",
    system_prompt="prompt.md",
    tools=[bash, read_file, edit, glob, grep, write],
    model="co/gemini-2.5-pro",
    max_iterations=50,
)

if __name__ == "__main__":
    print("🤖 Coder Agent")
    print("Type 'quit' to exit\n")

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in ["quit", "exit", "q"]:
            print("👋 Goodbye!")
            break

        if not user_input:
            continue

        response = agent.input(user_input)
        print(f"Agent: {response}\n")
```

## System Prompt

```markdown
# Coder Agent

You are an expert software engineer assistant with access to the local filesystem and shell.

## Tools
- `bash` — run shell commands (install deps, run tests, git, etc.)
- `read_file` — read file contents with line numbers
- `edit` — make precise edits to existing files
- `write` — create or overwrite files
- `glob` — find files by pattern
- `grep` — search file contents

## Principles
- Read files before editing them
- Run tests after making changes
- Keep changes small and focused
- Explain what you're doing as you go
```

## Example Usage

```
You: Add a hello world function to main.py
Agent: [reads main.py → edits it → confirms change]

You: Run the tests
Agent: [runs pytest → reports results]

You: Find all TODO comments in the codebase
Agent: [uses grep to search → lists results]
```

## Use Cases

- Code generation and refactoring
- Debugging failing tests
- Searching and navigating codebases
- Automating repetitive file edits

## Configuration

`max_iterations=50` is set high to handle complex multi-step coding tasks. Reduce it for simpler use cases.

## Next Steps

- [Tools](../concepts/tools.md) - Add custom tools
- [Events](../concepts/events.md) - Add lifecycle hooks
- [Browser Template](browser.md) - Add web browsing capabilities
