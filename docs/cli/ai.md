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
- Starts an authenticated ACP v1 WebSocket at `/acp` for compatible clients

The current O Chat release still connects through the authenticated `/ws`
compatibility transport. The `/acp` endpoint is started now so native ACP
clients can be validated before the React/O Chat migration. Both endpoints use
the same ConnectOnion identity, recipient binding, replay protection, and trust
policy; starting ACP does not make the coding Agent anonymous or public.

Browser ACP connections first exchange a signed request for a short-lived,
single-use, Origin-bound ticket. Programmatic clients can sign the WebSocket
upgrade directly. See [Authenticated ACP WebSocket](../network/acp-websocket.md).
This preview supports direct loopback or TLS/WSS connections only. It does not
claim end-to-end encryption through an untrusted TLS-terminating relay.
Network clients send `/` as their ACP workspace; the Host maps that virtual
root to the project directory captured when `co ai` started. They cannot select
another Host path. Local stdio ACP clients continue to provide an existing
absolute working directory.

Native ACP prompts accept text, PNG/JPEG/GIF/WebP images, and embedded text or
binary files. Files use the opaque URI form
`connectonion-upload:/<percent-encoded-filename>`; the URI never names a Host
path and ordinary resource links are not fetched. Count and decoded-size limits
come from `host.yaml`, while the direct ACP preview also keeps a one-MiB
JSON-RPC frame limit. Larger files need a future authenticated streaming upload
rather than a larger inline WebSocket message. Successful network files are
retained for resumable sessions under a per-authenticated-principal quota
(`max_acp_upload_storage`, 100 MiB by default; `max_acp_upload_files`, 100 by
default). Reaching either cumulative limit fails before the Agent turn without
writing another file.

Durable native-network ACP sessions have a separate authenticated-principal
quota: 100 snapshots, 100 MiB total serialized state, and 32 MiB for one
snapshot by default. Operators can lower these with `max_acp_sessions`,
`max_acp_session_storage`, and `max_acp_snapshot_size`. Quota exhaustion keeps
the previous resumable snapshot unchanged; it never truncates conversation
state. Local stdio ACP is not charged to a remote principal quota.

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

Use `--acp` when another local process launches `co ai` and owns its stdio.
Default web-server mode also exposes authenticated ACP v1 at `/acp`; it is a
network endpoint and therefore keeps ConnectOnion authentication and trust in
front of ACP initialization.

Each ACP session owns one in-memory `co ai` Agent, so later prompts in that
session reuse its conversation and tool state. The working directory supplied
by the client must be an existing absolute directory. Additional workspace
roots are not accepted yet.

Automation and concurrent acceptance tests can give one ACP process a private
mutable-state root:

```bash
co ai --acp --state-dir /private/tmp/co-acp-test
```

This roots that process's durable ACP snapshots, Agent logs, and eval files
under the selected directory. It does not copy credentials or create another
ConnectOnion identity: the Agent name and configured provider credentials still
come from the normal global configuration. On POSIX, the selected directory is
created or tightened to mode `0700`; a symlink is rejected. The default remains
`~/.co`, and `--state-dir` without `--acp` exits with an error. This first slice
does not change web-server or network Host storage semantics.

The stdio adapter advertises image and embedded-context prompt capabilities
with the same validated content-block mapping as the network endpoint. Audio is
not advertised. Invalid MIME types, base64, counts, sizes, or unsafe upload
names fail before the Agent turn begins.

ACP stdio MCP servers are disabled by default because their configuration can
launch local processes. An operator can grant that launch authority explicitly:

```bash
co ai --acp --acp-mcp
```

With that flag, `session/new` and `session/resume` may provide up to eight
stdio MCP servers with absolute executable paths. HTTP, SSE, and ACP-transport
MCP servers are rejected. Each server runs in the session cwd with the MCP
SDK's safe environment baseline plus only the environment entries explicitly
provided for that server; the complete parent environment is not copied.

MCP commands, arguments, environment values, and discovered tools are not
persisted. A resumed session must provide its complete MCP list again. Closing
the session, client EOF, or partial startup failure reaps every owned process.
Discovery is bounded to 128 tools and 32 pages, schemas and results are bounded
to 64 KiB, tool-call arguments are bounded to 64 KiB, and calls have a
60-second read timeout.

Remote tool names and annotations are not trusted as permissions. MCP tools
receive collision-resistant `mcp__...` names and pass through the ordinary
ConnectOnion approval hook. Read only and Auto profiles ask the ACP operator
when an action is outside their policy; explicit Full access remains the only
approval bypass.
"Allow for this session" lasts only for the current open MCP process pool.
Client-granted MCP approvals are not persisted, so resume asks again even when
the client supplies the same server and tool names. Explicit operator rules in
`.co/host.yaml` remain durable configuration.

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
stream. Client-mediated approval is generation-scoped and fails closed on
cancelled, unknown, or disconnected outcomes. `--yolo` remains an explicit
operator choice at process launch.

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
| `--acp-mcp` | | off | With `--acp`, allow session-scoped stdio MCP launches |
| `--state-dir` | | `~/.co` | With `--acp`, isolate mutable session, log, and eval state |

```bash
co ai --port 9000
co ai --model co/gemini-3.6-flash
co ai "Build an agent" --model co/gpt-4o --max-iterations 50
co ai --yolo "Fix the failing suite" --yolo-turns 20
co ai --acp
co ai --acp --acp-mcp
co ai --acp --state-dir /private/tmp/co-acp-test
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

### Delegate through a generic ACP child

`co ai` also exposes `acp_agent` for a task that specifically needs the common
ACP client edge rather than the preferred native `codex` or `claude_code`
routes. The tool accepts a named engine, explicit working directory, and
optional resumable session ID; command, approval, and workspace authority are
not model arguments.

Read only and Workspace profiles keep the child in manual approval. A valid,
bounded Full Access grant selects auto. Hosted non-admin requesters cannot
start a local ACP child. The pinned `codex-acp@1.1.14` route is rejected outside
Full Access because its manual/read-only mode does not reliably request ACP
permission for shell or outbound network actions; use the native `codex` tool
for approval-aware Codex delegation.

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
