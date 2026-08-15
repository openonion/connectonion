# co ai

AI coding agent that works in your project — in the terminal or via web chat.

## Quick Start

```bash
co ai
```

Opens a web chat at `chat.openonion.ai` connected to a coding agent running locally. The agent can read and edit your project files, run shell commands, manage tasks, and more.

## Three Modes

### Web Server Mode (default)

```bash
co ai
```

- Starts an agent server on `localhost:8000`
- Opens `chat.openonion.ai/{your-address}` in your browser
- You chat with the agent through the web UI
- Agent runs in your project directory
- Serves OIP 0.1 over the authenticated `/ws` connection

On its first web-server start, `co ai` creates a private owner invite in
`~/.co/keys.env`. The code is never printed in startup logs. When you are ready
to connect your own client, reveal it intentionally:

```bash
co keys --reveal
```

Restarting `co ai` keeps the same invite, so clients already given the code are
not locked out. An explicit `CO_INVITE_CODE` in the current project or process
continues to take precedence.

The published `@connectonion/react` package owns the browser OIP client, browser
identity, onboarding, reconnect, approvals, and session normalization. O Chat
pins one exact preview version. The Host advertises OIP 0.1 in `CONNECTED`; an
explicit unsupported descriptor fails clearly instead of selecting another
transport. Identity, recipient binding, replay protection, and trust policy
remain ConnectOnion Host responsibilities.

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
| `--model` | `-m` | `co/gemini-3.7-flash` | LLM model to use |
| `--max-iterations` | `-i` | `100` | Max tool iterations per turn |
| `--yolo` | | off | Skip tool approvals and keep working across turns |
| `--yolo-turns` | | `100` | Autonomous turns before a checkpoint; must be positive |
| `--eval` | | off | Debug a task with two extra model calls that score completion |
| `--json` | | off | Emit one JSON envelope to stdout in one-shot mode |
| `--resume` | | | With `--json`, continue a one-shot session by ID |

```bash
co ai --port 9000
co ai --model co/gemini-3.7-flash
co ai "Build an agent" --model co/gpt-4o --max-iterations 50
co ai --yolo "Fix the failing suite" --yolo-turns 20
co ai --eval "Check whether this agent really completed the task"
```

## Full access (`--yolo`)

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

YOLO is the familiar CLI shorthand for Full access. It selects the canonical
`:danger-full-access` permission profile and uses `full_access_turns` for the
bounded autonomous checkpoint.

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
session ID. Read only starts Codex read-only and asks when it requests more
permission. Auto permits workspace changes but still asks about untrusted
commands, while Full access runs without prompts using Codex's
`danger-full-access` sandbox. The policy is reapplied when a Codex session is
resumed. In a hosted session, only the operator can approve Codex's
nested permission requests; shared contacts are always confined to read-only
Codex runs with permission requests denied.

**Claude Code delegation**
- Hand a scoped coding task to the installed Claude Code CLI
- Continue the same Claude Code session by passing back its `session_id`
- Watch Claude's inner tools start and finish as live O Chat cards
- Receive one stable JSON result for success, timeout, or provider errors

### Delegate to Claude Code

`co ai` can delegate an implementation or investigation while retaining
responsibility for the plan and review:

```text
Ask Claude Code to implement the parser in /path/to/repo and run the focused
tests. Review its diff, then continue the same session for any fixes.
```

The Claude Code CLI must be installed and authenticated. `co ai` still makes
one ordinary `claude_code` tool call, but the web UI now shows inner activity
such as `Claude Code › Read`, `Claude Code › Edit`, and `Claude Code › Bash` as
it happens. The enclosing ConnectOnion agent keeps ownership of the final
answer and reviews Claude's result.

Read only maps to Claude's manual permission mode, Auto maps to
`acceptEdits`, and Full access maps to Claude Auto mode. The
integration never selects `bypassPermissions`, and the selected mode is
supplied again when a session resumes. Separately, every delegated run uses
Claude's `--safe-mode` isolation switch, which disables
ordinary user and project customizations—including `CLAUDE.md`, skills,
plugins, hooks, MCP servers, commands, and custom agents—so they cannot raise
that mode's authority; admin-managed policy still applies. The directory
passed by the model must resolve inside the project root where `co ai` started.
Relevant project instructions are already carried by the parent prompt instead
of being reloaded as provider-side filesystem configuration.

Claude Code runs in headless `stream-json` mode. Its inner tool activity is
visible, but it still cannot display an unmatched Claude permission prompt in
the `co ai` UI: Read only can run actions allowed by its bound provider mode,
while other protected actions fail closed. Auto automatically
permits in-scope edits, but shell or network actions that still need a prompt
also fail closed. A denied action can be described in a successful provider
result, so always review the diff and test output rather than treating `status`
alone as proof of completion.

Because delegation starts a local coding subprocess with operator-bound
authority, hosted Claude Code remains operator-only. Shared contacts receive a
structured error and the local Claude CLI is not started.

Auto mode is narrower than `bypassPermissions`, but it is not universally
available. It requires an eligible account and model, an Anthropic API
connection (not Bedrock, Vertex, or Foundry), and any required organization
administrator setting. Ineligible Auto mode is returned as a provider error;
the integration does not fall back to a more permissive mode.

The real-binary smoke test is opt-in because it can use an authenticated model:

```bash
pytest -m real_api tests/e2e/real_api/test_real_claude_code.py
```

This is a fail-closed release check: absence of the optional Claude executable
is a skip, but an installed CLI with stale authentication or a provider error is
a failure. Both tests must pass before the result counts as live integration evidence.
The test respects an explicit `CLAUDE_CONFIG_DIR`; without one it selects the
native macOS Keychain login or the platform's isolated Claude credential directory,
without copying or printing credential contents.

When a hosted turn is interrupted, both built-in coding adapters cooperatively
stop their launch process group and discard late session state and UI events.
This bounds future provider work; filesystem or external effects completed
before the interrupt are not rolled back.

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
- Session records saved to `~/.co/evals/` (the newest 500 are retained)
- Resumable one-shot sessions saved privately under `~/.co/ai/sessions/`
- Same address across all `co ai` sessions

Task scoring is separate from session recording. It is off by default; pass
`--eval` when debugging to generate an expected outcome and score completion.

## Examples

```bash
# Start web chat
co ai

# Add a feature
co ai "Add rate limiting to the API endpoint in oo-api/routes/llm.py"

# Fix a bug
co ai "The test test_agent_loop is failing, investigate and fix it"

# Use a different model
co ai --model co/gemini-3.7-flash

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
