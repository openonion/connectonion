# WebSocket Protocol

> CONNECT to start or resume, INPUT to message. Session stays alive between executions.

---

## Overview

Two client message types, two intents:

| Message | Intent | When |
|---------|--------|------|
| `CONNECT` | "Authenticate me, restore my session" | First message on every WebSocket |
| `INPUT` | "Run this prompt" | After CONNECT, while the session is idle |

If `INPUT` arrives while the session's agent is already running, the server
returns a retryable `ERROR`. It does not claim the request ID or queue the
prompt, so the client can retry the same signed INPUT after the current
`OUTPUT` without risking a second agent thread.

```
┌────────────────────────────────────────────────────────────────┐
│                    WebSocket Lifecycle                          │
│                                                                │
│   Every connection:  WS open → CONNECT → CONNECTED → ...      │
│                                                                │
│   CONNECT carries:   signed action + session digest            │
│   INPUT carries:     signed action + prompt/id/attachment hash │
│                                                                │
│   Server decides:    new / connected / running                 │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Session Lifecycle

```
════════════════════════════════════════════════════════════════════
  SESSION persists across connections. EXECUTION = one INPUT → OUTPUT cycle.
  Session outlives executions and transport reconnects.
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

    Cleanup: 'connected' after 10min idle. A live running thread is never
    evicted; a dead/stale running registry entry is eligible after 1h.
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
  │── INPUT ───────────────────────────────►│  verify session.input signature
  │   { input_id, prompt, session_id, ... }  │  claim one-time input_id
  │                                         │
  │◄── thinking ───────────────────────────│  stream events
  │◄── tool_call ──────────────────────────│
  │◄── OUTPUT ─────────────────────────────│  { result, session }
  │                                         │  session → "connected" (not dead)
  │                                         │
  │── INPUT ───────────────────────────────►│  same WS, same session
  │   { signed session.input, new input_id } │
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
  │                                         │  retain owner-bound server transcript
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
  │                                         │  restore owner-bound server data
  │                                         │
  │◄── CONNECTED ──────────────────────────│  { session_id: "abc",
  │                                         │    status: "connected",
  │                                         │    server_newer: true,
  │                                         │    session: {merged},
  │                                         │    chat_items: [...] }
  │                                         │
  │    (client updates UI with server data) │
  │                                         │
  │── INPUT ───────────────────────────────►│  ready for next signed prompt
  │   { signed session.input, new input_id } │
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

A stored legacy record with no `owner_address` is different from "not found": it
cannot be claimed or resumed. The server returns an error instructing the client
to reconnect without that old `session_id` and start a new owned session.

---

## Message Reference

### Client → Server

#### CONNECT

Authenticate, restore session, and sync conversation. **Always the first message.**

```json
{
  "type": "CONNECT",
  "to": "0x3d4017c3e843...",
  "timestamp": 1702234567,
  "session_id": "550e8400-...",
  "session": { "session_id": "550e8400-...", "messages": [...] },
  "last_msg_id": "ev-9f12...",
  "payload": {
    "action": "session.connect",
    "to": "0x3d4017c3e843...",
    "timestamp": 1702234567,
    "session_id": "550e8400-...",
    "session_sha256": "<sha256-of-canonical-session-json>"
  },
  "from": "0xClientPublicKey",
  "signature": "0x..."
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `session_id` | No | Session to resume. Omit for new session. |
| `session` | No | Client-visible conversation snapshot. It cannot carry authority. |
| `last_msg_id` | No | ID of the last agent event the client fully rendered. On resume of a `running` session, server rewinds its event cursor to right after this id and replays anything the client missed. Omit (or pass `null`) to replay all in-flight events of the current execution. |
| `payload` | Yes | Signed payload for authentication |
| `from` | Yes | Client's public address |
| `signature` | Yes | Ed25519 signature of payload |

Modern CONNECT uses `action: "session.connect"`. `session_sha256` is the
SHA-256 of canonical JSON for the top-level `session` (or `{}` when absent).
On resume, `session_id` must match at top level, inside `session`, and in the
signed payload. A stored owner-bound transcript remains authoritative even if a
client snapshot claims larger counters; an empty stored transcript is still
authoritative.

Server response based on state:

| session_id | Server state | Response status | Server action |
|------------|-------------|-----------------|---------------|
| Not provided | — | `"new"` | Allocate new session |
| Provided | In registry, running | `"running"` | Reattach IO, pipe buffered events |
| Provided | In registry, connected | `"connected"` | Restore server recovery data, reset idle timer |
| Provided | Not found | `"new"` | Allocate new session (same id) |

#### INPUT

Send a prompt after CONNECTED. Each modern INPUT is independently signed and
bound to the server-issued session ID.

```json
{
  "type": "INPUT",
  "to": "0x3d4017c3e843...",
  "timestamp": 1702234567,
  "session_id": "550e8400-...",
  "input_id": "input-7c2a...",
  "prompt": "Translate hello to Spanish",
  "images": ["data:image/png;base64,..."],
  "files": [{ "name": "doc.pdf", "data": "data:application/pdf;base64,..." }],
  "payload": {
    "action": "session.input",
    "to": "0x3d4017c3e843...",
    "timestamp": 1702234567,
    "session_id": "550e8400-...",
    "input_id": "input-7c2a...",
    "prompt": "Translate hello to Spanish",
    "attachments_sha256": "<sha256-of-canonical-images-and-files>"
  },
  "from": "0xClientPublicKey",
  "signature": "0x..."
}
```

`attachments_sha256` hashes canonical JSON
`{"images":[...],"files":[...]}` with empty arrays for omitted fields. An HTTP
client uses the equivalent `request_id`; do not mix both aliases. The ID is
single-use within the signature window, so a replay returns `duplicate request`.

If sent while the session's agent is already running, even a fully bound INPUT
receives a retryable `ERROR`. The host does not claim its request ID or deliver
the prompt/mode through the generic interaction mailbox. Retry that exact
signed frame after the current `OUTPUT` to start the next execution.

Legacy or signature-stripped INPUT remains compatible only for an idle Safe-mode
turn. It cannot restore capabilities or select a privileged mode, and it is
rejected while the session is running.

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

`server_newer`, `session`, and `chat_items` indicate that the host has
owner-bound recovery data the client should adopt (for example, the agent
completed while the client was away). They do not imply that a client with a
larger counter may overwrite the server transcript.

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

#### Running INPUT error

Rejects an INPUT that arrived while the agent was running. The request remains
unclaimed and may be retried after the current execution completes.

```json
{
  "type": "ERROR",
  "message": "session is running; retry INPUT after current turn",
  "retryable": true,
  "session_id": "550e8400-...",
  "request_id": "input-7c2a..."
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
  │ Client keeps: latest UI/session copy (localStorage)           │
  │ Server owns: recovery transcript, capabilities, replay state │
  │ CONNECT binds the client snapshot; stored server history wins │
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
│ PING/PONG       │  │ Client UI copy  │  │ Agent thread    │
│ Persistent      │  │ Sent via CONNECT│  │ Temporary       │
│                 │  │ Server recovery │  │                 │
│ Dies: WS close  │  │ Dies: never     │  │ Dies: OUTPUT    │
│ + 10min grace   │  │ (localStorage)  │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Authentication and Replay Binding

CONNECT authenticates the socket, and every modern INPUT authenticates its own
action and content.

```
CONNECT (signed)          INPUT (signed)
  │                          │
  ▼                          ▼
session.connect +          session.input + recipient,
session_sha256             sid, id, prompt, attachment hash
```

Both payloads include the recipient `to`, preventing cross-host replay.
`input_id` is atomically claimed and duplicates are rejected. Trust levels run
after protocol signature verification; they decide whether the verified caller
is allowed, not whether routing fields may be unsigned.

Legacy incomplete INPUT can perform only idle Safe-mode work and is rejected
during a running execution.

---

## Client Reconnect

```
Page loads → Zustand hydrates → session_id exists?
  │
  ├── Yes → CONNECT { session_id, session, signed session_sha256 }
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

           INPUT { signed session.input, input_id } → events → OUTPUT
           INPUT { signed session.input, new id }   → events → OUTPUT
           INPUT { signed session.input, new id }   → events → OUTPUT

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
  ↕ server recovery selected          # owner-bound server history restored
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

## Worker Limit

The active registry, replay claims, per-session locks, and capability leases are
process-local. Run exactly one worker per host identity. `host(workers=N)` fails
for `N != 1`, and external uvicorn/gunicorn deployments must also use one worker
unless they provide shared transactional state and sticky WebSocket routing.
