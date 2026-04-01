# Claude Code System Prompt

The full Claude Code system prompt collection (110+ pieces), extracted from Claude Code's compiled source.

## What's Inside

Claude Code doesn't use a single system prompt. It has many prompt pieces:

- `prompts/system/` - Core behavior, tool usage, tone, security, planning
- `prompts/agents/` - Specialized agents (Explore, Plan, general-purpose, etc.)
- `prompts/tools/` - Per-tool guidance (Bash, Read, Write, Edit, Grep, etc.)
- `prompts/skills/` - Built-in slash commands (/commit, /review-pr, /simplify, etc.)
- `prompts/reminders/` - Contextual injections (plan mode, hooks, memory, etc.)
- `prompts/data/` - API references, SDK patterns, model catalog

## Usage

```bash
co copy cc_prompt
```

## Why This Matters

Understanding Claude Code's prompt architecture helps build better coding agents:

1. Per-tool "when NOT to use" sections - negative guidance is as important as positive
2. Modular assembly - prompts composed from many small pieces, not one giant blob
3. Progressive detail - each tool gets dedicated instructions with examples
4. Safety layers - security rules, action reversibility checks, hook systems
