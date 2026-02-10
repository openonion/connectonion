# Connect to Remote Agents

> Use any agent, anywhere, as if it were local. Real-time UI updates included.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            YOUR APPLICATION                                 │
│  ┌──────────────┐        ┌──────────────┐        ┌──────────────────────┐  │
│  │ React/Vue    │        │  Python      │        │  Swift/Kotlin        │  │
│  │ useAgent()   │        │  connect()   │        │  connect()           │  │
│  └──────┬───────┘        └──────┬───────┘        └──────────┬───────────┘  │
│         │                       │                           │              │
└─────────┼───────────────────────┼───────────────────────────┼──────────────┘
          │                       │                           │
          └───────────────────────┼───────────────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │  WebSocket /ws/input        │
                    │  wss://oo.openonion.ai      │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
          ┌────────────────────────────────────────────────────┐
          │                   RELAY SERVER                      │
          │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
          │  │ /ws/announce │  │ /ws/input    │  │ /ws/lookup│ │
          │  │ Agents       │  │ Clients      │  │ Discovery │ │
          │  └──────┬───────┘  └──────┬───────┘  └───────────┘ │
          │         │                 │                         │
          │         │  active_connections {address → WebSocket} │
          │         │  pending_outputs {input_id → Future}      │
          │         │                                           │
          └─────────┼─────────────────┼─────────────────────────┘
                    │                 │
                    │     ┌───────────┘
                    │     │
                    ▼     ▼
          ┌────────────────────────────────────────────────────┐
          │                    AGENT                            │
          │  host(agent) → /ws/announce → ANNOUNCE → ready     │
          │                                                     │
          │  INPUT received → agent.input(prompt) → OUTPUT      │
          └────────────────────────────────────────────────────┘
```

---

## Lifecycle

### 1. Agent Registers (Server Side)

```python
from connectonion import Agent, host

agent = Agent("my-agent", tools=[...])
host(agent)  # Connects to /ws/announce, sends ANNOUNCE
```

The agent:
1. Connects WebSocket to `wss://oo.openonion.ai/ws/announce`
2. Sends ANNOUNCE: `{type, address, summary, endpoints, signature}`
3. Relay stores in `active_connections[address] = websocket`
4. Agent waits for INPUT messages

### 2. Client Connects (Any Platform)

```python
from connectonion import connect

agent = connect("0x123abc...")
response = agent.input("Hello")
```

The client:
1. `connect(address)` creates RemoteAgent instance
2. `input(prompt)` opens WebSocket to `/ws/input`
3. Sends INPUT: `{type: "INPUT", input_id, to: "0x...", prompt, session?}`
4. Relay looks up `active_connections[to]`
5. Relay forwards INPUT to agent's WebSocket

### 3. Agent Processes

```
Relay → INPUT → Agent
        │
        ├─ agent.input(prompt)
        │
        ├─ Streaming events (direct /ws only):
        │  ← tool_call, tool_result, thinking, assistant, ask_user
        │
        └─ OUTPUT → Relay → Client
```

### 4. Client Receives Response

```python
response = agent.input("Hello")

response.text   # "Hello! How can I help?"
response.done   # True (complete) or False (needs more input)

agent.ui        # All events for rendering
agent.status    # 'idle' | 'working' | 'waiting'
```

---

## Connection Modes

### Via Relay (Default)

Uses agent address to route through relay server:

```python
# Python
agent = connect("0x3d4017c3...")
```

```typescript
// TypeScript
const agent = connect("0x3d4017c3...");
```

### Direct to Deployed Agent

For agents deployed via `co deploy`, connect directly to their URL:

```typescript
// TypeScript - bypass relay
const agent = connect("agent-name", {
  directUrl: "https://my-agent.agents.openonion.ai"
});
```

### Discovery & Smart Routing (Recommended for Custom Clients)

The relay stores agent-provided endpoints and can return them for direct connections.
The SDKs do **not** automatically probe endpoints yet; they use relay by default (Python) or `directUrl` when provided (TypeScript).

To implement smarter routing:
1. **Lookup endpoints** for the agent via relay:
   - **WebSocket** `/ws/lookup` with `GET_AGENT`
   - **HTTP** `/api/relay/agents/{address}`
2. **Try direct endpoints first** (if any):
   - Prefer `ws://`/`http://` endpoints that are reachable from your network.
   - If you are on the same LAN, a private IP (RFC1918) endpoint may be fastest.
3. **Fallback to relay** `/ws/input` if direct endpoints fail.

The relay does not determine whether an endpoint is “local” or “public”; it simply returns what the agent announced.
There is no WebRTC support in the relay server today.
TODO: Add WebRTC-style ICE candidates (host/srflx/relay) and connectivity checks
so clients can automatically pick the best direct path.

#### Lookup via WebSocket

```json
// Client → /ws/lookup
{ "type": "GET_AGENT", "address": "0x3d4017c3..." }
```

```json
// Server → client
{
  "type": "AGENT_INFO",
  "agent": {
    "address": "0x3d4017c3...",
    "summary": "translator agent",
    "endpoints": ["ws://192.168.1.10:8000/ws"],
    "last_announce": "2024-01-15T10:23:45Z",
    "online": true
  }
}
```

#### Lookup via HTTP

```bash
curl https://oo.openonion.ai/api/relay/agents/0x3d4017c3...
```

```json
{
  "online": true,
  "endpoints": ["ws://192.168.1.10:8000/ws"],
  "last_seen": "2024-01-15T10:23:45Z"
}
```

---

## Connection Reliability & Recovery

The ConnectOnion client (TypeScript/Python) automatically handles connection failures and recovers results seamlessly.

### Automatic Keep-Alive

**Server sends PING every 30 seconds:**
- Client automatically responds with PONG
- Keeps connection alive through proxies and firewalls
- Detects dead connections within 60 seconds

No configuration needed - handled automatically by the SDK.

### Extended Timeout

**Default timeout: 10 minutes** (600 seconds)

Long-running agent tasks have plenty of time to complete:

```typescript
// TypeScript - default 10 minutes
const response = await agent.input("Analyze this large dataset");

// Override if needed (5 minutes)
const response = await agent.input("Quick task", 300000);
```

### Automatic Session Recovery

If the WebSocket connection fails (network drop, timeout, page refresh), the SDK **automatically polls** the server to retrieve your result:

```
1. Connection fails or times out
   ↓
2. SDK polls GET /sessions/{session_id} every 10s
   ↓
3. Server returns result when ready
   ↓
4. SDK returns result to your code
   ↓
5. You get the result as if nothing happened! ✅
```

**What this means for you:**
- ✅ Page refresh during long tasks? No problem.
- ✅ Network hiccup? Result still delivered.
- ✅ Connection timeout? Automatically recovered.
- ✅ Agent takes 15 minutes? You still get the result.

**Configuration (TypeScript):**

```typescript
const agent = connect("0x123...", {
  enablePolling: true,        // Default: true
  pollIntervalMs: 10000,      // Poll every 10s (default)
  maxPollAttempts: 30         // Try for 5 minutes (default)
});
```

**Session persistence:**
- Results stored server-side for **24 hours**
- Session ID automatically generated and tracked
- localStorage used (browser) to survive page refreshes

### Connection Lifecycle

```
┌─────────────────────────────────────────────────────┐
│  Normal Operation (WebSocket)                       │
├─────────────────────────────────────────────────────┤
│  1. Connect via WebSocket                           │
│  2. Send INPUT with session_id                      │
│  3. Receive PING every 30s, respond with PONG       │
│  4. Receive streaming events                        │
│  5. Receive OUTPUT (result)                         │
│  6. Close connection                                │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Recovery Mode (HTTP Polling)                       │
├─────────────────────────────────────────────────────┤
│  1. WebSocket fails/timeout                         │
│  2. SDK polls: GET /sessions/{session_id}           │
│  3. Server responds: {"status": "running"}          │
│  4. Wait 10s, poll again                            │
│  5. Server responds: {"status": "done", "result"}   │
│  6. SDK returns result to your code                 │
└─────────────────────────────────────────────────────┘
```

### Error Scenarios Handled

| Scenario | What Happens |
|----------|-------------|
| **Network disconnect** | Automatic polling recovers result |
| **Page refresh** | Session ID in localStorage, poll for result |
| **10-minute timeout** | Polling activates, waits for completion |
| **Server restart** | Polling continues, result available when server back |
| **Connection drops mid-stream** | Polling recovers final result |

### Best Practices

**1. For long-running tasks:**
```typescript
// Just call input() - recovery is automatic
const response = await agent.input("Process 1GB of data");
// Works even if it takes 20 minutes
```

**2. For user feedback:**
```typescript
agent.on('reconnecting', () => {
  showMessage('Connection lost, recovering...');
});

agent.on('polling', () => {
  showMessage('Checking for results...');
});
```

**3. For critical operations:**
```typescript
try {
  const response = await agent.input("Critical task");
  console.log("Success:", response.text);
} catch (error) {
  // Only fails if:
  // - Server down for 24+ hours
  // - Session expired (24h TTL)
  console.error("Failed:", error);
}
```

---

## Message Protocol

### INPUT (Client → Relay → Agent)

```json
{
  "type": "INPUT",
  "input_id": "uuid-1234",
  "to": "0x3d4017c3...",
  "prompt": "Book a flight to Tokyo",
  "session": { "messages": [...] }
}
```

### OUTPUT (Agent → Relay → Client)

```json
{
  "type": "OUTPUT",
  "input_id": "uuid-1234",
  "result": "Booked! Confirmation #ABC123",
  "session": { "messages": [...updated...] }
}
```

### Streaming Events (Agent → Client)

| Event | Purpose |
|-------|---------|
| `tool_call` | Tool execution started `{id, name, args, status: "running"}` |
| `tool_result` | Tool completed `{id, result, status: "done"}` |
| `thinking` | Agent is processing |
| `ask_user` | Agent needs input `{text, options, multi_select}` → `done: false` |

Note: Relay /ws/input does not forward streaming events. Use direct host /ws for real-time events.

---

## Related Files

| File | Purpose |
|------|---------|
| `connectonion/network/connect.py` | Python client - RemoteAgent class |
| `connectonion/network/relay.py` | Agent-side relay connection |
| `connectonion-ts/src/connect.ts` | TypeScript client - same API |
| `connectonion-ts/src/react/index.ts` | useAgent React hook |
| `oo-api/relay/routes.py` | Relay server endpoints |

---

## Quick Start

```python
from connectonion import connect

agent = connect("0x...")

response = agent.input("Book a flight to Tokyo")
print(response.text)   # "Which date do you prefer?"
print(response.done)   # False - agent asked a question

response = agent.input("March 15")
print(response.text)   # "Booked! Confirmation #ABC123"
print(response.done)   # True
```

---

## Response

```python
response = agent.input("task")

response.text   # Agent's response or question
response.done   # True = complete, False = needs more input
```

---

## Session State

`current_session` is synced from the server when the server includes it (direct host /ws).
Relay /ws/input currently returns only OUTPUT without session data.

```python
agent.current_session   # Synced from server when available (read-only)
agent.ui                # Client-side UI event list (input + streamed events)
agent.status            # 'idle' | 'working' | 'waiting'
```

---

## UI Rendering

`agent.ui` contains all events for rendering. **One type = one component.**
Streaming events are delivered only for direct host /ws connections; relay returns only OUTPUT.

```python
agent.ui = [
    {"id": "1", "type": "user", "content": "Book a flight"},
    {"id": "2", "type": "thinking"},
    {"id": "3", "type": "tool_call", "name": "search_flights", "status": "running"},
    # ↑ When tool_result arrives, client updates this item to status: "done"
    {"id": "4", "type": "agent", "content": "Found 3 flights..."},
    {"id": "5", "type": "ask_user", "text": "Which date?", "options": ["Mar 15", "Mar 16"]},
]
```

### Event Types

| Type | Component | Fields |
|------|-----------|--------|
| `user` | User chat bubble | `content` |
| `agent` | Agent chat bubble | `content` |
| `thinking` | Loading spinner | - |
| `tool_call` | Tool card | `name`, `status`, `result?` |
| `ask_user` | Question form | `text`, `options`, `multi_select` |

### Server → Client Mapping

Server sends two events, client merges into one UI item:

```
Server: tool_call   {id: "3", name: "search"}     → UI: {id: "3", status: "running"}
Server: tool_result {id: "3", result: "..."}      → UI: {id: "3", status: "done", result: "..."}
```

---

## Cross-Platform SDKs

### Python

```python
from connectonion import connect

agent = connect("0x...")
response = agent.input("Book a flight")
print(response.text)   # "Which date?"
print(response.done)   # False
print(agent.ui)        # All events for rendering
```

### TypeScript

```typescript
import { connect } from 'connectonion';

const agent = connect('0x...');
const response = await agent.input('Book a flight');
console.log(response.text);   // "Which date?"
console.log(response.done);   // false
console.log(agent.ui);        // All events for rendering
```

### Swift

```swift
import ConnectOnion

let agent = connect("0x...")
let response = try await agent.input("Book a flight")
print(response.text)   // "Which date?"
print(response.done)   // false
print(agent.ui)        // All events for rendering
```

### Kotlin

```kotlin
import com.connectonion.connect

val agent = connect("0x...")
val response = agent.input("Book a flight")
println(response.text)   // "Which date?"
println(response.done)   // false
println(agent.ui)        // All events for rendering
```

---

## React / Vue Integration

For reactive UI updates, use framework-specific hooks:

### React

```tsx
import { useAgent } from 'connectonion/react';

function ChatUI() {
    const agent = useAgent('0x...');

    return (
        <div>
            {agent.ui.map(item => {
                switch (item.type) {
                    case 'user':      return <UserBubble key={item.id} {...item} />;
                    case 'agent':     return <AgentBubble key={item.id} {...item} />;
                    case 'thinking':  return <Thinking key={item.id} />;
                    case 'tool_call': return <ToolCard key={item.id} {...item} />;
                    case 'ask_user':  return <QuestionForm key={item.id} {...item} onAnswer={agent.send} />;
                }
            })}
            <Input onSend={agent.send} disabled={agent.status === 'working'} />
        </div>
    );
}
```

### Vue

```vue
<script setup>
import { useAgent } from 'connectonion/vue';

const agent = useAgent('0x...');
</script>

<template>
    <div v-for="item in agent.ui" :key="item.id">
        <UserBubble v-if="item.type === 'user'" v-bind="item" />
        <AgentBubble v-if="item.type === 'agent'" v-bind="item" />
        <Thinking v-if="item.type === 'thinking'" />
        <ToolCard v-if="item.type === 'tool_call'" v-bind="item" />
        <QuestionForm v-if="item.type === 'ask_user'" v-bind="item" @answer="agent.send" />
    </div>
    <Input @send="agent.send" :disabled="agent.status === 'working'" />
</template>
```

### Hook Interface

All hooks return the same interface:

```ts
const agent = useAgent('0x...');

agent.ui        // UIEvent[] - reactive, auto updates
agent.status    // 'idle' | 'working' | 'waiting' - reactive
agent.send()    // Send message
agent.reset()   // Clear conversation
```

---

## API Reference

### connect()

```python
agent = connect("0x...", relay_url="ws://localhost:8000/ws/announce")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `address` | `str` | required | Agent's address (0x...) |
| `relay_url` | `str` | production | Relay server URL |

### RemoteAgent

```python
class RemoteAgent:
    # Actions
    def input(self, prompt: str) -> Response
    def reset(self) -> None

    # State (read-only)
    current_session: dict    # Full session data
    ui: List[UIEvent]        # Shortcut to current_session['trace']
    status: str              # 'idle' | 'working' | 'waiting'
```

### useAgent() (React/Vue)

```ts
const agent = useAgent('0x...');

agent.ui        // Reactive - auto updates when data changes
agent.status    // Reactive - 'idle' | 'working' | 'waiting'
agent.send()    // Send message to agent
agent.reset()   // Clear conversation
```

### Data Types

```python
@dataclass
class Response:
    text: str       # Agent's response
    done: bool      # True = complete, False = needs input

# Server trace events (what server sends)
@dataclass
class ServerEvent:
    id: str
    type: str       # 'user' | 'agent' | 'thinking' | 'tool_call' | 'tool_result' | 'ask_user'

# UI events (what client renders) - tool_result merged into tool_call
@dataclass
class UIEvent:
    id: str
    type: str       # 'user' | 'agent' | 'thinking' | 'tool_call' | 'ask_user'

    # For user/agent
    content: Optional[str]

    # For tool_call (merged from tool_call + tool_result)
    name: Optional[str]
    status: Optional[str]    # 'running' | 'done' | 'error'
    result: Optional[str]

    # For ask_user
    text: Optional[str]
    options: Optional[List[str]]    # Required when type == 'ask_user'
    multi_select: Optional[bool]    # Required when type == 'ask_user'
```

---

## State Machine

```
                    input()                 response.done=false
        IDLE ────────────────▶ WORKING ─────────────────────▶ WAITING
          ▲                       │                              │
          │                       │ response.done=true           │ input()
          │                       ▼                              │
          └───────────────────────────────────────────────────────
```

---

## Common Patterns

### Conversation Loop

```python
agent = connect("0x...")

response = agent.input("book a flight")

while not response.done:
    answer = input(f"{response.text}: ")
    response = agent.input(answer)

print(f"Final: {response.text}")
```

### Multiple Agents

```python
researcher = connect("0xaaa...")
writer = connect("0xbbb...")

research = researcher.input("Research AI trends").text
article = writer.input(f"Write about: {research}").text
```

### Complete Example

**Terminal 1: Host an Agent**

```python
from connectonion import Agent, host

def search(query: str) -> str:
    return f"Found results for: {query}"

def book_flight(destination: str, date: str) -> str:
    return f"Booked flight to {destination} on {date}. Confirmation: ABC123"

agent = Agent("travel-assistant", tools=[search, book_flight])
host(agent)
```

**Terminal 2: Connect and Use**

```python
from connectonion import connect

agent = connect("0x7a8f...")
response = agent.input("Book me a flight to Paris")

while not response.done:
    print(response.text)
    answer = input("> ")
    response = agent.input(answer)

print(f"Done: {response.text}")
```

---

## Error Handling

```python
from connectonion import connect, ConnectionError, TimeoutError

agent = connect("0x...")
response = agent.input("task")
# Errors raise exceptions - no try/except needed unless you want custom handling
```

---

## Summary

```python
# Python / TypeScript / Swift / Kotlin
agent = connect("0x...")
response = agent.input("task")
agent.ui      # All events for UI rendering
agent.status  # 'idle' | 'working' | 'waiting'
```

```tsx
// React / Vue (reactive)
const agent = useAgent('0x...');
agent.ui      // Reactive - auto updates
agent.send()  // Send message
```

**Server events:** `user`, `agent`, `thinking`, `tool_call`, `tool_result`, `ask_user`

**UI events:** `user`, `agent`, `thinking`, `tool_call`, `ask_user` (tool_result merged into tool_call)

**One UI type = one component.** That's it.

---

## Learn More

- **[host.md](host.md)** - Host agents for remote access
- **[io.md](io.md)** - IO interface for real-time communication
