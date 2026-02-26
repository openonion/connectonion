# WebSocket Session Lifecycle

## Complete Message Flow (Client → Server → Client)

### Phase 1: Client Sends INPUT

**Client (TypeScript SDK):**
```typescript
// User calls: agent.input("What is Python?")

1. Client creates INPUT message:
{
  type: "INPUT",
  input_id: "uuid-123",
  prompt: "What is Python?",
  session: {                    // ← Sent from client
    session_id: "session-456",
    messages: [...],
    turn: 2
  },
  payload: {...},
  signature: "..."
}

2. Send via WebSocket
ws.send(JSON.stringify(message))
```

**Server (Python SDK):**
```python
# websocket.py receives INPUT

1. Extract session from message (line 136):
   session = data.get("session")

2. Pass to agent (line 146):
   result = route_handlers["ws_input"](storage, prompt, io, session)

3. Agent restores or creates session (agent.py line 226-243):
   if session:
       self.current_session = {
           'session_id': session['session_id'],
           'messages': session['messages'],
           'trace': session.get('trace', []),
           'turn': session.get('turn', 0)
       }
   else:
       self.current_session = {
           'messages': [{"role": "system", "content": "..."}],
           'trace': [],
           'turn': 0
       }
```

---

### Phase 2: Agent Processing (Multiple Events Sent)

**Server sends multiple events via `_record_trace()`:**

```python
# agent.py line 153-167

def _record_trace(self, entry: dict):
    # Add to local trace
    self.current_session['trace'].append(entry)

    # Send to client via WebSocket
    if self.io:
        self.io.send(entry)  # ← Goes to WebSocket
```

**Event sequence:**

```
1. LLM_CALL event:
{
  type: "llm_call",
  id: "uuid-1",
  model: "gemini-2.5-pro",
  iteration: 1,
  status: "running",
  ts: 1234567890
  // ❌ No session data (current)
  // ✅ Would have session data (after our change)
}

2. THINKING event:
{
  type: "thinking",
  text: "I need to search for Python information",
  id: "uuid-2",
  ts: 1234567891
  // ❌ No session data (current)
}

3. LLM_RESULT event:
{
  type: "llm_result",
  id: "uuid-1",
  model: "gemini-2.5-pro",
  duration_ms: 1500,
  tool_calls_count: 1,
  iteration: 1,
  ts: 1234567892
  // ❌ No session data (current)
}

4. TOOL_CALL event:
{
  type: "tool_call",
  tool: "search",
  arguments: {"query": "Python programming"},
  id: "uuid-3",
  ts: 1234567893
  // ❌ No session data (current)
}

5. TOOL_RESULT event:
{
  type: "tool_result",
  tool: "search",
  result: "Python is a high-level programming language...",
  status: "completed",
  duration_ms: 500,
  id: "uuid-4",
  ts: 1234567894
  // ❌ No session data (current)
}

6. ASK_USER event (if agent needs input):
{
  type: "ask_user",
  text: "Which version do you want to know about?",
  options: ["Python 2", "Python 3"],
  id: "uuid-5",
  ts: 1234567895
  // ❌ No session data (current)
  // ⚠️  CRITICAL: Connection drop here loses context!
}

7. APPROVAL_NEEDED event (if tool needs approval):
{
  type: "approval_needed",
  tool: "send_email",
  arguments: {"to": "user@example.com", "body": "..."},
  id: "uuid-6",
  ts: 1234567896
  // ❌ No session data (current)
  // ⚠️  CRITICAL: Connection drop here loses context!
}
```

**Meanwhile, PING messages sent every 30s (separate from trace):**

```python
# websocket.py line 256-262

async def send_ping():
    while not agent_done.is_set():
        await asyncio.sleep(30)
        await ws_send({
            "type": "websocket.send",
            "text": json.dumps({"type": "PING"})
        })
        # ❌ No session data
```

**Client receives PING and responds:**
```typescript
// connect.ts line 1006-1014

if (data?.type === 'PING') {
  ws.send(JSON.stringify({ type: 'PONG' }))
  // ❌ PONG doesn't send session either
}
```

---

### Phase 3: Interactive Wait (CRITICAL TIMING)

**Scenario: Agent sends ASK_USER event**

```
Time   Server (Python)              WebSocket              Client (TypeScript)
====   ==================           ===========            ===================

T+0    agent.io.ask_user()
       → generates ask_user event
       → _record_trace(event)
       → io.send(event)         →   ws.send(event)    →    ws.onmessage(event)
                                                            → status = 'waiting'
                                                            → shows question UI

       [Agent thread BLOCKED]                               [User thinking...]
       waiting for response...

                                                            User types answer
                                                            agent.respond("Python 3")
                                                       ←    ws.send({
                                                              type: "ASK_USER_RESPONSE",
                                                              answer: "Python 3"
                                                            })

       io.receive() unblocks    ←   ws.receive()      ←
       → continues processing

T+30s                           →   PING              →    [Connection check]
                                ←   PONG              ←    ws.send({type: "PONG"})

⚠️  PROBLEM: If connection drops between ask_user and user response:
    - Server: Agent still has current_session in memory
    - Client: Only has events up to ask_user, but NO SESSION DATA
    - Client can't restore session on reconnect!
```

---

### Phase 4: Final Response

**Server sends OUTPUT:**

```python
# websocket.py line 169-176

await send({
    "type": "websocket.send",
    "text": json.dumps({
        "type": "OUTPUT",
        "result": "Python is a programming language...",
        "session_id": "session-456",
        "duration_ms": 5000,
        "session": {              # ✅ Session IS sent here (current)
            "session_id": "session-456",
            "messages": [...],
            "trace": [...],
            "turn": 2
        }
    })
})
```

**Client receives OUTPUT:**

```typescript
// connect.ts line 1116-1130

if (data?.type === 'OUTPUT') {
  // Sync session from server
  if (data.session) {
    this._currentSession = data.session;
    this._saveSession(data.session);  // ← Save to localStorage
  }

  resolve({
    result: data.result,
    sessionId: data.session_id
  })
}
```

---

## Current State Summary

| Message Type | Goes Through | Current Session? | Problem? |
|--------------|--------------|------------------|----------|
| INPUT (client→server) | WebSocket direct | ✅ Yes | No |
| llm_call | `_record_trace()` | ❌ No | Minor |
| thinking | `_record_trace()` | ❌ No | Minor |
| tool_call | `_record_trace()` | ❌ No | Minor |
| tool_result | `_record_trace()` | ❌ No | Minor |
| **ask_user** | `_record_trace()` | ❌ No | **⚠️ CRITICAL** |
| **approval_needed** | `_record_trace()` | ❌ No | **⚠️ CRITICAL** |
| PING | Direct (websocket.py) | ❌ No | Minor |
| PONG (client→server) | Direct | ❌ No | No |
| OUTPUT | Direct (websocket.py) | ✅ Yes | No |
| ERROR | Direct (websocket.py) | ❌ No | Minor |

---

## Proposed Change

**Option 1: Add session to all `_record_trace()` events**
```python
def _record_trace(self, entry: dict):
    self.current_session['trace'].append(entry)

    if self.io:
        # Attach session to every event
        entry['session'] = {k: v for k, v in self.current_session.items() if k != 'trace'}
        self.io.send(entry)
```

**Benefits:**
- ✅ Solves ask_user / approval_needed timing issue
- ✅ Client always has latest session state
- ✅ Works for ALL trace events automatically

**Tradeoffs:**
- Session sent with every event (more bandwidth)
- Still doesn't cover PING messages

**Option 2: Also add session to PING**
```python
# websocket.py
async def send_ping():
    while not agent_done.is_set():
        await asyncio.sleep(30)
        # Get current session from agent somehow?
        await ws_send(json.dumps({
            "type": "PING",
            "session": get_agent_session()  # ← How to access?
        }))
```

**Problem:** Agent runs in separate thread, hard to access `current_session` safely

---

## Recommendation

**Implement Option 1 (attach session to all trace events)**

This solves the critical timing issue where connection drops during `ask_user` or `approval_needed` would lose context. PING messages are less critical since they happen every 30s and we'll have recent session data from the last trace event.
