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

## React: useAgent() Hook

The `connectonion/react` subpath exports a React hook with state management and localStorage persistence.

### Basic Usage

```tsx
import { useAgent } from 'connectonion/react'

function ChatPage() {
  const {
    ui,              // ChatItem[] — all streaming events
    status,          // 'idle' | 'working' | 'waiting'
    isProcessing,    // true while agent is working
    mode,            // approval mode
    input,           // send a message
    respond,         // answer ask_user
    respondToApproval,
    respondToPlanReview,
    setMode,
    reset,
  } = useAgent("0x3d4017c3e843...", {
    sessionId: "my-session-123"  // required — auto-persisted to localStorage
  })

  return (
    <div>
      {ui.map(item => {
        if (item.type === 'user') return <UserMsg key={item.id}>{item.content}</UserMsg>
        if (item.type === 'agent') return <AgentMsg key={item.id}>{item.content}</AgentMsg>
        if (item.type === 'thinking') return <Thinking key={item.id} />
        if (item.type === 'tool_call') return <ToolCall key={item.id} name={item.name} />
        if (item.type === 'ask_user') return (
          <AskUser
            key={item.id}
            question={item.text}
            options={item.options}
            onAnswer={(answer) => respond(answer)}
          />
        )
        if (item.type === 'approval_needed') return (
          <Approval
            key={item.id}
            tool={item.tool}
            onApprove={() => respondToApproval(true, 'once')}
            onReject={() => respondToApproval(false, 'once')}
          />
        )
        return null
      })}
      <Input onSend={(msg) => input(msg)} disabled={isProcessing} />
    </div>
  )
}
```

### Hook Return Interface

```ts
const agent = useAgent(address, { sessionId })

// State (reactive)
agent.ui: ChatItem[]           // All events for rendering
agent.status: AgentStatus      // 'idle' | 'working' | 'waiting'
agent.isProcessing: boolean    // true while agent working
agent.mode: ApprovalMode       // 'safe' | 'plan' | 'accept_edits' | 'ulw'
agent.error: Error | null
agent.sessionId: string

// Actions
agent.input(prompt, options?)       // Send message
agent.respond(answer)               // Answer ask_user
agent.respondToApproval(approved, scope, mode?, feedback?)
agent.respondToPlanReview(message)
agent.respondToUlwTurnsReached(action, options?)
agent.submitOnboard(options)        // Submit invite code / payment
agent.setMode(mode, options?)       // Change approval mode
agent.setPrompt(prompt)             // Set persistent system prompt
agent.reset()                       // Clear conversation
```

### Session Persistence

The hook automatically saves state to localStorage:
- Key: `co:agent:{address}:session:{sessionId}`
- Page refresh restores the full conversation
- No manual save/load needed

### Interactive Features

Agents can ask questions, request approval, and present plans:

```typescript
// Ask User — agent needs information
// Event: { type: 'ask_user', text: 'Which city?', options: ['Sydney', 'Tokyo'] }
respond("Sydney")
respond(["Sydney", "Tokyo"])  // multi-select

// Tool Approval — agent wants to run a dangerous tool
// Event: { type: 'approval_needed', tool: 'shell', arguments: { cmd: 'rm -rf /tmp' } }
respondToApproval(true, 'once')      // approve once
respondToApproval(true, 'session')   // approve for session
respondToApproval(false, 'once', 'reject_explain', 'Too dangerous')

// Plan Review — agent presenting a plan
// Event: { type: 'plan_review', plan_content: '1. Research\n2. Analyze' }
respondToPlanReview("Looks good, proceed")
respondToPlanReview("Skip step 2")
```

---

## oo-chat: Open-Source Reference Client

[oo-chat](https://github.com/openonion/oo-chat) is an open-source Next.js chat client built on the TypeScript SDK. It's a complete working example.

### Architecture

```
┌──────────────────────────────────────────────────┐
│  oo-chat (Next.js)                               │
│                                                   │
│  app/[address]/[sessionId]/page.tsx               │
│    └─ useAgentSDK()     ← elapsed time, pending   │
│         └─ useAgent()   ← connectonion/react      │
│              └─ connect()  ← WebSocket to agent   │
│                                                   │
│  <Chat />                                         │
│    ├─ <ChatMessages />  ← renders ui: ChatItem[]  │
│    ├─ <AskUser />       ← from pendingAskUser     │
│    ├─ <Approval />      ← from pendingApproval    │
│    └─ <ChatInput />     ← calls send()            │
└──────────────────────────────────────────────────┘
         │ WebSocket
         ▼
┌──────────────────────────────────────────────────┐
│  Hosted Agent (Python)                            │
│  host(agent)                                      │
└──────────────────────────────────────────────────┘
```

### File Structure

```
oo-chat/
├── app/[address]/[sessionId]/page.tsx   ← session page (uses useAgentSDK)
├── components/chat/
│   ├── chat.tsx                         ← main Chat component
│   ├── chat-input.tsx                   ← message input
│   ├── chat-messages.tsx                ← message list (renders ChatItem[])
│   ├── use-agent-sdk.ts                 ← wrapper hook around useAgent()
│   └── messages/
│       ├── tool-call.tsx                ← tool call card
│       └── tools/plan-card.tsx          ← plan review UI
└── package.json                         ← depends on connectonion
```

### How It Connects

```tsx
// app/[address]/[sessionId]/page.tsx
import { useAgentSDK } from '@/components/chat/use-agent-sdk'

export default function ChatSession({ params }) {
  const { address, sessionId } = params

  const {
    ui,
    isLoading,
    elapsedTime,
    pendingAskUser,
    pendingApproval,
    pendingPlanReview,
    mode,
    send,
    respondToAskUser,
    respondToApproval,
    respondToPlanReview,
    setMode,
    clear,
  } = useAgentSDK({ agentAddress: address, sessionId })

  return (
    <Chat
      ui={ui}
      isLoading={isLoading}
      elapsedTime={elapsedTime}
      onSend={(msg, images) => send(msg, images)}
      pendingAskUser={pendingAskUser}
      onAskUserResponse={respondToAskUser}
      pendingApproval={pendingApproval}
      onApprovalResponse={respondToApproval}
      pendingPlanReview={pendingPlanReview}
      onPlanReviewResponse={respondToPlanReview}
      mode={mode}
      onModeChange={setMode}
    />
  )
}
```

`useAgentSDK` is a thin wrapper around `useAgent()` that adds elapsed time tracking and extracts pending states (ask_user, approval, plan_review) from the `ui` array for easy conditional rendering.

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

### useAgent() (React)

```ts
const agent = useAgent(address, { sessionId })

// State (reactive)
agent.ui: ChatItem[]           // All events for rendering
agent.status: AgentStatus      // 'idle' | 'working' | 'waiting'
agent.isProcessing: boolean
agent.mode: ApprovalMode       // 'safe' | 'plan' | 'accept_edits' | 'ulw'

// Actions
agent.input(prompt)            // Send message
agent.respond(answer)          // Answer ask_user
agent.respondToApproval(approved, scope)
agent.respondToPlanReview(message)
agent.setMode(mode)            // Change approval mode
agent.reset()                  // Clear conversation
```

### ChatItem Types (TypeScript)

```typescript
type ChatItem =
  | { id, type: 'user', content, images? }
  | { id, type: 'agent', content, images? }
  | { id, type: 'thinking', status, model?, duration_ms? }
  | { id, type: 'tool_call', name, args?, status, result?, timing_ms? }
  | { id, type: 'ask_user', text, options, multi_select }
  | { id, type: 'approval_needed', tool, arguments, description? }
  | { id, type: 'plan_review', plan_content }
  | { id, type: 'tool_blocked', tool, reason, message, command? }
  | { id, type: 'onboard_required', methods, paymentAmount? }
  | { id, type: 'ulw_turns_reached', turns_used, max_turns }
```

### Data Types (Python)

```python
@dataclass
class Response:
    text: str       # Agent's response
    done: bool      # True = complete, False = needs input
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
# Python
agent = connect("0x...")
response = agent.input("task")
agent.ui      # All events for UI rendering
agent.status  # 'idle' | 'working' | 'waiting'
```

```typescript
// TypeScript
const agent = connect("0x...")
const response = await agent.input("task")
agent.ui      // ChatItem[] for rendering
```

```tsx
// React
const { ui, input, respond, respondToApproval } = useAgent("0x...", { sessionId })
```

**Event types:** `user`, `agent`, `thinking`, `tool_call`, `ask_user`, `approval_needed`, `plan_review`, `tool_blocked`

**One event type = one UI component.** Render `ui` array, handle interactive events with `respond()` / `respondToApproval()` / `respondToPlanReview()`.

**Reference implementation:** [oo-chat](https://github.com/openonion/oo-chat) — open-source Next.js chat client built on the TypeScript SDK.

---

## Learn More

- **[host.md](host.md)** - Host agents for remote access
- **[io.md](io.md)** - IO interface for real-time communication
