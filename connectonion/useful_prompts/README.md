# useful_prompts

Prompt examples and patterns for ConnectOnion agents. Copy what you need to your project.

## Philosophy

These are **examples**, not framework code. You:
1. Browse the examples
2. Copy what fits your needs
3. Modify freely - you own the code now

No lock-in. No rigid structure. Just good patterns.

## Available Examples

### coding_agent/
A modular prompt structure for coding assistants.

```
coding_agent/
├── prompts/
│   ├── main.md           # Core agent behavior
│   └── tools/            # Per-tool guidance
│       ├── shell.md
│       ├── read.md
│       ├── write.md
│       └── todo.md
├── assembler.py          # Simple prompt assembly
└── README.md
```

**Good for:** CLI coding assistants, code review bots, development helpers

## How to Use

```bash
# Copy the example to your project
cp -r useful_prompts/coding_agent/ my-project/

# Customize the prompts
cd my-project/coding_agent
vim prompts/main.md       # Edit core behavior
vim prompts/tools/shell.md # Edit shell guidance
```

## Creating Your Own

1. Start with an existing example
2. Modify `main.md` for your agent's personality
3. Add/remove tool files as needed
4. Customize `assembler.py` for your assembly logic

## Principles

From Claude Code's architecture, we learned:

1. **Modular prompts** - Split by concern (main, per-tool)
2. **"When NOT to use"** - As important as "when to use"
3. **Examples with reasoning** - Show good AND bad patterns
4. **Assembly at runtime** - Combine pieces based on available tools
5. **User owns the code** - No framework lock-in
