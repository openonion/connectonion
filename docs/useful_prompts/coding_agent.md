# Coding Agent Prompt

A modular prompt template for building coding assistants. This is a **prompt**, not code - you copy it, customize it, and use it as your agent's system prompt.

## Overview

This template provides:
- **Main prompt** - Core agent behavior, tone, workflow
- **Per-tool prompts** - Guidance for shell, file read/write, todo list
- **Assembler** - Simple utility to combine prompts

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
├── assembler.py          # Prompt assembly (~50 lines)
└── README.md
```

## Quick Start

### 1. Copy to your project

```bash
# Using co copy (recommended)
co copy coding_agent

# Or manually
cp -r $(python -c "from connectonion.useful_prompts import get_example_path; print(get_example_path('coding_agent'))") ./prompts
```

### 2. Use in your agent

```python
from prompts.assembler import assemble_prompt
from connectonion import Agent
from connectonion.useful_tools import Shell, DiffWriter, TodoList

def read_file(path: str) -> str:
    """Read file contents."""
    return open(path).read()

# Define tools
tools = [Shell(), read_file, DiffWriter(), TodoList()]

# Assemble prompt (only includes docs for tools you have)
prompt = assemble_prompt(
    prompts_dir="prompts/prompts",
    tools=tools
)

# Create agent
agent = Agent("coder", system_prompt=prompt, tools=tools)
agent.run()
```

## Prompt Files

### main.md

Core agent behavior:
- Tone and style (concise, no preamble)
- Task workflow (understand → search → implement → verify)
- Coding guidelines (read first, mimic style, minimal changes)
- Persistence (don't give up easily)
- Security rules (no secrets, no force push)

### tools/shell.md

When to use shell:
- Git operations
- Package management
- Running tests
- Build commands

When NOT to use:
- Reading files (use read_file)
- Writing files (use write)

### tools/read.md

File reading best practices:
- Always read before modifying
- Check dependencies
- Understand context

### tools/write.md

File writing guidelines:
- Read first, then write
- Match existing style
- Minimal changes

### tools/todo.md

Task tracking guidance:
- When to use (3+ steps)
- When not to use (trivial tasks)
- Task states and flow

## Customization

### Change agent personality

Edit `prompts/main.md`:

```markdown
# My Custom Agent

You are a friendly coding assistant that loves emojis! 🚀

## Tone
- Be enthusiastic and encouraging
- Use emojis liberally
- Celebrate small wins
```

### Add custom tool guidance

Create `prompts/tools/my_api.md`:

```markdown
# Tool: My API

## When to Use
- Fetching user data
- Updating records

## When NOT to Use
- Bulk operations (use batch API)

## Rate Limits
- Max 100 requests/minute
- Use caching when possible
```

### Add project context

Create `.co/AGENT.md`:

```markdown
# Project: E-commerce API

## Stack
- Python 3.11, FastAPI, PostgreSQL

## Conventions
- snake_case for functions
- Type hints required
- Tests in tests/ directory
```

Use in assembler:

```python
prompt = assemble_prompt(
    prompts_dir="prompts/prompts",
    tools=tools,
    context_file=".co/AGENT.md"
)
```

## The Assembler

The assembler is intentionally simple (~50 lines):

```python
def assemble_prompt(prompts_dir, tools, context_file=None):
    parts = []

    # 1. Main prompt
    parts.append(read("prompts/main.md"))

    # 2. Tool descriptions (for each tool)
    for tool in tools:
        tool_file = f"prompts/tools/{tool.name}.md"
        if exists(tool_file):
            parts.append(read(tool_file))

    # 3. Project context (optional)
    if context_file:
        parts.append(read(context_file))

    return "\n\n---\n\n".join(parts)
```

You own this code. Modify it for your needs:
- Add variable interpolation
- Add conditional sections
- Add version tracking
- Whatever you need

## Best Practices

### From Claude Code

1. **"When NOT to use"** sections are as important as "when to use"
2. **Examples with reasoning** - show good AND bad patterns
3. **Keep tool docs focused** - one tool per file
4. **Project context separate** - easy to update per-project

### Keep It Simple

- Start with the template as-is
- Only add complexity when needed
- Delete files you don't use
- The goal is clarity, not completeness
