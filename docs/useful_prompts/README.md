# Prompt Templates

Pre-built prompt structures for common agent patterns. Copy to your project and customize.

## Quick Reference

| Template | Purpose | Use Case |
|----------|---------|----------|
| [coding_agent](coding_agent.md) | Coding Agent Prompt | CLI coding tools, code review bots |

## Philosophy

These are **examples to copy**, not framework code to import.

1. Browse the templates
2. Copy what fits your needs
3. Modify freely - you own the code

No lock-in. No rigid structure. Just good patterns.

## Usage Pattern

```bash
# Copy template to your project
cp -r $(python -c "from connectonion.useful_prompts import get_example_path; print(get_example_path('coding_agent'))") ./my_prompts

# Or manually
cp -r .../connectonion/useful_prompts/coding_agent/ ./my_prompts
```

```python
# Use the assembler from your copied template
from my_prompts.assembler import assemble_prompt
from connectonion import Agent, Shell, DiffWriter

tools = [Shell(), DiffWriter()]
prompt = assemble_prompt(prompts_dir="my_prompts/prompts", tools=tools)

agent = Agent("my-agent", system_prompt=prompt, tools=tools)
```

## Why Modular Prompts?

Learned from Claude Code's architecture:

| Benefit | Description |
|---------|-------------|
| **Per-tool guidance** | Each tool gets dedicated "when to use" / "when NOT to use" |
| **Easy customization** | Modify one file without touching others |
| **Conditional assembly** | Only include prompts for tools you actually use |
| **Project context** | Add project-specific instructions separately |

## Template Structure

Each template follows this pattern:

```
template_name/
├── prompts/
│   ├── main.md           # Core agent behavior
│   └── tools/            # Per-tool guidance
│       ├── tool_a.md
│       └── tool_b.md
├── assembler.py          # Prompt assembly utility
└── README.md             # Template documentation
```

## Customizing Templates

### Modify agent behavior
Edit `prompts/main.md`:
- Agent personality and tone
- Workflow steps
- General guidelines

### Add tool guidance
Create `prompts/tools/my_tool.md`:
```markdown
# Tool: My Tool

## When to Use
- Situation A
- Situation B

## When NOT to Use
- Situation C

## Examples
<good-example>
...
</good-example>

<bad-example>
...
</bad-example>
```

### Add project context
Create `.co/AGENT.md` in your project:
```markdown
# Project: My App

## Tech Stack
- Python 3.11, FastAPI

## Conventions
- Use snake_case
- Type hints required
```

Pass it to the assembler:
```python
prompt = assemble_prompt(
    prompts_dir="my_prompts/prompts",
    tools=tools,
    context_file=".co/AGENT.md"
)
```

## Comparison: Single File vs Modular

| Approach | Pros | Cons |
|----------|------|------|
| **Single file** | Simple, one place | Hard to maintain, can't customize per-tool |
| **Modular** | Easy to update, per-tool control | More files to manage |

**Recommendation:** Start with single file for simple agents. Switch to modular when you need per-tool customization or have 3+ tools.
