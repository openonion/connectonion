# WebSocket Protocol

> Connect first, then message. The connection IS the session.

---

## Overview

The WebSocket protocol separates **connection** from **messaging**. This follows the same pattern as Socket.IO, Phoenix Channels, and ActionCable.

```
┌─────────────────────────────────────────────────────────────┐
│                    WebSocket Lifecycle                        │
│                                                              │
│   1. Open WebSocket                                         │
│   2. CONNECT  →  authenticate + link to agent + get session │
│   3. INPUT    →  send prompt (as many as needed)            │
│   4. Close    →  session survives for reconnection          │
│                                                              │
│   On reconnect: CONNECT with session_id → resume            │
└─────────────────────────────────────────────────────────────┘
```

**Two message types, two concerns:**

| Message | Purpose |
|---------|---------|
| `CONNECT` | Authenticate, link to agent, allocate or resume session |
| `INPUT` | Send a prompt to the agent |

Everything else (OUTPUT, PING, events) flows from the server.

---

## Protocol Flow

### New Session

```
Client                                    Server
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ───────────────────────────►│  verify signature
  │   { to, auth }                         │  create agent instance
  │                                         │  allocate session_id
  │                                         │
  │◄── CONNECTED ─────────────────────────│  { session_id, status: "new" }
  │                                         │
  │◄── PING ──────────────────────────────│  keep-alive starts (every 30s)
  │── PONG ──────────────────────────────►│
  │                                         │
  │── INPUT ─────────────────────────────►│  run agent with prompt
  │   { prompt }                           │
  │                                         │
  │◄── thinking ──────────────────────────│  stream events
  │◄── tool_call ─────────────────────────│
  │◄── tool_result ───────────────────────│
  │◄── OUTPUT ────────────────────────────│  { result, session }
  │                                         │
  │── INPUT ─────────────────────────────►│  another prompt, same session
  │   { prompt }                           │
  │◄── ... ───────────────────────────────│
  │◄── OUTPUT ────────────────────────────│
```

### Reconnect After Disconnect

```
Client                                    Server
  │                                         │
  │    (agent still running on server)      │
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ───────────────────────────►│  verify signature
  │   { to, session_id, auth }             │  registry.get(session_id)
  │                                         │  → found, status: running
  │                                         │  reattach IO queues
  │                                         │
  │◄── CONNECTED ─────────────────────────│  { session_id, status: "running" }
  │◄── buffered event ───────────────────│  drain queued events
  │◄── buffered event ───────────────────│
  │◄── PING ──────────────────────────────│  keep-alive resumes
  │── PONG ──────────────────────────────►│
  │                                         │
  │◄── stream events ─────────────────────│  live again
  │◄── OUTPUT ────────────────────────────│
```

### Reconnect After Session Completed

```
Client                                    Server
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ───────────────────────────►│  registry.get(session_id)
  │   { to, session_id, auth }             │  → found, status: completed
  │                                         │
  │◄── CONNECTED ─────────────────────────│  { session_id, status: "completed",
  │                                         │    result: "..." }
```

### Reconnect After Session Expired

```
Client                                    Server
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ───────────────────────────►│  registry.get(session_id)
  │   { to, session_id, auth }             │  → not found
  │                                         │
  │◄── CONNECTED ─────────────────────────│  { session_id, status: "expired" }
```

---

## Message Reference

### Client → Server

#### CONNECT

First message after WebSocket opens. Authenticates and links to an agent.

```json
{
  "type": "CONNECT",
  "to": "0x3d4017c3e843...",
  "session_id": "550e8400-...",
  "payload": {
    "to": "0x3d4017c3e843...",
    "timestamp": 1702234567
  },
  "from": "0xClientPublicKey",
  "signature": "0x..."
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `to` | Yes | Agent's public address |
| `session_id` | No | Existing session to resume. Omit for new session. |
| `payload` | Yes | Signed payload for authentication |
| `from` | Yes | Client's public address |
| `signature` | Yes | Ed25519 signature of payload |

#### INPUT

Send a prompt to the connected agent. Only valid after CONNECTED.

```json
{
  "type": "INPUT",
  "prompt": "Translate hello to Spanish",
  "images": ["data:image/png;base64,..."],
  "files": [{ "name": "doc.pdf", "data": "data:application/pdf;base64,..." }]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `prompt` | Yes | Natural language prompt |
| `images` | No | Base64 data URLs |
| `files` | No | Named file attachments |

No signature needed — the WebSocket connection is already authenticated by CONNECT.

#### PONG

Acknowledge server PING. Send immediately on receiving PING.

```json
{ "type": "PONG" }
```

#### ASK_USER_RESPONSE

Answer an agent's question.

```json
{ "type": "ASK_USER_RESPONSE", "answer": "Python 3" }
```

#### APPROVAL_RESPONSE

Approve or reject a tool execution.

```json
{ "type": "APPROVAL_RESPONSE", "approved": true, "scope": "once" }
```

#### SESSION_STATUS

Check if a session exists without connecting to it.

```json
{ "type": "SESSION_STATUS", "session": { "session_id": "550e8400-..." } }
```

### Server → Client

#### CONNECTED

Response to CONNECT. Contains session info.

```json
{
  "type": "CONNECTED",
  "session_id": "550e8400-...",
  "status": "new"
}
```

| `status` | Meaning |
|----------|---------|
| `"new"` | New session allocated |
| `"running"` | Resumed — agent still executing. Buffered events follow. |
| `"completed"` | Session finished. Result included. |
| `"expired"` | Session no longer in memory. Poll `/sessions/{id}` for result. |

#### OUTPUT

Agent completed. Contains result and session state.

```json
{
  "type": "OUTPUT",
  "result": "Hola",
  "session_id": "550e8400-...",
  "duration_ms": 1250,
  "session": {
    "session_id": "550e8400-...",
    "messages": [...],
    "trace": [...],
    "turn": 2
  }
}
```

#### PING

Keep-alive. Sent every 30 seconds. Client must respond with PONG.

```json
{ "type": "PING" }
```

#### Stream Events

Sent during agent execution:

| Type | Description |
|------|-------------|
| `thinking` | Agent reasoning |
| `tool_call` | Tool execution started |
| `tool_result` | Tool execution completed |
| `ask_user` | Agent needs human input |
| `approval_needed` | Tool requires approval |
| `plan_review` | Plan ready for review |
| `compact` | Context compaction |
| `intent` | Intent analysis |

#### ERROR

```json
{ "type": "ERROR", "message": "Something went wrong" }
```

---

## Authentication

Authentication happens once, on CONNECT. Ed25519 signature proves identity.

```
CONNECT (signed)          INPUT (not signed)
  │                          │
  ▼                          ▼
Server verifies            Server trusts
signature → OK             (same WS connection,
                            already authenticated)
```

**Why not sign every message?**

The WebSocket is a point-to-point TCP connection over TLS (WSS). Once authenticated:
- TLS encrypts everything in transit
- Only the connected client can send messages on this socket
- No one can inject messages into an existing WS connection

Signing every message would be redundant. The connection itself is the trust boundary.

**Trust levels still apply:**

| Trust Level | CONNECT Behavior |
|-------------|-----------------|
| `open` | Accept without signature |
| `careful` | Accept unsigned, recommend signature |
| `strict` | Require valid signature |

---

## Connection vs Messaging

### Before (v0.8.x)

INPUT did everything — authenticate, connect, allocate session, send prompt:

```
WS open → INPUT { prompt, session, auth } → events → OUTPUT → WS close
WS open → INPUT { prompt, session, auth } → events → OUTPUT → WS close
           ↑ re-authenticate every time
           ↑ new WS connection per message
```

### After (v0.9.x)

CONNECT and INPUT are separate concerns:

```
WS open → CONNECT { auth } → CONNECTED
           INPUT { prompt } → events → OUTPUT
           INPUT { prompt } → events → OUTPUT
           INPUT { prompt } → events → OUTPUT
           ↑ one connection, multiple messages
           ↑ authenticate once
```

| Concern | Before | After |
|---------|--------|-------|
| Authentication | Every INPUT | Once on CONNECT |
| Session allocation | Implicit in INPUT | Explicit in CONNECT |
| Reconnection | Send INPUT with empty prompt (hack) | Send CONNECT with session_id |
| Multiple messages | New WS per message | Same WS connection |
| Separation | Mixed | Clean |

---

## Client Auto-Reconnect

After a page refresh or network drop, the client should automatically reconnect:

```
Page loads
  │
  ▼
Zustand hydrates from localStorage
  │
  ├── session_id exists?
  │     │
  │     ▼
  │   Open WebSocket
  │   Send CONNECT { session_id }
  │     │
  │     ├── CONNECTED { status: "running" }
  │     │     → receive buffered events
  │     │     → resume live streaming
  │     │
  │     ├── CONNECTED { status: "completed" }
  │     │     → show cached result
  │     │
  │     └── CONNECTED { status: "expired" }
  │           → show cached UI as history
  │
  └── no session?
        → show empty state
```

The client reconnects automatically. No "Retry" button needed.

---

## Comparison with Other Protocols

| Protocol | Connect | Message | Reconnect |
|----------|---------|---------|-----------|
| Socket.IO | CONNECT { sid } | MESSAGE { data } | CONNECT { sid } |
| Phoenix Channels | JOIN { topic } | PUSH { event } | JOIN { topic } |
| ActionCable | SUBSCRIBE { channel } | MESSAGE { data } | SUBSCRIBE { channel } |
| **ConnectOnion** | **CONNECT { to, session_id }** | **INPUT { prompt }** | **CONNECT { session_id }** |

Same pattern. Connect first, then message.

---

## Key Files

| File | Role |
|------|------|
| `network/asgi/websocket.py` | WebSocket handler — CONNECT/INPUT routing |
| `network/host/session/active.py` | ActiveSessionRegistry — in-memory session tracking |
| `network/io/websocket.py` | WebSocketIO — queue bridge between async/sync |
| `network/host/session/storage.py` | SessionStorage — JSONL persistence |
| `network/host/session/merge.py` | Session merge conflict resolution |
