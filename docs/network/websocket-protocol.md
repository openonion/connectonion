# WebSocket Protocol

> CONNECT to start or resume, INPUT to message, EXEC to run one tool directly. Session stays alive between executions.

---

## Overview

Three client message types, three intents:

| Message | Intent | When |
|---------|--------|------|
| `CONNECT` | "Authenticate me, restore my session" | First message on every WebSocket |
| `INPUT` | "Run this prompt" or runtime input mid-execution | After CONNECT |
| `EXEC` | "Run this one tool directly, no LLM" | After CONNECT |

If `INPUT` arrives while the session's agent is already running, the server treats it as **runtime input** (mid-execution user input) instead of starting a second agent. The new prompt is appended to the agent's message history at the next iteration, and the server replies with `RUNTIME_INPUT_ACK` instead of starting a new OUTPUT cycle.

`EXEC` is the direct-execution fast path: it runs one named tool with no LLM, no session, and no history, replying with a single `EXEC_RESULT`. It requires the same CONNECT auth as INPUT, and the tool is gated by the host's `.co/host.yaml` permission whitelist. See [remote-call.md](remote-call.md).

```
┌────────────────────────────────────────────────────────────────┐
│                    WebSocket Lifecycle                          │
│                                                                │
│   Every connection:  WS open → CONNECT → CONNECTED → ...      │
│                                                                │
│   CONNECT carries:   auth + session (conversation history)     │
│   INPUT carries:     just the prompt (session already set)     │
│                                                                │
│   Server decides:    new / connected / running                 │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Session Lifecycle

```
════════════════════════════════════════════════════════════════════
  SESSION = connection.  EXECUTION = one INPUT → OUTPUT cycle.
  Session outlives executions. Multiple INPUTs per session.
════════════════════════════════════════════════════════════════════

    ╭──────────╮
    │   new    │◄──────────────────── session_id not found
    ╰────┬─────╯
         │ CONNECT
         ↓
    ╭──────────────╮
    │  connected   │◄── agent done (OUTPUT)
    ╰──────┬───────╯
           │ INPUT
           ↓
    ╭──────────────╮
    │   running    │── agent working (LLM → tools → LLM)
    ╰──────┬───────╯
           │ agent done
           ↓
    ╭──────────────╮
    │  connected   │── 10min idle → removed
    │   (idle)     │
    ╰──────────────╯


    Two states only: 'running' (agent working) and 'connected' (idle, alive).
    WS disconnect does NOT change session.status — IO queues survive the WS,
    a reconnecting client just re-subscribes via CONNECT { last_msg_id }.

    Cleanup: 'connected' after 10min idle, 'running' after 1h (stuck-agent cap).
```

---

## Protocol Flows

### New Session

```
Client                                    Server
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ─────────────────────────────►│  verify Ed25519 signature
  │   { auth, session: {messages} }         │  no session_id → new session
  │                                         │  store conversation history
  │                                         │
  │◄── CONNECTED ──────────────────────────│  { session_id: "abc", status: "new" }
  │                                         │
  │◄── PING ───────────────────────────────│  keep-alive starts (every 30s)
  │── PONG ────────────────────────────────►│
  │                                         │
  │── INPUT ───────────────────────────────►│  run agent with prompt
  │   { prompt: "hello" }                   │  (no session in INPUT)
  │                                         │
  │◄── thinking ───────────────────────────│  stream events
  │◄── tool_call ──────────────────────────│
  │◄── OUTPUT ─────────────────────────────│  { result, session }
  │                                         │  session → "connected" (not dead)
  │                                         │
  │── INPUT ───────────────────────────────►│  same WS, same session
  │   { prompt: "tell me more" }            │
  │◄── ... ────────────────────────────────│
  │◄── OUTPUT ─────────────────────────────│
```

### Resume After Page Refresh (agent still running)

```
Client                                    Server
  │                                         │
  │    (agent still running on server)      │
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ─────────────────────────────►│  verify signature
  │   { session_id: "abc", session: {...} } │  registry.get("abc") → running
  │                                         │  merge sessions if server newer
  │                                         │
  │◄── CONNECTED ──────────────────────────│  { session_id: "abc", status: "running" }
  │◄── buffered events ───────────────────│  drain queued events
  │◄── PING ───────────────────────────────│  keep-alive resumes
  │                                         │
  │◄── stream events ─────────────────────│  live again
  │◄── OUTPUT ─────────────────────────────│
```

### Resume After Page Refresh (agent finished)

```
Client                                    Server
  │                                         │
  │    (agent finished while client away)   │
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ─────────────────────────────►│  verify signature
  │   { session_id: "abc", session: {...} } │  registry.get("abc") → connected
  │                                         │  merge: server has newer data
  │                                         │
  │◄── CONNECTED ──────────────────────────│  { session_id: "abc",
  │                                         │    status: "connected",
  │                                         │    server_newer: true,
  │                                         │    session: {merged},
  │                                         │    chat_items: [...] }
  │                                         │
  │    (client updates UI with server data) │
  │                                         │
  │── INPUT ───────────────────────────────►│  ready for next prompt
  │   { prompt: "what else?" }              │
  │◄── ... ────────────────────────────────│
  │◄── OUTPUT ─────────────────────────────│
```

### Session Not Found (expired or never existed)

```
Client                                    Server
  │                                         │
  │── WS open ────────────────────────────►│
  │── CONNECT { session_id: "abc" } ──────►│  not in registry
  │◄── CONNECTED ──────────────────────────│  { session_id: "abc", status: "new" }
  │                                         │
  │── INPUT ───────────────────────────────►│  fresh session, full history from CONNECT
```

---

## Message Reference

### Client → Server

#### CONNECT

Authenticate, restore session, and sync conversation. **Always the first message.**

```json
{
  "type": "CONNECT",
  "session_id": "550e8400-...",
  "session": { "messages": [...], "mode": "safe" },
  "last_msg_id": "ev-9f12...",
  "payload": { "to": "0x3d4017c3e843...", "timestamp": 1702234567 },
  "from": "0xClientPublicKey",
  "signature": "0x..."
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `session_id` | No | Session to resume. Omit for new session. |
| `session` | No | Conversation history (messages, mode, etc.) |
| `last_msg_id` | No | ID of the last agent event the client fully rendered. On resume of a `running` session, server rewinds its event cursor to right after this id and replays anything the client missed. Omit (or pass `null`) to replay all in-flight events of the current execution. |
| `payload` | Yes | Signed payload for authentication |
| `from` | Yes | Client's public address |
| `signature` | Yes | Ed25519 signature of payload |

Server response based on state:

| session_id | Server state | Response status | Server action |
|------------|-------------|-----------------|---------------|
| Not provided | — | `"new"` | Allocate new session |
| Provided | In registry, running | `"running"` | Reattach IO, pipe buffered events |
| Provided | In registry, connected | `"connected"` | Merge sessions, reset idle timer |
| Provided | Not found | `"new"` | Allocate new session (same id) |

#### INPUT

Send a prompt. Only valid after CONNECTED. **No session data — just the prompt.**

```json
{
  "type": "INPUT",
  "prompt": "Translate hello to Spanish",
  "images": ["data:image/png;base64,..."],
  "files": [{ "name": "doc.pdf", "data": "data:application/pdf;base64,..." }]
}
```

If sent while the session's agent is already running, this message is routed as runtime input: the prompt is appended to the running agent's message history (with framing telling the LLM to treat it as additional context, not a replacement) and the server replies `RUNTIME_INPUT_ACK` instead of starting a new OUTPUT cycle. No new `thinking` chat item is created — the existing one keeps streaming.

#### EXEC

Run one registered tool directly — no LLM, no session, no history. Only valid after CONNECTED. The server replies with a single `EXEC_RESULT`.

```json
{
  "type": "EXEC",
  "exec_id": "7c2a...",
  "tool": "bash",
  "args": { "command": "co status" }
}
```

The tool is checked against the host's `.co/host.yaml` permission whitelist (the same list the LLM approval flow uses); a tool that isn't whitelisted comes back as an `EXEC_RESULT` with `status: "error"`. Each `EXEC` runs as its own server-side task, so a slow tool never blocks the connection, and `exec_id` correlates the reply — several `EXEC`s can be pipelined on one socket.

#### PONG

```json
{ "type": "PONG" }
```

#### ASK_USER_RESPONSE

```json
{ "type": "ASK_USER_RESPONSE", "answer": "Python 3" }
```

#### APPROVAL_RESPONSE

```json
{ "type": "APPROVAL_RESPONSE", "approved": true, "scope": "once" }
```

### Server → Client

#### CONNECTED

Response to CONNECT.

```json
{
  "type": "CONNECTED",
  "session_id": "550e8400-...",
  "status": "new",
  "server_newer": true,
  "session": { "messages": [...] },
  "chat_items": [...]
}
```

| `status` | Meaning | Client action |
|----------|---------|---------------|
| `"new"` | Fresh session | Send INPUT when ready |
| `"connected"` | Session alive, idle | Send INPUT when ready |
| `"running"` | Agent still running | Wait for events/OUTPUT |

`server_newer`, `session`, and `chat_items` are only included when the server's session data is newer than the client's (e.g., agent completed while client was away).

#### OUTPUT

Execution completed. **Session stays alive for next INPUT.**

```json
{
  "type": "OUTPUT",
  "result": "Hola",
  "session_id": "550e8400-...",
  "duration_ms": 1250,
  "session": { "messages": [...], "trace": [...], "turn": 2 }
}
```

#### EXEC_RESULT

Reply to an `EXEC`. `exec_id` echoes the request. `result` is the tool's raw output — text, or a base64 data URL for a screenshot tool.

```json
{
  "type": "EXEC_RESULT",
  "exec_id": "7c2a...",
  "tool": "bash",
  "status": "success",
  "result": "...raw output...",
  "duration_ms": 42
}
```

On failure (tool raised, not whitelisted, unknown tool): `status: "error"` with an `error` field instead of `result`.

#### PING

Keep-alive. Sent every 30 seconds.

```json
{ "type": "PING" }
```

#### Stream Events

| Type | Description |
|------|-------------|
| `thinking` | Agent reasoning |
| `tool_call` | Tool execution started |
| `tool_result` | Tool execution completed |
| `ask_user` | Agent needs human input |
| `approval_needed` | Tool requires approval |
| `plan_review` | Plan ready for review |
| `compact` | Context compaction |

#### RUNTIME_INPUT_ACK

Acknowledges an INPUT that arrived while the agent was running. The prompt has been queued and will be picked up at the agent's next iteration.

```json
{
  "type": "RUNTIME_INPUT_ACK",
  "session_id": "550e8400-...",
  "id": "runtime-input-7c2a..."
}
```

#### ERROR

```json
{ "type": "ERROR", "message": "Something went wrong" }
```

---

## Architecture Diagram

```
════════════════════════════════════════════════════════════════════

  ╔══════════════╗                    ╔═══════════════════════════╗
  ║   oo-chat    ║                    ║     Agent Server          ║
  ║  (browser)   ║                    ║  (Python SDK + host())    ║
  ╠══════════════╣                    ╠═══════════════════════════╣
  ║              ║                    ║                           ║
  ║ localStorage ║    WebSocket       ║  ┌─────────────────────┐  ║
  ║ ┌──────────┐ ║   ┌──────────┐    ║  │ ActiveSessionRegistry│  ║
  ║ │ session  │ ║───│ /ws      │────║──│                     │  ║
  ║ │ chatItems│ ║   └──────────┘    ║  │ session_id → {      │  ║
  ║ │ messages │ ║    CONNECT ──►    ║  │   io, thread,       │  ║
  ║ └──────────┘ ║    ◄── CONNECTED  ║  │   status, last_ping │  ║
  ║              ║    INPUT ────►    ║  │ }                   │  ║
  ║ TS SDK       ║    ◄── events     ║  └─────────┬───────────┘  ║
  ║ RemoteAgent  ║    ◄── OUTPUT     ║            │              ║
  ║              ║    PING/PONG      ║            ↓              ║
  ╚══════════════╝                    ║  ┌─────────────────────┐  ║
                                      ║  │ SessionStorage      │  ║
                                      ║  │ (.co/session_       │  ║
                                      ║  │  results.jsonl)     │  ║
                                      ║  └─────────────────────┘  ║
                                      ╚═══════════════════════════╝

  Data Ownership:
  ┌────────────────────────────────────────────────────────────────┐
  │ Client owns: conversation history (localStorage)              │
  │ Server owns: execution state (registry), results (storage)    │
  │ CONNECT syncs: client → server (session), server → client     │
  │                (if server_newer)                               │
  └────────────────────────────────────────────────────────────────┘

════════════════════════════════════════════════════════════════════
```

---

## Separation of Concerns

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Connection    │  │  Conversation   │  │   Execution     │
│                 │  │                 │  │                 │
│ WebSocket + auth│  │ Message history │  │ One INPUT→OUTPUT│
│ PING/PONG       │  │ Owned by client │  │ Agent thread    │
│ Persistent      │  │ Sent via CONNECT│  │ Temporary       │
│                 │  │ Merged on server│  │                 │
│ Dies: WS close  │  │ Dies: never     │  │ Dies: OUTPUT    │
│ + 10min grace   │  │ (localStorage)  │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Authentication

Authentication happens once, on CONNECT.

```
CONNECT (signed)          INPUT (not signed)
  │                          │
  ▼                          ▼
Server verifies            Server trusts
signature → OK             (same WS, already authenticated)
```

Trust levels:

| Trust Level | CONNECT Behavior |
|-------------|-----------------|
| `open` | Accept without signature |
| `careful` | Accept unsigned, recommend signature |
| `strict` | Require valid signature |

---

## Client Reconnect

```
Page loads → Zustand hydrates → session_id exists?
  │
  ├── Yes → CONNECT { session_id, session: {messages} }
  │           │
  │           ├── "new"       → session expired, start fresh (client has history)
  │           ├── "connected" → session alive, ready for INPUT
  │           └── "running"   → agent running, events will stream
  │
  └── No  → show empty state, wait for user input
              → CONNECT (no session_id) on first message
```

---

## Before vs After

### Before (v0.9.x) — INIT + ATTACH

```
WS open → INIT { auth }    → CONNECTED { status: "new" }
           INPUT { prompt, session }  → events → OUTPUT → session dies
```

### v0.10.x — CONNECT (unified)

```
WS open → CONNECT { auth, session_id? } → CONNECTED { status }
           INPUT { prompt, session }     → events → OUTPUT → session dies
```

### v0.11.x — Session survives execution (current)

```
WS open → CONNECT { auth, session_id?, session }
           → CONNECTED { status: new/connected/running }

           INPUT { prompt }   → events → OUTPUT  (session stays alive)
           INPUT { prompt }   → events → OUTPUT  (again, same session)
           INPUT { prompt }   → events → OUTPUT  (and again)

WS close → 10min grace → session cleaned up
```

---

## Server Console Output

The WebSocket handler prints structured status lines to the server console. Designed for quick scanning: routine messages are compact, data flow events are indented sub-lines.

### Connection lifecycle

```
⚡ ws+ 127.0.0.1 (0 active)        # new WebSocket, show active session count
✓ CONNECT identity=0x2f3d... session=aad5... status=new
✓ INPUT identity=0x2f3d... session=aad5... prompt=hello world...
⚡ ws- (1 active)                    # disconnect, show remaining sessions
```

### Data flow visibility

When client data is accepted, merged, or reattached, indented sub-lines show what's happening:

```
✓ CONNECT identity=0x2f3d... session=aad5... status=connected
  ↑ client session: 4 messages       # client sent conversation history
  ↕ merged sessions (server newer)   # server had newer data, merged
```

```
✓ CONNECT identity=0x2f3d... session=aad5... status=running
  ↻ reattaching to running agent     # reconnecting to in-progress execution
```

```
✓ INPUT identity=0x2f3d... session=aad5... prompt=analyze this...
  ↑ 2 images, 1 files                # client sent attachments
```

### What's suppressed

Routine message types that already have their own status lines don't print a generic `← WS recv:` line:
- `CONNECT`, `INPUT`, `SESSION_STATUS`, `PONG`

Non-routine types still print:
```
← WS recv: ONBOARD_SUBMIT
← WS recv: ADMIN_PROMOTE
```

### Error lines

```
✗ CONNECT auth error: forbidden
✗ INPUT rejected: not authenticated (send CONNECT first)
✗ agent error: <exception message>
```

---

## Key Files

| File | Role |
|------|------|
| `network/host/ws_router/` | 4-file message router package — `session.py` (run_ws_session main loop), `connect.py` (handle_connect), `agent_io.py` (start_agent / resume_forwarding / forwarding), `ping.py` (keepalive) |
| `network/asgi/websocket.py` | ASGI adapter — wraps ASGI primitives into send_msg/recv_msg for ws_router |
| `network/relay.py` | Relay adapter — wraps asyncio.Queue/relay WS into send_msg/recv_msg for ws_router |
| `network/host/session/active.py` | ActiveSessionRegistry — in-memory session tracking |
| `network/io/websocket.py` | WebSocketIO — queue bridge between async/sync |
| `network/host/session/storage.py` | SessionStorage — JSONL persistence |
| `network/host/session/merge.py` | Session merge conflict resolution |
