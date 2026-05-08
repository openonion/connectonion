# Session Reconnection

WebSocket connections drop. Agents keep running. Here's how reconnection works.

## Architecture

Two layers handle session survival:

```
┌─────────────────────────────────────┐
│ In-Memory (ActiveSessionRegistry)   │
│ Running agents, IO queues, threads  │
│ Cleaned after 10min idle            │
└──────────────┬──────────────────────┘
               │ save on completion
┌──────────────▼──────────────────────┐
│ Disk (.co/session_results.jsonl)    │
│ Final results for polling recovery  │
│ Expires after 24h                   │
└─────────────────────────────────────┘
```

**In-memory** keeps the agent thread and IO queues alive so a reconnecting client resumes mid-execution. **Disk** stores final results so a client that never reconnects can poll later.

---

## Session Lifecycle

```
    ╭──────────────╮
    │     new      │◄──── session_id not found / first connect
    ╰──────┬───────╯
           │ CONNECT
           ↓
    ╭──────────────╮
    │  connected   │
    │   (idle)     │── 10min idle ─► REMOVED
    ╰──────┬───────╯
           │ INPUT
           ↓
    ╭──────────────╮
    │   running    │── 1h idle (stuck) ─► REMOVED
    ╰──────┬───────╯
           │ agent done
           ↓
    ╭──────────────╮
    │  connected   │── 10min idle ─► REMOVED
    ╰──────────────╯
```

Two states. WS disconnect does **not** change session.status — the IO and agent
thread stay live in `ActiveSessionRegistry`, a reconnecting client re-subscribes
through CONNECT.

| Transition | Trigger | What happens |
|---|---|---|
| → RUNNING | `register()` on INPUT | Agent thread spawned, IO queues created |
| → CONNECTED | Agent finishes (OUTPUT) → `mark_session_connected()` | Session alive, idle, ready for next INPUT |
| → CONNECTED (reattach) | Client reconnects via CONNECT { session_id } | Same io reused, forward task restarted, cursor rewound |
| → REMOVED | 10min idle (connected) / 1h idle (running) | Freed from memory by `cleanup_expired` |

---

## Reconnection Flow

The key insight: the **IO queues survive the WebSocket**. When a client reconnects with `CONNECT { session_id }`, the server finds the running session and reattaches the same queues to the new connection. The agent thread never knows the difference.

See [WebSocket Protocol](websocket-protocol.md) for the full CONNECT/INPUT protocol specification.

```
Time   Client              WebSocket Handler    Agent Thread
────   ──────              ─────────────────    ────────────
T+0    CONNECT ───────────► accept, auth
       ◄── CONNECTED ──────  { session_id, status: "new" }
       INPUT ─────────────► register()
                            spawn thread ───────► agent.input() starts
T+5                        ◄─────────────────── io.send(thinking)
       ◄── thinking ────────

T+15                       ◄─────────────────── io.send(approval_needed)
       ◄── approval_needed─                     io.receive() BLOCKS
                                                 waiting for response...

T+20   ✕ DISCONNECT         (status stays 'running', queues stay alive)
                                                  (still blocked)

T+25   WS open
       CONNECT ───────────► registry.get() → FOUND (running)
       { session_id }       reattach IO queues
       ◄── CONNECTED ──────  { status: "running" }
       ◄── queued events ── drain buffer
                             update_ping()
                             start PING/PONG
       approve ────────────► send_to_agent → _msgs_from_client → io.receive() unblocks
                                                   agent continues...

T+35                        ◄─────────────────── agent finishes
                             mark_session_connected()
                             save to JSONL
       ◄── OUTPUT ──────────  session → "connected" (alive, ready for more)

T+40   INPUT ─────────────► new agent thread  ► agent.input() starts
                             (same session, next turn)
```

**What happened:**
1. Agent asked for approval at T+15, blocked waiting
2. Client disconnected at T+20 — agent stayed blocked, events buffered
3. Client reconnected at T+25 with `CONNECT { session_id, session }` — server found running session, piped buffered events, client sent approval
4. Agent unblocked and finished — session stays alive ("connected"), ready for next INPUT

### Cursor Rewind on Resume

Agent-side events are appended to an in-memory log on the `WebSocketIO` object with a monotonic cursor. Each event carries a UUID `id`. The forwarder advances the cursor as it ships events to the WebSocket — but a `ws.send()` only confirms the OS-level buffer accepted the bytes, not that the client rendered them. If the connection dies between buffer-accept and client-render, the cursor sits past events the user never actually saw. The most painful case: a blocking `ask_user` / `approval_needed` event that the agent is now waiting on, but the client has no idea exists.

To recover, `CONNECT` accepts an optional `last_msg_id` — the id of the last agent event the client fully rendered. On resume of a `running` session the server calls `io.rewind_to(last_msg_id)`, which sets the cursor to right after the matching event. The new forwarder task replays everything after that point. If `last_msg_id` is omitted or unknown, the cursor rewinds to 0 and the entire current execution is replayed (the client should dedup by `id`).

Cursor rewind only fires when status is `running`. For `connected` the agent isn't producing events anymore; the client's session reconciliation (chat_items in the CONNECTED reply) carries the final state.

### Auto-Reconnect (Browser)

After a page refresh, the client automatically reconnects:

```
Page loads → Zustand hydrates → session_id exists
    │
    ▼
Open WebSocket → CONNECT { session_id, session: {messages} }
    │
    ├─ CONNECTED { status: "running" }    → agent running, events stream in
    ├─ CONNECTED { status: "connected" }  → session alive, send INPUT when ready
    └─ CONNECTED { status: "new" }        → session expired, start fresh (client has history)
```

One message handles all cases. No "completed" or "expired" death states.

---

## IO Queue Bridge

The agent runs in a sync thread. The WebSocket handler is async. Two thread-safe queues bridge them:

```
┌───────────────────┐          ┌───────────────────┐
│  Agent Thread      │          │  WebSocket Handler │
│  (sync Python)     │          │  (async ASGI)      │
│                    │          │                    │
│  io.send(event) ──►│─outgoing─│►── ws.send(event)  │
│                    │  queue   │                    │
│  io.receive()  ◄──│─incoming─│◄── ws.receive()    │
│  (blocks)          │  queue   │                    │
└───────────────────┘          └───────────────────┘
```

On **disconnect**: `io.close()` puts a sentinel in the incoming queue, unblocking any waiting `receive()`.

On **reconnect**: the **same io object** is reused. A new WebSocket handler starts pumping the same queues. The agent thread continues as if nothing happened.

---

## Keep-Alive

Server sends PING every 30s. Client responds with PONG. Each message updates `last_ping` in the registry.

```
Client                    Server
  │                         │
  │◄──── PING ──────────────│  every 30s
  │───── PONG ─────────────►│  update last_ping
  │                         │
  │◄──── PING ──────────────│
  │───── PONG ─────────────►│  update last_ping
  │                         │
  │  ✕ disconnect            │
  │                         │  last_ping freezes
  │                         │  idle timer starts
  │                         │  ...
  │                         │  10min idle → cleanup
```

---

## Session Cleanup

One rule: clean up idle sessions that aren't running:

```
             status == 'connected'
             AND idle > 10min
                   │
                   ▼
          ┌────────────────┐
          │ REMOVE from    │
          │ registry       │
          │ (memory freed) │
          └────────────────┘
```

- **'connected' sessions** removed after 10min idle.
- **'running' sessions** removed after 1h idle (stuck-agent safety cap).
- **Results already on disk.** JSONL storage has the final result.
- **Client can still poll.** `GET /sessions/{id}` works for 24h.
- **Background job** runs every 60s to sweep expired sessions.

---

## Recovery Without Reconnect

If the client never comes back:

```
Client gone                 Server
                              │
                              │  agent finishes
                              │  save result to .co/session_results.jsonl
                              │  mark_session_connected()
                              │
                              │  ... 10min idle ...
                              │
                              │  cleanup_expired() → removed from memory
                              │
                              │  (result still on disk for 24h)
                              │
Client returns (hours later)  │
  │                           │
  │── GET /sessions/{id} ────►│  read from JSONL
  │◄── result ────────────────│
```

No data loss. The JSONL file is the durable record.

---

## Session Merge

When a client reconnects and both sides have session state, `merge_sessions()` resolves the conflict using iteration count (incremented on each LLM call):

```
Client (stale)              Server (continued)
iteration: 5                iteration: 10
    │                           │
    └───────────┬───────────────┘
                │ merge_sessions()
                ▼
          server wins (higher iteration)
          → use server session state
```

| Scenario | Resolution |
|---|---|
| Server continued (iteration 10 vs 5) | Server wins |
| Client newer (iteration 8 vs 3) | Client wins |
| Tie (same iteration) | Higher `updated` timestamp wins |

---

## Reconnect During Approval / Ask-User Blocks

The hard case: client refreshes while the agent is blocked in `io.receive()` waiting for `APPROVAL_RESPONSE` or `ASK_USER_RESPONSE`. The current implementation handles it cleanly:

```
Time   What happens
────   ─────────────────────────────────────────────
T+0    Agent sends approval_needed, blocks on io.receive()
       (waiting on _msgs_from_client mailbox)
T+5    Client refreshes → WebSocket disconnects
       → run_session's finally → _cleanup_session()
       → forward_task.cancel() + await unwind
       → ping_task.cancel() + await unwind
       → run_session returns
       → The WebSocketIO instance and its queues stay alive
         in ActiveSessionRegistry (status still 'running')
       → Agent thread is STILL BLOCKED in io.receive() —
         that's fine, no one consumed its mailbox yet
T+10   New WebSocket connects → CONNECT { session_id, last_msg_id }
       → registry.get() returns the same ActiveSession
       → status == 'running' branch:
            io.rewind_to(last_msg_id)        # reset cursor under lock
            _resume_connection() spawns new forward_task on same io
       → Server replays any agent events the old client missed
       → Client sees the approval_needed UI again, user clicks Approve
       → APPROVAL_RESPONSE arrives → send_to_agent puts it in _msgs_from_client
       → Agent's io.receive() unblocks with the response → continues
```

Three properties make this work:

1. **`_run_agent_thread` has `try/except/finally`** — captures exceptions in `result_holder[0]`, always calls `io.finish()` in finally so the forwarder can exit cleanly. The thread never silently disappears.

2. **The io is not closed on WS disconnect** — `_cleanup_session` only cancels the forward/ping tasks. The `WebSocketIO` instance, its three channels, and the agent thread all stay live under `ActiveSession`.

3. **Single forward task per session** — the old forward_task is fully cancelled and awaited before a new one is created on reconnect (in `_resume_connection`). No competing loops on the same io.

## Key Files

| File | Role |
|---|---|
| `network/host/session/active.py` | ActiveSessionRegistry — in-memory session tracking |
| `network/io/websocket.py` | WebSocketIO — queue bridge between async/sync |
| `network/host/session/storage.py` | SessionStorage — JSONL persistence |
| `network/host/session/merge.py` | Session merge conflict resolution |
| `network/asgi/websocket.py` | WebSocket handler — orchestrates reconnection |
