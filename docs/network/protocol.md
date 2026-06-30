# WebSocket Message Router

> `connectonion/network/host/ws_router/` — 4-file package, single message-routing implementation used by both the direct ASGI WebSocket path and the relay-routed path.

---

## Why one router

Earlier the WebSocket message handling (CONNECT auth, INPUT → spawn agent, streaming back, onboard, admin, ...) lived inside the ASGI handler. The relay path opened a **loopback WebSocket** back to `ws://127.0.0.1:{port}/ws` to reuse it — extra hop, extra moving parts, double maintenance.

Now the message-routing logic lives in the `ws_router/` package. Both paths call `run_ws_session()` directly with their own send_msg/recv_msg adapters:

```
Client → ASGI websocket.py → send_msg/recv_msg adapter ─┐
                                                         ├─→ run_ws_session()
Client → Relay relay.py    → send_msg/recv_msg adapter ─┘
```

No loopback. Same router. Two thin adapters.

---

## Package layout

```
network/host/ws_router/
├── __init__.py    # exports run_ws_session
├── session.py     # run_ws_session — main read loop + dispatch + cleanup
├── connect.py     # handle_connect — CONNECT auth + session merge + reattach trigger
├── agent_io.py    # start_agent / resume_forwarding / forward_agent_msgs_to_client / _agent_thread_body
└── ping.py        # ping_loop — 30s WS keepalive
```

| File | Layer | What's in it |
|---|---|---|
| `session.py` | WS protocol orchestration | `run_ws_session` is the only public API. Owns the read loop, dispatches by message type, handles small inline cases (PONG / SESSION_STATUS / runtime input detection), and runs cleanup |
| `connect.py` | WS protocol | `handle_connect` — verifies auth, merges client/server session, decides new/connected/running, triggers reattach |
| `agent_io.py` | Agent execution | Spawning agent threads, restarting forward tasks on reconnect, streaming agent output back to the client |
| `ping.py` | WS keepalive | `ping_loop` coroutine that sends a PING frame every 30s |

Dependencies: `session.py` imports from `connect.py`, `agent_io.py`, `ping.py`. `connect.py` imports `resume_forwarding` from `agent_io.py`. `agent_io.py` and `ping.py` are leaves.

---

## Public entry: `run_ws_session`

```python
async def run_ws_session(
    send_msg,       # async (dict) -> None
    recv_msg,       # async () -> dict | None  (None = client closed)
    *,
    route_handlers, # dict: auth, ws_input, trust_agent, admin_*
    storage,        # SessionStorage
    registry,       # ActiveSessionRegistry
    trust,          # TrustAgent or trust level string
    blacklist=None,
    whitelist=None,
    enable_ping=True,  # on for direct AND relay — the 30s PING is forwarded through the relay to the client (ANNOUNCE only keeps the agent↔relay link alive)
)
```

`send_msg` and `recv_msg` are the only transport-specific pieces. Everything else is shared.

Each call to `run_ws_session` drives **one client session** from connect to disconnect. The body is the read loop + per-type dispatch + cleanup, all in one function — no nested helpers for state init/teardown.

```python
async def run_ws_session(send_msg, recv_msg, *, ...):
    conn = {"authenticated": False, "identity": None, "session_id": None, "session": None}
    active_io = None
    forward_task = None
    ping_task = asyncio.create_task(ping_loop(send_msg)) if enable_ping else None

    try:
        while True:
            data = await recv_msg()
            if data is None:
                break
            # ... dispatch by data["type"] ...
    finally:
        for task in (forward_task, ping_task):
            if task and not task.done():
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass
```

`conn` is the per-session auth/identity dict, mutated in place by `handle_connect` when CONNECT succeeds. `active_io` and `forward_task` get assigned when CONNECT-resume or INPUT-new spawns them.

---

## Transport adapters

### ASGI (`asgi/websocket.py`)

```python
async def send_msg(data):
    await ws_send({"type": "websocket.send", "text": json.dumps(data, default=pydantic_json_encoder)})

async def recv_msg():
    msg = await ws_receive()
    if msg["type"] == "websocket.disconnect":
        return None
    return json.loads(msg["text"])
```

### Relay (`relay.py:_run_session`)

```python
async def send_msg(data):
    data["session_id"] = session_id        # tag back to relay
    await relay_ws.send(json.dumps(data, default=pydantic_json_encoder))

async def recv_msg():
    try:
        msg = await asyncio.wait_for(q.get(), timeout=300)   # 5min idle timeout
    except asyncio.TimeoutError:
        return None
    if msg is None or msg.get("type") == "close":
        return None
    return msg
```

Relay's `recv_msg` reads from a per-session `asyncio.Queue` populated by `serve_loop`. The 300s idle timeout prevents zombie sessions if the client vanishes without a close signal.

---

## Message dispatch (inlined inside `run_ws_session`)

```python
match data["type"]:
    "PONG"           → registry.update_ping(...)
    "SESSION_STATUS" → reply with registry-side status (inline 4 lines)
    "ONBOARD_SUBMIT" → handle_onboard_submit(...)
    "ADMIN_*"        → handle_admin_message(...)
    "CONNECT"        → handle_connect(...)        # in connect.py
    "INPUT"          → if existing running agent: push runtime_input + ACK (inline)
                       else: start_agent(...)     # in agent_io.py
    else (with active_io) → active_io.send_to_agent(data)   # ASK_USER_RESPONSE, APPROVAL_RESPONSE, etc.
```

`CONNECT` must come first — it authenticates and populates `conn`. `INPUT` and most others require `conn["authenticated"] == True`.

`SESSION_STATUS`, `ONBOARD_SUBMIT`, `ADMIN_*` carry their own auth and don't require prior CONNECT.

---

## CONNECT flow (`connect.py:handle_connect`)

```
Client → CONNECT {from, signature, payload, session_id?, last_msg_id?, session?}
```

1. **Auth** — `route_handlers["auth"](data, trust)` verifies Ed25519 signature.
2. **Forbidden + onboard** — if auth returns "forbidden" and trust config defines onboard methods (invite_code / payment), server sends `ONBOARD_REQUIRED` instead of ERROR.
3. **Session merge** — if `session_id` provided, loads stored session and merges with client's via `merge_sessions` (whichever is newer wins).
4. **Registry check** — looks up session in `ActiveSessionRegistry`:
   - `running` → agent is mid-execution; client is reconnecting, reattach via `resume_forwarding`.
   - `connected` → agent finished; session alive, ready for next INPUT.
   - not found → `new`.
5. **Send CONNECTED** — `{session_id, status, server_newer?, session?, chat_items?}`.
6. **Reattach (running only)** — call `active.io.rewind_to(last_msg_id)` to reset the message cursor, then call `resume_forwarding` (in `agent_io.py`) which spawns a new forward task that replays everything after `last_msg_id`.

Server session statuses: only `'running'` and `'connected'`. WS disconnect doesn't change `session.status` — IO queues survive the WS, a reconnecting client just re-subscribes.

---

## INPUT flow

Two paths depending on whether an agent is already running:

**Fresh agent (`agent_io.py:start_agent`)** when `registry.get(session_id)` is None or `connected`:
1. Validate (`conn["authenticated"]`, `prompt` non-empty).
2. Defense check: if status is unexpectedly `'running'`, refuse.
3. Create `WebSocketIO` (thread-safe queue pair: agent ↔ async transport).
4. Register in `ActiveSessionRegistry` BEFORE `agent_thread.start()` — registering after creates a race where a fast-completing agent calls `mark_session_connected` on an absent entry.
5. Spawn daemon thread running `route_handlers["ws_input"]` (which calls user's `create_agent` factory and runs `agent.input(prompt)`).
6. Spawn `forward_task = asyncio.create_task(forward_agent_msgs_to_client(...))` to pipe `io.read_msgs_from_agent()` events out via `send_msg`. On agent completion, sends `OUTPUT` (or `ERROR` on exception).

**Runtime input (inline in `session.py`)** when `existing.status == 'running'`:
1. Push `{type: RUNTIME_INPUT, id, prompt}` onto `existing.io._runtime_inputs` (separate queue from `receive()`'s mailbox to avoid being eaten by ask_user/approval pops).
2. Reply `RUNTIME_INPUT_ACK`. No new agent thread, no new OUTPUT cycle.
3. The agent's `apply_runtime_input` plugin (in `useful_plugins/runtime_input.py`) drains the queue at the next iteration boundary and appends each prompt to message history with an additive framing prefix.

See [websocket-protocol.md](websocket-protocol.md) for full message reference.

---

## Agent IO bridge

The agent runs in a **synchronous thread** (LLM calls are blocking, tool calls are blocking). The client is on the **async event loop**. `WebSocketIO` (`network/io/websocket.py`) is the bridge:

```
Agent thread                          Async event loop                 Client
     │                                       │                            │
     │─ io.send(event) ─► _msgs_from_agent ──│─ forward_task ────────────►│
     │  (append to in-memory log,            │  (read_msgs_from_agent     │
     │   indexed by cursor)                  │   yields events one by one)│
     │                                       │                            │
     │◄─ io.receive() ◄─ _msgs_from_client ◄─│◄─ active_io.send_to_agent  │
     │  (block until client sends, e.g.      │  (per-message dispatch     │
     │   ASK_USER_RESPONSE)                  │   in run_ws_session)          │
     │                                       │                            │
     │  io.pop_runtime_inputs() (separate    │   push_runtime_input from  │
     │  queue, drained at iteration start    │   INPUT-during-running     │
     │  by apply_runtime_input plugin)       │   inline branch            │
```

Three independent channels on one `WebSocketIO`:

| Channel | Direction | Storage | Reader / Writer |
|---|---|---|---|
| `_msgs_from_agent` | agent → client | append-only list, cursor-indexed for replay | written by `io.send`, read by `forward_task` via `read_msgs_from_agent` |
| `_msgs_from_client` | client → agent | mailbox (consumed on read) | written by `send_to_agent`, read by `io.receive` (blocking) |
| `_runtime_inputs` | client → agent | drain-all queue | written by `push_runtime_input`, drained by `apply_runtime_input` plugin |

---

## Safety / lifecycle

### Agent thread crash → still surfaces

`agent_io._agent_thread_body` wraps execution in `try/except Exception`, captures the exception in `result_holder[0]`, and always calls `io.mark_agent_done()` in `finally`. The forwarder reads `result_holder` after `read_msgs_from_agent` returns and emits `{type: ERROR, message: <exception>}` to the client. Threads don't propagate exceptions on their own — this is the manual surfacing.

### Relay session idle timeout (5 minutes)

Relay's `recv_msg` uses `asyncio.wait_for(q.get(), timeout=300)`. No message for 5 minutes → returns None → `run_ws_session` exits → cleanup. Prevents zombie sessions when a client vanishes without close.

### Relay disconnect cascade

When `serve_loop` catches `ConnectionClosed`, it puts `None` into every per-session queue before breaking. This unblocks every `recv_msg` waiting on `q.get()`, letting all in-flight `_run_session` coroutines exit cleanly.

### Cursor write under lock

`read_msgs_from_agent` writes `self._cursor` under `_agent_condition` after each yield batch, so a concurrent `rewind_to(last_msg_id)` (which holds the same lock) can't be silently overwritten by an in-flight reader still finishing its yield loop.

---

## Onboard flow

When CONNECT is forbidden but trust config defines onboard methods:

```
Server → ONBOARD_REQUIRED {methods: [invite_code, payment], payment_amount?, payment_address?}
Client → ONBOARD_SUBMIT   {payload: {invite_code: "BETA2024"}}
Server → ONBOARD_SUCCESS  {level: "contact"}    or    ERROR
```

`handle_onboard_submit` verifies signature with "open" trust (strangers can't pass strict verification yet), checks blocked status, then validates the invite code or payment via `trust_agent`. On success the client is promoted.

The original CONNECT that the trust gate interrupted is completed server-side: `handle_connect` stashes it as `conn["pending_connect"]`, and after verified onboard the session loop calls `establish_connection()` with the onboard-verified identity, ending in `CONNECTED`. The client does not re-send CONNECT, so its pending `INPUT` can resume even if the original signature has aged while the user typed an invite code or completed payment. The stash is popped only on a **successful** onboard — a failed submit (e.g. wrong invite code) keeps it, so a retry on the same socket can still complete the interrupted CONNECT.

---

## Admin flow

`ADMIN_*` messages let admins manage trust levels remotely. Each admin message carries its own auth (signature verified independently per message).

```
Client → ADMIN_PROMOTE {payload: {client_id: "0x..."}}
Server → ADMIN_RESULT  {action: promote, success: true, level: contact}
```

| Action | Requires | Handler key |
|---|---|---|
| `ADMIN_PROMOTE` | admin | `admin_trust_promote` |
| `ADMIN_DEMOTE`  | admin | `admin_trust_demote`  |
| `ADMIN_BLOCK`   | admin | `admin_trust_block`   |
| `ADMIN_UNBLOCK` | admin | `admin_trust_unblock` |
| `ADMIN_GET_LEVEL` | admin | `admin_trust_level` |
| `ADMIN_ADD`     | super_admin | `admin_admins_add`    |
| `ADMIN_REMOVE`  | super_admin | `admin_admins_remove` |

---

## Key files

| File | Role |
|---|---|
| `network/host/ws_router/__init__.py` | Public re-export: `run_ws_session` |
| `network/host/ws_router/session.py` | Main loop, dispatch chain, inline helpers (PONG, SESSION_STATUS, runtime input) |
| `network/host/ws_router/connect.py` | `handle_connect` — CONNECT auth, session merge, reattach trigger |
| `network/host/ws_router/agent_io.py` | `start_agent`, `resume_forwarding`, `forward_agent_msgs_to_client`, `_agent_thread_body` |
| `network/host/ws_router/ping.py` | `ping_loop` keepalive |
| `network/asgi/websocket.py` | ASGI adapter — wraps ASGI WS into send_msg/recv_msg |
| `network/relay.py` | Relay adapter — wraps relay WS + per-session queue into send_msg/recv_msg |
| `network/io/websocket.py` | `WebSocketIO` — three channels, thread-safe, cursor-indexed replay |
| `network/host/session/active.py` | `ActiveSessionRegistry` — running/connected sessions |
| `network/host/session/storage.py` | `SessionStorage` — JSONL persistence |
| `network/host/session/ui.py` | `session_to_chat_items` — convert session → ChatItem[] for UI |
| `network/host/server.py` | `host()` entry point. Wires `run_ws_session` into ASGI app and as `relay_session_runner` partial for the relay path |
| `useful_plugins/runtime_input.py` | `apply_runtime_input` `@before_iteration` plugin + `RUNTIME_INPUT_FRAME_PREFIX` |
