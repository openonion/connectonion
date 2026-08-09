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

For scripts and other coding agents, request one stable JSON object:

```bash
co ai "Fix the failing tests" --json
# {"session_id":"...","result":"...","error":null}

co ai "Now update the docs" --resume <session-id> --json
```

Human-oriented progress moves to stderr in JSON mode, so stdout is safe to
parse. A successful run exits `0`; invalid sessions and execution failures put
a concise message in `error` and exit non-zero. Resume never silently starts a
new conversation when the requested session is missing or invalid. Resume must
run from the same project directory, and concurrent turns for one session fail
fast instead of overwriting each other.

JSON mode omits `run_background`, `task_output`, and `kill_task` because their
process handles only exist inside one CLI process and cannot be resumed safely.
Use foreground shell commands when the next subprocess must retain their result.
On Windows, snapshot files rely on the current user's profile-directory ACLs;
POSIX systems additionally enforce `0700` directories and `0600` files.

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--port` | `-p` | `8000` | Port for web server |
| `--model` | `-m` | `co/gemini-3.6-flash` | LLM model to use |
| `--max-iterations` | `-i` | `100` | Max tool iterations per turn |
| `--yolo` | | off | Skip tool approvals and keep working across turns |
| `--yolo-turns` | | `100` | Autonomous turns before a checkpoint; must be positive |
| `--json` | | off | Emit one JSON envelope to stdout in one-shot mode |
| `--resume` | | | With `--json`, continue a one-shot session by ID |

```bash
co ai --port 9000
co ai --model co/gemini-3.6-flash
co ai "Build an agent" --model co/gpt-4o --max-iterations 50
co ai --yolo "Fix the failing suite" --yolo-turns 20
```

## YOLO mode

Use `--yolo` for a trusted task that should run without tool-approval prompts.
It works in both one-shot and web-server modes:

```bash
# Run one task autonomously, then exit at the 20-turn bound
co ai --yolo "Implement issue #123" --yolo-turns 20

# Start web chat with autonomous mode enabled for each session
co ai --yolo --yolo-turns 20
```

Slash skills are expanded before the first model call. Project skills can live
under either `.co/skills/` or `.claude/skills/`, so a project workflow can run
directly:

```bash
co ai --yolo "/deploy-oo-chat" --yolo-turns 10
```

YOLO deliberately reuses the existing ULW session and frontend protocol.
Persisted fields such as `mode: ulw`, `ulw_turns`, and
`skip_tool_approval` remain unchanged for compatibility.

## What the Agent Can Do

The agent has a full suite of tools for coding tasks:

**File operations**
- Read, search (glob, grep), edit, and write files

**Shell**
- Run bash commands (with approval flow for destructive operations)

**Planning**
- Track complex work with a visible todo list; handle simple work directly

**Task management**
- Create and track todos, run background tasks, get task output

**Codex delegation**
- Hand a scoped coding task to the installed Codex CLI
- Continue the same Codex thread by passing back its `session_id`
- Stream Codex progress and approve concrete sensitive actions in the same UI

### Delegate to Codex

`co ai` can use Codex as a collaborator while keeping ownership of planning and
review. Ask it to delegate a bounded task, for example:

```text
Ask Codex to implement the parser in /path/to/repo, run the focused tests, then
review the diff yourself. Continue the same Codex session for any fixes.
```

The Codex CLI must be installed and authenticated. `co ai` passes an explicit
working directory and returns a structured result containing the resumable
session ID. Safe Mode starts Codex read-only and asks when it requests more
permission. Plan Mode is read-only and denies escalation. Accept Edits permits
workspace changes but still asks about untrusted commands, while explicit
YOLO/ULW runs without prompts inside that same sandbox. The policy is reapplied
when a Codex session is resumed, and `danger-full-access` is never selected by
the integration.

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
- Resumable one-shot sessions saved privately under `~/.co/ai/sessions/`
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
co ai --model co/gemini-3.6-flash

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
