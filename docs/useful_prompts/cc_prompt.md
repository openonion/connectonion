# Claude Code System Prompt

The full Claude Code system prompt collection, extracted from Claude Code's compiled source.

## What's Inside

Claude Code doesn't use a single system prompt. It has 250 prompt pieces:

- **System prompts** - Core behavior, tool usage, tone, security, planning
- **Agent prompts** - Specialized agents (Explore, Plan, general-purpose, etc.)
- **Tool descriptions** - Per-tool guidance (Bash, Read, Write, Edit, Grep, etc.)
- **Skills** - Built-in slash commands (/commit, /review-pr, /simplify, etc.)
- **System reminders** - Contextual injections (plan mode, hooks, memory, etc.)
- **Data files** - API references, SDK patterns, model catalog

## Usage with `co copy`

```bash
co copy cc_prompt
```

This copies the full prompt collection to `./prompts/cc_prompt/` in your project, organized by category:

```
prompts/cc_prompt/
├── agents/       # Specialized agent prompts (Explore, Plan, etc.)
├── data/         # API references, SDK patterns, model catalog
├── reminders/    # Contextual system reminders
├── skills/       # Built-in slash commands
├── system/       # Core behavior prompts
└── tools/        # Per-tool descriptions and guidance
```

## Why This Matters

Understanding Claude Code's prompt architecture helps build better coding agents:

1. **Per-tool "when NOT to use"** sections - negative guidance is as important as positive
2. **Modular assembly** - prompts composed from many small pieces, not one giant blob
3. **Progressive detail** - each tool gets dedicated instructions with examples
4. **Safety layers** - security rules, action reversibility checks, hook systems
