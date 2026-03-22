# co ai

AI coding agent that works in your project — in the terminal or via web chat.

## Quick Start

```bash
co ai
```

Opens a web chat at `chat.openonion.ai` connected to a coding agent running locally. The agent can read and edit your project files, run shell commands, manage tasks, and more.

## Two Modes

### Web Server Mode (default)

```bash
co ai
```

- Starts an agent server on `localhost:8000`
- Opens `chat.openonion.ai/{your-address}` in your browser
- You chat with the agent through the web UI
- Agent runs in your project directory

### One-Shot Mode

```bash
co ai "Create a calculator tool"
co ai "Fix the failing test in tests/unit/test_agent.py"
co ai "Refactor agent.py to use the new event system"
```

Runs the prompt, prints the result, and exits. No server started.

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--port` | `-p` | `8000` | Port for web server |
| `--model` | `-m` | `co/claude-opus-4-5` | LLM model to use |
| `--max-iterations` | `-i` | `100` | Max tool iterations per turn |

```bash
co ai --port 9000
co ai --model co/gemini-2.5-pro
co ai "Build an agent" --model co/gpt-4o --max-iterations 50
```

## What the Agent Can Do

The agent has a full suite of tools for coding tasks:

**File operations**
- Read, search (glob, grep), edit, and write files

**Shell**
- Run bash commands (with approval flow for destructive operations)

**Planning**
- Enter plan mode, write plans, exit and implement

**Task management**
- Create and track todos, run background tasks, get task output

**Skills**
- Load and run user-defined skills from `~/.claude/skills/`

## Project Context

When started, the agent automatically loads context from your project:

1. `.co/OO.md` — project-specific instructions (primary)
2. `CLAUDE.md` — Claude Code compatibility
3. `README.md` — project overview (truncated at 5000 chars)
4. Available skills from `~/.claude/skills/`
5. Git status — branch, uncommitted changes, recent commits
6. Working directory and current date

This means the agent understands your project without you having to explain it.

## Project Instructions

Create `.co/OO.md` in your project to give the agent persistent instructions:

```bash
mkdir -p .co
cat > .co/OO.md << 'EOF'
Always run tests before committing.
Use snake_case for function names.
The main entry point is src/main.py.
EOF
```

This is loaded every session, so the agent always follows your rules.

## Identity & Logs

`co ai` uses your global identity from `~/.co/`:

- Logs saved to `~/.co/logs/oo.log`
- Eval sessions saved to `~/.co/evals/`
- Same address across all `co ai` sessions

## Examples

```bash
# Start web chat
co ai

# Add a feature
co ai "Add rate limiting to the API endpoint in oo-api/routes/llm.py"

# Fix a bug
co ai "The test test_agent_loop is failing, investigate and fix it"

# Use a different model
co ai --model co/gemini-2.5-pro

# Run on a different port
co ai --port 9000
```

## Web Chat vs Terminal

| | Web Chat (`co ai`) | Terminal (`co ai "..."`) |
|--|-------------------|--------------------------|
| Interaction | Conversational, multi-turn | One-shot, exits after |
| Best for | Extended coding sessions | Quick tasks, scripting |
| Output | Web UI | Printed to stdout |
| Server | Runs on localhost | Not started |
