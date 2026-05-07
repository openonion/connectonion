# Transport-Agnostic Protocol Handler

> `connectonion/network/host/ws_router.py` — shared protocol logic for both ASGI WebSocket and relay paths.

---

## Why

Before this module, the WebSocket protocol (CONNECT, INPUT, streaming, onboard, admin) lived inside the ASGI handler (`websocket.py`). The relay path had to open a **loopback WebSocket** back to `ws://127.0.0.1:{port}/ws` to reuse that logic — an extra network hop and a layer of complexity.

Now the protocol logic is extracted into `ws_router.py` with a transport-agnostic interface. Both paths call `dispatch_message_loop()` directly with their own adapters:

```
Client → ASGI websocket.py → send_msg/recv_msg adapter → dispatch_message_loop()
Client → Relay relay.py    → send_msg/recv_msg adapter → dispatch_message_loop()
```

No loopback. Same protocol. Two thin adapters.

---

## Interface

```python
async def dispatch_message_loop(
    send_msg,       # async (dict) -> None
    recv_msg,       # async () -> dict | None  (None = disconnected)
    *,
    route_handlers, # dict of handler functions (auth, ws_input, trust_agent, admin_*)
    storage,        # SessionStorage instance
    registry,       # ActiveSessionRegistry
    trust,          # TrustAgent or trust level string
    blacklist=None,
    whitelist=None,
    enable_ping=True,  # False for relay (relay has ANNOUNCE heartbeat)
)
```

`send_msg` and `recv_msg` are the only transport-specific pieces. Everything else is shared.

---

## Transport Adapters

### ASGI (`websocket.py`, ~60 lines)

```python
async def send_msg(data):
    await ws_send({"type": "websocket.send", "text": json.dumps(data, default=pydantic_json_encoder)})

async def recv_msg():
    msg = await ws_receive()
    if msg["type"] == "websocket.disconnect":
        return None
    return json.loads(msg["text"])
```

### Relay (`relay.py`)

```python
async def send_msg(data):
    data["session_id"] = session_id
    await relay_ws.send(json.dumps(data, default=pydantic_json_encoder))

async def recv_msg():
    msg = await asyncio.wait_for(q.get(), timeout=300)  # 5min idle timeout
    if msg is None or msg.get("type") == "close":
        return None
    return msg
```

Relay's `recv_msg` reads from an `asyncio.Queue` populated by `serve_loop`. The 300s timeout prevents zombie sessions when the client disappears without sending a close signal.

---

## Message Dispatch

`dispatch_message_loop` maintains connection state in a mutable dict and dispatches by message type:

```python
conn = {"authenticated": False, "identity": None, "session_id": None, "session": None}

while True:
    data = await recv_msg()
    if data is None:
        break

    match data["type"]:
        "SESSION_STATUS" → _handle_session_status()
        "ONBOARD_SUBMIT" → handle_onboard_submit()
        "ADMIN_*"        → handle_admin_message()
        "CONNECT"        → _handle_connect()     # sets conn["authenticated"]
        "INPUT"          → _start_agent()         # requires conn["authenticated"]
```

`CONNECT` must come first — it authenticates and populates `conn`. `INPUT` checks `conn["authenticated"]` before proceeding.

`SESSION_STATUS`, `ONBOARD_SUBMIT`, and `ADMIN_*` don't require prior CONNECT — they carry their own auth.

---

## CONNECT Flow

```
Client → CONNECT {from, signature, payload: {timestamp}, session_id?}
```

1. **Auth**: `route_handlers["auth"](data, trust)` verifies Ed25519 signature
2. **Forbidden + onboard**: If auth returns "forbidden" and trust config has onboard methods (invite_code, payment), sends `ONBOARD_REQUIRED` instead of ERROR
3. **Session merge**: If `session_id` provided, loads stored session and merges with client's (whichever has more messages wins)
4. **Registry check**: Looks up session in `ActiveSessionRegistry`:
   - `running` → agent is running (client reconnected mid-execution)
   - `connected`/`disconnected` → agent finished, session alive (returned to client as `"connected"`)
   - not found → `new`
5. **Send CONNECTED**: `{session_id, status, server_newer?, session?, chat_items?}`
6. **Reattach**: If `status == "running"`, pipes buffered events and resumes IO bridge

---

## INPUT Flow

```
Client → INPUT {prompt, images?, files?}
```

1. **Validate**: Must be authenticated, prompt required
2. **Create IO bridge**: `WebSocketIO` (thread-safe queue pair for sync agent ↔ async transport)
3. **Start agent thread**: `route_handlers["ws_input"]()` runs in a daemon thread
4. **Bridge IO**: Three concurrent async tasks pipe messages until agent completes or client disconnects
5. **Result**: Agent done → send `OUTPUT`; client disconnected → `mark_session_disconnected` (agent keeps running)

---

## Agent IO Bridge

The agent runs in a synchronous thread (LLM calls are blocking). The client is on the async event loop. `_pipe_agent_io` bridges them with three tasks:

```
Agent thread                          Async event loop                    Client
     │                                      │                               │
     │─ io.send(event) ─► _outgoing queue ─►│─ _pump_agent_events ────────►│
     │                                      │                               │
     │◄─ io._incoming queue ◄───────────────│◄─ _pump_client_messages ─────│
     │                                      │                               │
     │                                      │─ _send_ping (30s) ──────────►│
```

- **`_pump_agent_events_to_client`**: Drains `io._outgoing` queue, sends each event to client. After `agent_finished`, flushes remaining events.
- **`_pump_client_messages_to_agent`**: Reads from `recv_msg`, puts into `io._incoming` queue. Returns None → sets `disconnected` event.
- **`_send_ping`**: 30s keepalive. Disabled for relay (`enable_ping=False`) because relay has its own ANNOUNCE heartbeat. If send fails, sets `disconnected` to signal other tasks.

`_pipe_agent_io` returns `True` if client disconnected first (session marked disconnected), `False` if agent completed normally.

---

## Onboard Flow

When CONNECT is forbidden but trust config defines onboard methods:

```
Server → ONBOARD_REQUIRED {methods: ["invite_code", "payment"], payment_amount?, payment_address?}
Client → ONBOARD_SUBMIT {payload: {invite_code: "BETA2024"}}
Server → ONBOARD_SUCCESS {level: "contact"} or ERROR
```

`_handle_onboard_submit` verifies signature (with "open" trust — strangers can't be verified strictly), checks blocked status, then validates invite code or payment via `trust_agent`. On success, the client is promoted and can re-CONNECT.

---

## Admin Flow

`ADMIN_*` messages let admins manage trust levels remotely. Every admin message carries its own auth (signature verified independently).

```
Client → ADMIN_PROMOTE {payload: {client_id: "0x..."}}
Server → ADMIN_RESULT {action: "promote", success: true, level: "contact"}
```

| Action | Requires | Handler key |
|--------|----------|-------------|
| `ADMIN_PROMOTE` | admin | `admin_trust_promote` |
| `ADMIN_DEMOTE` | admin | `admin_trust_demote` |
| `ADMIN_BLOCK` | admin | `admin_trust_block` |
| `ADMIN_UNBLOCK` | admin | `admin_trust_unblock` |
| `ADMIN_GET_LEVEL` | admin | `admin_trust_level` |
| `ADMIN_ADD` | super_admin | `admin_admins_add` |
| `ADMIN_REMOVE` | super_admin | `admin_admins_remove` |

---

## Safety Mechanisms

### Agent thread crash recovery

`_run_agent_thread` wraps execution in `try/finally` to guarantee `agent_finished.set()`. Without this, an agent exception would leave the async IO bridge spinning forever — the thread dies silently (threads don't propagate exceptions), but the async side never gets the signal.

### Relay session idle timeout

Relay's `recv_msg` uses `asyncio.wait_for(q.get(), timeout=300)`. If no message arrives for 5 minutes, returns None, causing `dispatch_message_loop` to exit and the session to clean up. Prevents zombie sessions when the client disappears without a close signal.

### Relay disconnect cleanup

When `serve_loop` exits on `ConnectionClosed`, it sends `None` to all session queues before breaking. This unblocks every `recv_msg` waiting on `q.get()`, allowing all `_run_session` coroutines to exit cleanly.

### Ping failure detection

`_send_ping` catches send failures and sets `disconnected`, signaling the other IO bridge tasks to stop. Without this, a dead connection would only be detected when the next send/recv attempt fails.

---

## Key Files

| File | Role |
|------|------|
| `network/host/ws_router.py` | Transport-agnostic protocol handler (this module) |
| `network/asgi/websocket.py` | ASGI adapter — wraps ASGI primitives into send_msg/recv_msg |
| `network/relay.py` | Relay adapter — wraps asyncio.Queue/relay WS into send_msg/recv_msg |
| `network/io/websocket.py` | WebSocketIO — thread-safe queue bridge between sync agent and async transport |
| `network/host/session/active.py` | ActiveSessionRegistry — in-memory session tracking |
| `network/host/session/storage.py` | SessionStorage — JSONL persistence |
| `network/host/server.py` | Wires `dispatch_message_loop` into both ASGI app and relay via `functools.partial` |
