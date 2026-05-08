# WebSocket Message Router

> `connectonion/network/host/ws_router.py` — single message-routing implementation, used by both the direct ASGI WebSocket path and the relay-routed path.

---

## Why one router

Earlier the WebSocket message handling (CONNECT auth, INPUT → spawn agent, streaming back, onboard, admin, ...) lived inside the ASGI handler. The relay path opened a **loopback WebSocket** back to `ws://127.0.0.1:{port}/ws` to reuse it — extra hop, extra moving parts, double maintenance.

Now the message-routing logic is extracted into `ws_router.py` with a transport-agnostic interface. Both paths call `run_session()` directly with their own adapters:

```
Client → ASGI websocket.py → send_msg/recv_msg adapter ─┐
                                                         ├─→ run_session()
Client → Relay relay.py    → send_msg/recv_msg adapter ─┘
```

No loopback. Same router. Two thin adapters.

---

## Public entry: `run_session`

```python
async def run_session(
    send_msg,       # async (dict) -> None
    recv_msg,       # async () -> dict | None  (None = client closed)
    *,
    route_handlers, # dict: auth, ws_input, trust_agent, admin_*
    storage,        # SessionStorage
    registry,       # ActiveSessionRegistry
    trust,          # TrustAgent or trust level string
    blacklist=None,
    whitelist=None,
    enable_ping=True,  # False for relay path (it has ANNOUNCE heartbeat instead)
)
```

`send_msg` and `recv_msg` are the only transport-specific pieces. Everything else is shared.

Each call to `run_session` drives **one client session** from connect to disconnect:

```python
state = _init_session(send_msg, enable_ping)
try:
    while True:
        data = await recv_msg()
        if data is None:           # client closed
            break
        await route_message(data, state, ...)
finally:
    await _cleanup_session(state)
```

---

## Per-session state

`_init_session` returns a mutable dict:

```python
{
    "conn":         {"authenticated": False, "identity": None, "session_id": None, "session": None},
    "active_io":    None,           # WebSocketIO once an agent is running
    "forward_task": None,           # asyncio.Task forwarding agent → client
    "ping_task":    asyncio.Task,   # 30s keepalive, None when enable_ping=False
}
```

`route_message` mutates the dict in place — `conn` flips to authenticated on CONNECT; `active_io` and `forward_task` get assigned when an agent starts.

`_cleanup_session` cancels `forward_task` and `ping_task` and awaits their CancelledError unwind. Standard asyncio cancel idiom.

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
    msg = await asyncio.wait_for(q.get(), timeout=300)   # 5min idle timeout
    if msg is None or msg.get("type") == "close":
        return None
    return msg
```

Relay's `recv_msg` reads from a per-session `asyncio.Queue` populated by `serve_loop`. The 300s idle timeout prevents zombie sessions if the client vanishes without a close signal.

---

## Message dispatch (`route_message`)

```python
async def route_message(data, state, send_msg, route_handlers, storage, registry, trust, ...):
    msg_type = data.get("type")
    match msg_type:
        "PONG"           → registry.update_ping(...)
        "SESSION_STATUS" → _handle_session_status(...)
        "ONBOARD_SUBMIT" → handle_onboard_submit(...)
        "ADMIN_*"        → handle_admin_message(...)
        "CONNECT"        → _handle_connect(...)        # auth + maybe reattach to running agent
        "INPUT"          → _try_runtime_input(...) OR _start_agent(...)
        else (with active_io) → active_io.send_to_agent(data)   # ASK_USER_RESPONSE, APPROVAL_RESPONSE, etc.
```

`CONNECT` must come first — it authenticates and populates `state["conn"]`. `INPUT` and most others require `conn["authenticated"] == True`.

`SESSION_STATUS`, `ONBOARD_SUBMIT`, and `ADMIN_*` carry their own auth and don't require prior CONNECT.

---

## CONNECT flow

```
Client → CONNECT {from, signature, payload, session_id?, last_msg_id?, session?}
```

1. **Auth** — `route_handlers["auth"](data, trust)` verifies Ed25519 signature.
2. **Forbidden + onboard** — if auth returns "forbidden" and trust config defines onboard methods (invite_code / payment), server sends `ONBOARD_REQUIRED` instead of ERROR.
3. **Session merge** — if `session_id` provided, loads stored session and merges with client's via `merge_sessions` (whichever is newer wins).
4. **Registry check** — looks up session in `ActiveSessionRegistry`:
   - `running` → agent is mid-execution; client is reconnecting, reattach.
   - `connected` → agent finished; session alive, ready for next INPUT.
   - not found → `new`.
5. **Send CONNECTED** — `{session_id, status, server_newer?, session?, chat_items?}`. The optional fields appear only when the server has newer data than the client.
6. **Reattach (running only)** — call `active.io.rewind_to(last_msg_id)` to reset the message cursor, then start a new forward task that replays everything after `last_msg_id`. See [session-reconnect.md](session-reconnect.md) for the cursor semantics.

Server session statuses: only `'running'` and `'connected'`. WS disconnect doesn't change `session.status` — IO queues survive the WS, a reconnecting client just re-subscribes.

---

## INPUT flow

```
Client → INPUT {prompt, images?, files?}
```

Two paths depending on whether an agent is already running:

**Fresh agent (`_start_agent`)** when `registry.get(session_id)` is None or `connected`:
1. Validate (`conn["authenticated"]`, `prompt` non-empty).
2. Create `WebSocketIO` (thread-safe queue pair: agent ↔ async transport).
3. Register in `ActiveSessionRegistry` BEFORE `agent_thread.start()` — registering after creates a race where a fast-completing agent calls `mark_session_connected` on an absent entry.
4. Spawn daemon thread running `route_handlers["ws_input"]` (which calls user's `create_agent` factory and runs `agent.input(prompt)`).
5. Spawn `forward_task` to pipe `io.read_msgs_from_agent()` events out via `send_msg`. On agent completion, sends `OUTPUT`.

**Runtime input (`_try_runtime_input`)** when `existing.status == 'running'`:
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
     │   ASK_USER_RESPONSE)                  │   in route_message)        │
     │                                       │                            │
     │  io.pop_runtime_inputs() (separate    │   push_runtime_input from  │
     │  queue, drained at iteration start    │   _try_runtime_input on    │
     │  by apply_runtime_input plugin)       │   INPUT-during-running     │
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

`_run_agent_thread` wraps execution in `try/except Exception`, captures the exception in `result_holder[0]`, and always calls `io.finish()` in `finally`. The forwarder reads `result_holder` after `read_msgs_from_agent` returns and emits `{type: ERROR, message: <exception>}` to the client. Threads don't propagate exceptions on their own — this is the manual surfacing.

### Relay session idle timeout (5 minutes)

Relay's `recv_msg` uses `asyncio.wait_for(q.get(), timeout=300)`. No message for 5 minutes → returns None → `run_session` exits → cleanup. Prevents zombie sessions when a client vanishes without close.

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

`handle_onboard_submit` verifies signature with "open" trust (strangers can't pass strict verification yet), checks blocked status, then validates the invite code or payment via `trust_agent`. On success the client is promoted and can re-CONNECT.

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
| `network/host/ws_router.py` | Public `run_session` + `route_message` + helpers (this module) |
| `network/asgi/websocket.py` | ASGI adapter — wraps ASGI WS into send_msg/recv_msg |
| `network/relay.py` | Relay adapter — wraps relay WS + per-session queue into send_msg/recv_msg |
| `network/io/websocket.py` | `WebSocketIO` — three channels, thread-safe |
| `network/host/session/active.py` | `ActiveSessionRegistry` — running/connected sessions |
| `network/host/session/storage.py` | `SessionStorage` — JSONL persistence |
| `network/host/session/ui.py` | `session_to_chat_items` — convert session → ChatItem[] for UI |
| `network/host/server.py` | `host()` entry point. Wires `run_session` into ASGI app and as `relay_session_runner` partial for the relay path |
| `useful_plugins/runtime_input.py` | `apply_runtime_input` `@before_iteration` plugin + `RUNTIME_INPUT_FRAME_PREFIX` |
