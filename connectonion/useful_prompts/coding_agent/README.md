# Coding Agent Prompt

A modular **prompt template** for building coding agents. This is a prompt (not code) - copy it to your project and customize the markdown files.

## Structure

```
coding_agent/
├── prompts/
│   ├── main.md           # Core agent behavior
│   └── tools/            # Per-tool guidance
│       ├── shell.md      # Shell/bash usage
│       ├── read.md       # File reading
│       ├── write.md      # File writing
│       └── todo.md       # Task tracking
├── assembler.py          # Prompt assembly utility
└── README.md
```

## Quick Start

1. **Copy to your project:**
   ```bash
   cp -r coding_agent/ my-project/
   cd my-project/coding_agent
   ```

2. **Use the assembler:**
   ```python
   from assembler import assemble_prompt
   from connectonion import Agent
   from connectonion.useful_tools import Shell, DiffWriter

   def read_file(path: str) -> str:
       return open(path).read()

   tools = [Shell(), read_file, DiffWriter()]
   prompt = assemble_prompt(prompts_dir="prompts", tools=tools)

   agent = Agent("my-agent", system_prompt=prompt, tools=tools)
   agent.run()
   ```

## Customization

### Modify main.md
Edit `prompts/main.md` to change:
- Agent personality and tone
- Workflow steps
- General guidelines

### Add/modify tool descriptions
Each file in `prompts/tools/` provides guidance for one tool:
- `shell.md` - When to use shell, when not to
- `read.md` - File reading best practices
- `write.md` - File writing guidelines
- `todo.md` - Task tracking guidance

Add new files for your custom tools:
```markdown
# prompts/tools/my_custom_tool.md

# Tool: My Custom Tool

## When to Use
- Situation A
- Situation B

## When NOT to Use
- Situation C
```

### Add project context
Create `.co/AGENT.md` in your project root for project-specific instructions:
```markdown
# Project: My App

## Tech Stack
- Python 3.11
- FastAPI
- PostgreSQL

## Conventions
- Use snake_case for functions
- Type hints required
```

Then pass it to the assembler:
```python
prompt = assemble_prompt(
    prompts_dir="prompts",
    tools=tools,
    context_file=".co/AGENT.md"
)
```

## Philosophy

This is NOT a framework. It's an example you own completely.

- Modify any file freely
- Delete what you don't need
- Add what you want
- No dependencies on ConnectOnion internals

The assembler is ~50 lines of simple Python. Read it, understand it, change it.
