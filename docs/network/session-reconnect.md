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
register()
    │
    ▼
 RUNNING ──────────────────────► COMPLETED
    │            agent finishes       │
    │                                 │
    ▼ client disconnects              │ 10min idle
 SUSPENDED                           ▼
    │                              REMOVED
    │ client reconnects
    ▼
 RUNNING (same IO queues)
```

| Transition | Trigger | What happens |
|---|---|---|
| → RUNNING | `register()` | Agent thread spawned, IO queues created |
| → SUSPENDED | Client WebSocket drops | Agent keeps running, queues buffer events |
| → RUNNING | Client reconnects with same session_id | Same IO queues reattached to new WebSocket |
| → COMPLETED | Agent finishes | Result saved to JSONL, session stays in memory |
| → REMOVED | 10min idle (no client ping) | Freed from memory |

---

## Reconnection Flow

The key insight: the **IO queues survive the WebSocket**. When a client reconnects, the server reattaches the same queues to the new connection. The agent thread never knows the difference.

```
Time   Client              WebSocket Handler    Agent Thread
────   ──────              ─────────────────    ────────────
T+0    INPUT ─────────────► accept
                            register()
                            spawn thread ───────► agent.input() starts
T+5                        ◄─────────────────── io.send(thinking)
       ◄── thinking ────────

T+15                       ◄─────────────────── io.send(approval_needed)
       ◄── approval_needed─                     io.receive() BLOCKS
                                                 waiting for response...

T+20   ✕ DISCONNECT         mark_suspended()
                            (queues stay alive)   (still blocked)

T+25   RECONNECT ──────────► registry.get() → FOUND
                             drain queued events
       ◄── queued events ───
                             update_ping()
                             pump same IO queues
       approve ────────────► io._incoming.put() ► io.receive() unblocks
                                                   agent continues...

T+35                        ◄─────────────────── agent finishes
                             mark_completed()
                             save to JSONL
       ◄── OUTPUT ──────────
```

**What happened:**
1. Agent asked for approval at T+15, blocked waiting
2. Client disconnected at T+20 — agent stayed blocked, events buffered
3. Client reconnected at T+25 — got buffered events, sent approval
4. Agent unblocked and finished normally

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

One rule for all non-running sessions:

```
             status != 'running'
             AND idle > 10min
                   │
                   ▼
          ┌────────────────┐
          │ REMOVE from    │
          │ registry       │
          │ (memory freed) │
          └────────────────┘
```

- **No special cases.** Completed, suspended — same rule.
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
                              │  mark_completed()
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

## Key Files

| File | Role |
|---|---|
| `network/host/session/active.py` | ActiveSessionRegistry — in-memory session tracking |
| `network/io/websocket.py` | WebSocketIO — queue bridge between async/sync |
| `network/host/session/storage.py` | SessionStorage — JSONL persistence |
| `network/host/session/merge.py` | Session merge conflict resolution |
| `network/asgi/websocket.py` | WebSocket handler — orchestrates reconnection |
