# Client-Side WebSocket Reconnection

How the TypeScript SDK and React hooks manage WebSocket connections, session persistence, and reconnection after page refresh.

> Server-side counterpart: [session-reconnect.md](session-reconnect.md)

---

## Architecture

Three layers handle client-side connection:

```
┌─────────────────────────────────────────────────────────────┐
│  oo-chat (useAgentSDK)                                       │
│  Maps connectionState → UI session states                    │
│  Exposes respondToApproval(), reconnect()                    │
├─────────────────────────────────────────────────────────────┤
│  React Hook (useAgentForHuman)                               │
│  Session persistence via Zustand → localStorage              │
│  Restores session on mount, syncs on every event             │
├─────────────────────────────────────────────────────────────┤
│  RemoteAgent                                                 │
│  WebSocket lifecycle, CONNECT/INPUT protocol                 │
│  Ping monitor, session merge, reconnect()                    │
└─────────────────────────────────────────────────────────────┘
```

---

## RemoteAgent: WebSocket Lifecycle

File: `connectonion-ts/src/connect/remote-agent.ts`

### State

```typescript
_ws: WebSocketLike | null     // Active WebSocket (null when disconnected)
_authenticated: boolean        // CONNECT handshake complete
_connectionState: 'disconnected' | 'connected' | 'reconnecting'
_currentSession: SessionState  // Conversation history + mode
_chatItems: ChatItem[]         // UI events for rendering
_lastPingTime: number          // Timestamp of last PING from server
_pingTimer: interval           // 10s check: close if no PING in 60s
```

### connect() → _ensureConnected()

Every `input()` call goes through `_ensureConnected()`:

```
input(prompt)
  │
  ▼
_ensureConnected()
  │
  ├─ _ws exists + authenticated? → skip, send INPUT directly
  │
  └─ no connection:
       1. Resolve endpoint (relay or direct URL)
       2. new WebSocket(url)
       3. Send CONNECT { session_id, session, from, signature }
       4. Wait for CONNECTED (30s timeout)
       5. If server_newer: replace _currentSession + _chatItems
       6. _authenticated = true
       7. Send INPUT { prompt }
```

### send() — the error point

```typescript
send(message) {
  if (!this._ws) throw new Error('No active connection');
  this._ws.send(JSON.stringify(message));
}
```

Called by `respondToApproval()` and `sendMessage()`. Throws when `_ws` is null — after any connection loss, before `reconnect()` is called.

### reconnect()

```
reconnect(sessionId?)
  │
  1. _closeWs() — force close existing WS, null handlers, _ws = null
  2. new WebSocket(url)
  3. connectionState = 'reconnecting'
  4. On open: send CONNECT { session_id, session }
  5. Wait for CONNECTED (60s timeout)
  │
  ├─ status = 'running'   → wait for streaming events + OUTPUT
  ├─ status = 'connected' → resolve immediately (session alive, idle)
  └─ status = 'new'       → resolve immediately (session expired)
```

### _handleConnectionLoss() — unexpected disconnect

```
WebSocket closes unexpectedly (error, network drop)
  │
  1. _ws = null
  2. _authenticated = false
  3. Stop ping monitor
  4. Reject _connectReject if waiting for CONNECT handshake
  5. Reject _inputReject if waiting for INPUT response
  │
  → connectionState = 'disconnected'
  → UI shows error, user must call reconnect()
```

### _closeWs() — intentional close

```
_closeWs()
  │
  1. Stop ping monitor
  2. ws.onerror = null, ws.onclose = null, ws.onmessage = null
     (prevent ghost events after close)
  3. ws.close()
  4. _ws = null
  5. _authenticated = false
  6. connectionState = 'disconnected'
```

### _handleMessage() — message routing

Handles all incoming WebSocket messages:

| Message Type | Action |
|---|---|
| PING | Respond PONG, update _lastPingTime |
| CONNECTED | Resolve _ensureConnected() promise, merge session |
| SESSION_MERGED, session_sync | Update _currentSession |
| mode_changed | Update approval mode |
| thinking, tool_call, tool_result, llm_call, llm_result | Map to ChatItem via chat-item-mapper, append to _chatItems |
| approval_needed, ask_user, plan_review | Map to ChatItem, set status = 'waiting' |
| OUTPUT | Resolve input() promise, update session |
| ERROR | Reject with error message, disconnect |

Every message triggers `onMessage()` callback → React state sync.

### Ping monitor

- Starts on successful CONNECT
- Every 10s: check if server sent PING within last 60s
- If no PING in 60s → close WS as dead connection
- Stops on any disconnection

### checkSessionStatus()

Two paths:

```
checkSessionStatus(sessionId)
  │
  ├─ _ws exists + authenticated:
  │    Send SESSION_STATUS over existing WS
  │    Wait for response (10s timeout)
  │    Return: 'running' | 'connected' | 'not_found'
  │
  └─ no active WS:
       Open temporary WS just for status check
       Send SESSION_STATUS
       Wait for response
       Close temporary WS
       Return status
```

---

## React Hook: useAgentForHuman

File: `connectonion-ts/src/react/use-agent-for-human.ts`

### Session persistence

Zustand store → localStorage:
- `session` — conversation history (messages, trace, turn, mode)
- `ui` — ChatItem[] for rendering
- `sessionId` — stable session identifier
- `messages` — message array

### Page refresh flow

```
Page loads
  │
  ▼
Zustand hydrates from localStorage
  │ session, ui, sessionId, messages restored
  │
  ▼
useEffect([sessionId])
  │
  ├─ agent._currentSession = { ...session, session_id: sessionId }
  ├─ agent._chatItems = [...ui]
  │
  └─ NO auto-reconnect
     UI shows cached conversation from localStorage
     WebSocket only opens on next input() or explicit reconnect()
```

**Key design decision**: No auto-reconnect on mount. Cached conversation renders instantly from localStorage. WebSocket opens lazily on next user action.

### input() — merges session before sending

```
input(prompt, options?)
  │
  1. Clear error state
  2. Merge sessions:
     agent._currentSession = {
       ...agent session      (preserves mode from setMode())
       ...zustand session    (overlay store data)
       session_id            (ensure correct ID)
       messages              (from store)
     }
  3. Restore chatItems if agent empty but store has data
  4. agent.input(prompt, options)
     → _ensureConnected() opens WS if needed
     → CONNECT with session → server merges → INPUT sent
```

### reconnect() — restores session first

```
reconnect()
  │
  1. If agent has no session_id: set from Zustand store
  2. Restore chatItems from store if agent is empty
  3. agent.reconnect(sessionId)
     → _closeWs() force close
     → new WS
     → CONNECT with session
     → server responds with status
```

### onMessage callback — syncs everything

```
Every WebSocket event
  │
  ▼
agent.onMessage()
  │
  ├─ setUI([...agent.ui])                      → Zustand → localStorage
  ├─ setStatus(agent.status)                    → Zustand → localStorage
  ├─ setConnectionState(agent.connectionState)  → Zustand → localStorage
  ├─ setSession(agent.currentSession)           → Zustand → localStorage
  └─ updateMessages(agent.currentSession.messages)
```

Every streaming event (thinking, tool_call, etc.) triggers full state sync to localStorage. After refresh, UI restores exactly where it was — including pending approval cards.

### setMode() — mirrors immediately

```typescript
setMode(newMode, options?)
  1. agent.setMode(newMode, options)        // Sends to server
  2. Update Zustand store immediately       // UI reflects before server sync
```

---

## oo-chat: useAgentSDK

File: `oo-chat/components/chat/use-agent-sdk.ts`

Thin wrapper over `useAgentForHuman`:

### Session state mapping

```
connectionState    →  sessionState (UI)
'reconnecting'     →  'reconnecting'
'connected'        →  'active'
(disconnected)     →  'disconnected'  (if server session alive)
(disconnected)     →  'connected'     (if has cached UI)
(disconnected)     →  'idle'          (empty)
```

### respondToApproval()

```typescript
respondToApproval(approved, scope, mode?, feedback?)
  │
  ▼
sendMessage({
  type: 'APPROVAL_RESPONSE',
  approved: boolean,
  scope: 'once' | 'session',
  mode?,      // 'reject_soft' | 'reject_hard' | 'reject_explain'
  feedback?,  // User explanation for rejection
})
  │
  ▼
agent.send(message)
  │
  └─ if _ws === null → throw 'No active connection'
```

### Polls session status

After processing completes, polls `checkSessionStatus()` every 10s to detect if server session is still alive.

---

## Auth & Signing

File: `connectonion-ts/src/connect/auth.ts`

Every CONNECT message is signed with Ed25519:

```
ensureKeys()
  │
  ├─ Browser: load from localStorage, or generate + save
  └─ Node: load from file, or generate

signPayload(keys, payload)
  │
  1. Canonical JSON (sorted keys)
  2. Ed25519 sign with private key
  3. Return { payload, from: address, signature, timestamp }
```

---

## ChatItem Mapper

File: `connectonion-ts/src/connect/chat-item-mapper.ts`

Converts server events into `ChatItem[]` for React rendering:

| Server Event | ChatItem Behavior |
|---|---|
| tool_call | Create new item with status='running' |
| tool_result | Find matching tool_call, update status + result |
| llm_call | Create thinking item with status='running' |
| llm_result | Find matching llm_call, update status + usage |
| thinking, assistant | Add text content item |
| approval_needed | Add approval item (shows Approve/Deny buttons) |
| ask_user | Add question item (shows input field) |
| plan_review | Add plan item (shows Accept/Reject) |

---

## Known Issue: "No active connection" on Refresh

### Reproduction

```
1. Agent running, waiting for bash approval
2. User refreshes browser
3. Page reloads, Zustand hydrates from localStorage
4. UI shows cached bash approval card (Approve/Deny buttons)
5. User clicks "Approve"
6. respondToApproval() → sendMessage() → agent.send()
7. agent._ws === null → throw 'No active connection'
```

### Why

```
Page refresh
  │
  ▼
useAgentForHuman mount
  │ Restores session + chatItems from localStorage
  │ NO auto-reconnect (by design)
  │
  ▼
UI renders cached approval card
  │ Approve/Deny buttons are ENABLED
  │ But _ws is null — no WebSocket
  │
  ▼
User clicks "Approve"
  │ agent.send() → _ws === null → throw
```

### Root cause

Approval buttons render from cached chatItems without checking if WebSocket is connected. No guard between "UI shows interactive element" and "WebSocket is available to send response."

### Client-side fix options

**Option A: Auto-reconnect when interactive event is pending**

On mount, detect if cached UI has a pending approval/ask_user. If so, auto-call `reconnect()`.

```
useEffect([sessionId])
  ├─ restore session + chatItems
  └─ if chatItems has pending approval/ask_user:
       reconnect(sessionId)
```

**Option B: Guard send() with auto-connect**

Instead of throwing, `send()` queues the message and triggers `_ensureConnected()`:

```typescript
send(message) {
  if (!this._ws) {
    this._pendingMessages.push(message);
    this._ensureConnected();  // Will flush pending after connect
    return;
  }
  this._ws.send(JSON.stringify(message));
}
```

**Option C: Disable interactive UI until connected**

In approval/ask_user components, check `connectionState !== 'connected'` and disable buttons. Show "Reconnecting..." state.

### Server-side reconnect (current behavior)

Server-side reconnection works through three pieces (see [session-reconnect.md](session-reconnect.md) for details):

1. **`_agent_thread_body` has try/except/finally** — captures exceptions, always calls `io.mark_agent_done()` so the forwarder unwinds cleanly.
2. **IO survives the WS** — `WebSocketIO` lives in `ActiveSessionRegistry`, not on the WS; `run_ws_session`'s finally block only cancels forward/ping tasks.
3. **Single forward task per session** — old task is fully cancelled and awaited before `resume_forwarding` spawns a new one on the same io. `io.rewind_to(last_msg_id)` resets the cursor so missed events replay.

---

## Complete Reconnection Flow (Client + Server)

```
Time   Client (TypeScript)                Server (Python)
────   ────────────────────               ───────────────────
T+0    input("do something")
       _ensureConnected()
       CONNECT { session_id } ──────────► auth, register
       ◄──────────────────────────────── CONNECTED { status: "new" }
       INPUT { prompt } ────────────────► spawn agent thread
                                          agent starts...

T+5    ◄── approval_needed ──────────── io.send(approval_needed)
       chatItems += approval card         io.receive() BLOCKS on
       status = 'waiting'                 _msgs_from_client mailbox
       Zustand → localStorage

T+10   ✕ PAGE REFRESH
       _handleConnectionLoss()
       _ws = null                         run_ws_session finally →
       _inputReject(error)                  run_ws_session finally block:
                                              forward_task.cancel + await
                                              ping_task.cancel + await
                                          IO + agent thread STAY alive
                                          (status remains 'running')

T+15   Zustand hydrates
       UI renders cached approval card
       Auto-reconnect kicks in:
       reconnect(sessionId, last_msg_id)
       CONNECT { session_id, last_msg_id } ──► registry.get() → 'running'
       ◄────────────────────────────── CONNECTED { status: "running" }
                                          io.rewind_to(last_msg_id)
                                          new forward_task started
       ◄── replayed buffered events ──── (everything since last_msg_id)

T+16   User clicks "Approve"
       respondToApproval(true)
       agent.send(APPROVAL_RESPONSE) ──► send_to_agent → _msgs_from_client
                                          io.receive() unblocks
                                          agent continues...
```

---

## Key Files

| File | Role |
|---|---|
| `connectonion-ts/src/connect/remote-agent.ts` | WebSocket lifecycle, CONNECT/INPUT, reconnect() |
| `connectonion-ts/src/react/use-agent-for-human.ts` | React hook, Zustand persistence, session merge |
| `connectonion-ts/src/connect/types.ts` | ConnectionState, SessionState, ApprovalMode |
| `connectonion-ts/src/connect/auth.ts` | Ed25519 signing for CONNECT messages |
| `connectonion-ts/src/connect/chat-item-mapper.ts` | Server events → ChatItem[] for UI rendering |
| `oo-chat/components/chat/use-agent-sdk.ts` | oo-chat wrapper, respondToApproval() |
