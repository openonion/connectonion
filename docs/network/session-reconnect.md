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
    ╭──────────╮
    │   new    │◄───── session_id not found / first connect
    ╰────┬─────╯
         │ CONNECT
         ↓
    ╭──────────╮            ╭───────────╮
    │connected │◄───────────│ suspended │
    │ (idle)   │  reconnect │ (grace)   │
    ╰────┬─────╯            ╰─────┬─────╯
         │ INPUT                  │ 10min idle
         ↓                        ↓
    ╭──────────╮            ╭──────────╮
    │executing │            │ REMOVED  │
    ╰────┬─────╯            ╰──────────╯
         │
    ┌────┴────────────────────┐
    ↓ agent done              ↓ WS disconnects
    ╭──────────╮         ╭───────────╮
    │connected │         │ suspended │
    ╰──────────╯         ╰───────────╯
```

| Transition | Trigger | What happens |
|---|---|---|
| → EXECUTING | `register()` on INPUT | Agent thread spawned, IO queues created |
| → SUSPENDED | Client WebSocket drops | Agent may keep running, queues buffer events |
| → CONNECTED | Agent finishes (OUTPUT) | Session alive, idle, ready for next INPUT |
| → CONNECTED | Client reconnects | Same session reattached to new WebSocket |
| → REMOVED | 10min idle (no client ping) | Freed from memory |

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

T+20   ✕ DISCONNECT         mark_suspended()
                            (queues stay alive)   (still blocked)

T+25   WS open
       CONNECT ───────────► registry.get() → FOUND (running)
       { session_id }       reattach IO queues
       ◄── CONNECTED ──────  { status: "running" }
       ◄── queued events ── drain buffer
                             update_ping()
                             start PING/PONG
       approve ────────────► io._incoming.put() ► io.receive() unblocks
                                                   agent continues...

T+35                        ◄─────────────────── agent finishes
                             mark_connected()
                             save to JSONL
       ◄── OUTPUT ──────────  session → "connected" (alive, ready for more)

T+40   INPUT ─────────────► new agent thread  ► agent.input() starts
                             (same session, next turn)
```

**What happened:**
1. Agent asked for approval at T+15, blocked waiting
2. Client disconnected at T+20 — agent stayed blocked, events buffered
3. Client reconnected at T+25 with `CONNECT { session_id, session }` — server found executing session, piped buffered events, client sent approval
4. Agent unblocked and finished — session stays alive ("connected"), ready for next INPUT

### Auto-Reconnect (Browser)

After a page refresh, the client automatically reconnects:

```
Page loads → Zustand hydrates → session_id exists
    │
    ▼
Open WebSocket → CONNECT { session_id, session: {messages} }
    │
    ├─ CONNECTED { status: "executing" }  → agent running, events stream in
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

One rule: clean up idle sessions that aren't executing:

```
             status in ('connected', 'suspended')
             AND idle > 10min
                   │
                   ▼
          ┌────────────────┐
          │ REMOVE from    │
          │ registry       │
          │ (memory freed) │
          └────────────────┘
```

- **Never clean up executing sessions** (agent still running).
- **Connected and suspended** use the same 10min idle rule.
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
                              │  mark_connected()
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

## Known Issue: Reconnect During Approval Blocks

When a client refreshes while the agent is blocked waiting for approval (e.g., bash tool), reconnection fails. Here's the bug chain:

```
Time   What happens
────   ─────────────────────────────────────────────
T+0    Agent sends approval_needed, blocks on io.receive()
T+5    Client refreshes → WebSocket disconnects
       → _pipe_ws_io detects disconnect
       → io.close() puts {"type": "io_closed"} sentinel in io._incoming
       → io.receive() unblocks with sentinel
       → Agent treats it as "connection closed" error
       → If agent crashes: run_agent() has NO try/finally
         → agent_finished.set() NEVER fires
         → _pipe_ws_io hangs forever waiting for agent_finished
T+10   New WebSocket connects → CONNECT { session_id }
       → registry.get() finds session, status still 'executing'
       → Reattach path: uses SAME io object
       → BUT io._closed = True → io.send() drops all events
       → Agent can't send to new client
```

### Three bugs

1. **`run_agent()` has no error handling** — if agent crashes, `agent_finished.set()` never fires, `_pipe_ws_io` hangs forever.

2. **Reattach uses closed IO** — on reconnect, the server reattaches to the old `io` object which has `_closed = True`. Agent's `io.send()` silently drops all events.

3. **Two `_pipe_ws_io` loops compete** — the old loop (stuck waiting for `agent_finished`) and the new loop (from reattach) both reference the same `agent_finished` event, causing race conditions on completion.

### Fix plan

1. **`run_agent()`: wrap in try/finally** — always set `agent_finished`, capture error in `error_holder`.

2. **Reattach: reopen IO** — reset `io._closed = False` so the agent can send events through the new WebSocket.

3. **Old `_pipe_ws_io`: detect it's been superseded** — when a new connection reattaches, the old pipe should stop waiting and exit cleanly.

---

## Key Files

| File | Role |
|---|---|
| `network/host/session/active.py` | ActiveSessionRegistry — in-memory session tracking |
| `network/io/websocket.py` | WebSocketIO — queue bridge between async/sync |
| `network/host/session/storage.py` | SessionStorage — JSONL persistence |
| `network/host/session/merge.py` | Session merge conflict resolution |
| `network/asgi/websocket.py` | WebSocket handler — orchestrates reconnection |
