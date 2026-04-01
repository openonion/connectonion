# Claude Code System Prompt

The full Claude Code system prompt collection, extracted from Claude Code's compiled source.

## What's Inside

Claude Code doesn't use a single system prompt. It has 110+ prompt pieces:

- **System prompts** - Core behavior, tool usage, tone, security, planning
- **Agent prompts** - Specialized agents (Explore, Plan, general-purpose, etc.)
- **Tool descriptions** - Per-tool guidance (Bash, Read, Write, Edit, Grep, etc.)
- **Skills** - Built-in slash commands (/commit, /review-pr, /simplify, etc.)
- **System reminders** - Contextual injections (plan mode, hooks, memory, etc.)
- **Data files** - API references, SDK patterns, model catalog

## Local Copy

```bash
# Cloned at:
platform/claude-code-system-prompts/

# Browse system prompts
ls platform/claude-code-system-prompts/system-prompts/

# Browse tools
ls platform/claude-code-system-prompts/tools/
```

## Usage with `co copy`

```bash
co copy claude_code_system_prompt
```

## Why This Matters

Understanding Claude Code's prompt architecture helps build better coding agents:

1. **Per-tool "when NOT to use"** sections - negative guidance is as important as positive
2. **Modular assembly** - prompts composed from many small pieces, not one giant blob
3. **Progressive detail** - each tool gets dedicated instructions with examples
4. **Safety layers** - security rules, action reversibility checks, hook systems
