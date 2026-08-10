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

### ACP Agent Mode

```bash
co ai --acp
```

Starts a stable ACP v1 agent server over stdio so an ACP-compatible editor or
CLI can create a session and drive the real `co ai` coding agent. ACP messages
are newline-delimited JSON-RPC on stdin/stdout; human-readable diagnostics stay
on stderr.

Each ACP session owns one in-memory `co ai` Agent, so later prompts in that
session reuse its conversation and tool state. The working directory supplied
by the client must be an existing absolute directory. MCP servers and
additional workspace roots are not accepted yet.

ACP session updates preserve the Agent's event order: thinking, tool starts,
tool results, and the terminal assistant response are emitted through one FIFO
consumer per session. Tool arguments and supported JSON-native results remain
structured in ACP `rawInput`/`rawOutput`; every result also carries text content
for compatibility. Turn usage and stop reasons come from the Agent's structured
terminal record, not display text. `session/cancel` and client EOF cooperatively
stop the active turn, and late events from that retired turn are not forwarded
into a later prompt.

ConnectOnion currently receives one complete response from the model provider,
so the terminal assistant message is one ACP chunk rather than a live token
stream. Richer cancellation of external side effects and client-mediated
approvals remain follow-up work. Until the approval bridge is available, Safe
mode fails closed when a sensitive tool requires approval; `--yolo` remains an
explicit operator choice at process launch.

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
| `--acp` | | off | Serve stable ACP v1 over stdin/stdout |

```bash
co ai --port 9000
co ai --model co/gemini-3.6-flash
co ai "Build an agent" --model co/gpt-4o --max-iterations 50
co ai --yolo "Fix the failing suite" --yolo-turns 20
co ai --acp
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
permission. Accept Edits permits workspace changes but still asks about
untrusted commands, while explicit
YOLO/ULW runs without prompts inside that same sandbox. The policy is reapplied
when a Codex session is resumed, and `danger-full-access` is never selected by
the integration. In a hosted session, only the operator can approve Codex's
nested permission requests; shared contacts are always confined to read-only
Codex runs with permission requests denied.

**Claude Code delegation**
- Hand a scoped coding task to the installed Claude Code CLI
- Continue the same Claude Code session by passing back its `session_id`
- Receive one stable JSON result for success, timeout, or provider errors

### Delegate to Claude Code

`co ai` can delegate an implementation or investigation while retaining
responsibility for the plan and review:

```text
Ask Claude Code to implement the parser in /path/to/repo and run the focused
tests. Review its diff, then continue the same session for any fixes.
```

The Claude Code CLI must be installed and authenticated. Safe Mode retains
Claude's normal permission rules, Accept Edits allows in-workspace edits, and
explicit YOLO/ULW uses Claude Auto mode.
The integration never selects `bypassPermissions`, and the selected mode is
supplied again when a session resumes.

Claude Code runs in headless print mode. It cannot display an inner permission
prompt in the co ai UI: Safe Mode can read and run actions already allowed by
Claude settings, while other protected actions fail closed. Accept Edits
automatically permits in-scope edits, but shell or network actions that still
need a prompt also fail closed. A denied action can be described in a
successful provider result, so always review the diff and test output rather
than treating `status` alone as proof of completion.

Because Claude's local settings can pre-approve actions, hosted Claude Code
delegation is operator-only. Shared contacts receive a structured error and the
local Claude CLI is not started.

Auto mode is narrower than `bypassPermissions`, but it is not universally
available. It requires an eligible account and model, an Anthropic API
connection (not Bedrock, Vertex, or Foundry), and any required organization
administrator setting. Ineligible Auto mode is returned as a provider error;
the integration does not fall back to a more permissive mode.

The real-binary smoke test is opt-in because it can use an authenticated model:

```bash
pytest -m real_api tests/e2e/real_api/test_real_claude_code.py
```

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
