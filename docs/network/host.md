# host()

> Make your agent accessible over the network. One function call.

**Looking to deploy?** See [Deploy Your Agent](deploy.md) for production deployment options.

---

## Quick Start (60 Seconds)

```python
from connectonion import Agent, host

# Define your agent
def create_agent():
    return Agent("translator", tools=[translate])

# Make it network-accessible
host(create_agent)
```

**Output:**
```
╭─────────────────────────────────────────────────────────╮
│  Agent 'translator' is now hosted                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Address:  0x3d4017c3e843895a92b70aa74d1b7ebc9c98...   │
│                                                         │
│  HTTP Endpoints:                                        │
│    POST http://localhost:8000/input                     │
│    GET  http://localhost:8000/sessions/{session_id}     │
│    GET  http://localhost:8000/sessions                  │
│    GET  http://localhost:8000/health                    │
│    GET  http://localhost:8000/info                      │
│    GET  http://localhost:8000/admin/logs     (API key)  │
│    GET  http://localhost:8000/admin/sessions (API key)  │
│    WS   ws://localhost:8000/ws                          │
│                                                         │
│  Interactive UI:                                        │
│    http://localhost:8000/docs                           │
│                                                         │
│  P2P Relay:                                             │
│    wss://oo.openonion.ai/ws/announce                    │
│                                                         │
╰─────────────────────────────────────────────────────────╯

Waiting for tasks...
```

**That's it.** Your agent is now accessible via HTTP, WebSocket, and P2P relay.

**By default, your agent is automatically discoverable.** Anyone with your address can connect:

```python
from connectonion import connect

# From anywhere in the world
translator = connect("0x3d4017c3e843895a92b70aa74d1b7ebc9c98...")
result = translator.input("Hello!")
```

The relay handles all the complexity:
- Agent registers its endpoints (localhost, local IPs, public IP)
- Client queries relay by address
- SDK tries direct connection first (fastest path)
- Falls back to relay routing if needed

See [Agent-Relay Protocol](protocol/agent-relay-protocol.md) for technical details.

---

## Function Signature

```python
def host(
    create_agent: Callable[[], Agent],  # Factory that returns fresh Agent

    # Trust
    trust: Union[str, Agent] = "careful",
    blacklist: list = None,
    whitelist: list = None,

    # Server
    port: int = 8000,
    workers: int = 1,

    # Storage
    result_ttl: int = 86400,  # 24 hours (how long server keeps results)

    # P2P Discovery
    relay_url: str = "wss://oo.openonion.ai/ws/announce",

    # Development
    reload: bool = False,
) -> None:
```

---

## How It Works

When you call `host(create_agent)`, your agent becomes accessible via **three connection types**, all running in the same event loop:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            host(create_agent)                                │
│                                                                              │
│  Single Event Loop (uvicorn)                                                │
│  ═══════════════════════════                                                │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │   HTTP Client   │  │  WebSocket      │  │  Relay Server               │ │
│  │   (curl, SDK)   │  │  Client (chat)  │  │  (wss://oo.openonion.ai)    │ │
│  └────────┬────────┘  └────────┬────────┘  └──────────────┬──────────────┘ │
│           │                    │                          │                 │
│           ▼                    ▼                          ▼                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │  POST /input    │  │  WS /ws         │  │  Persistent WebSocket       │ │
│  │  GET /sessions  │  │  INPUT/OUTPUT   │  │  ANNOUNCE (register)        │ │
│  │  GET /health    │  │  PING/PONG      │  │  INPUT → OUTPUT (relay)     │ │
│  │  GET /info      │  │  Real-time      │  │  Heartbeat (60s)            │ │
│  └────────┬────────┘  └────────┬────────┘  └──────────────┬──────────────┘ │
│           │                    │                          │                 │
│           └────────────────────┼──────────────────────────┘                 │
│                                │                                            │
│                                ▼                                            │
│                    ┌───────────────────────┐                               │
│                    │  create_agent()       │  ← Fresh instance per request │
│                    │  agent.input(prompt)  │                               │
│                    │  Return result        │                               │
│                    └───────────────────────┘                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Connection Type 1: HTTP (`POST /input`)

Direct HTTP request/response. Best for simple integrations.

```bash
curl -X POST http://localhost:8000/input \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'
```

**Flow:**
1. Client sends HTTP POST with `{prompt, session?}`
2. Server checks trust (blacklist/whitelist/policy)
3. Server calls `create_agent()` for fresh instance
4. Server calls `agent.input(prompt)`
5. Server returns `{result, session_id, session}`

### Connection Type 2: WebSocket (`/ws`)

Bidirectional real-time connection. Best for chat UIs with streaming.

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");
ws.send(JSON.stringify({type: "INPUT", prompt: "Hello"}));
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

**Flow:**
1. Client connects via WebSocket
2. Server sends PING every 30s (keep-alive)
3. Client sends INPUT message
4. Server streams events (thinking, tool_call, tool_result)
5. Server sends OUTPUT with final result

### Connection Type 3: Relay (`wss://oo.openonion.ai`)

Persistent connection to relay server for discoverability. Runs automatically.

```
Agent                              Relay Server
  │                                     │
  │── ANNOUNCE (register) ────────────>│  Every 60s (heartbeat)
  │   {address, endpoints, tools}       │
  │                                     │
  │<─────────────── INPUT ─────────────│  From remote client
  │   {input_id, prompt}                │
  │                                     │
  │── OUTPUT ─────────────────────────>│  Back to client
  │   {input_id, result}                │
```

**Flow:**
1. On startup, agent connects to relay via WebSocket
2. Agent sends ANNOUNCE with address, endpoints, tools
3. Relay stores agent info (now discoverable)
4. Agent re-sends ANNOUNCE every 60s (heartbeat)
5. When client calls `connect("0xaddress")`:
   - Client queries relay for agent endpoints
   - Client tries direct connection first
   - Falls back to relay routing if needed
6. Relay forwards INPUT to agent, agent sends OUTPUT back

### Heartbeat & Keep-Alive

| Connection | Mechanism | Interval | Purpose |
|------------|-----------|----------|---------|
| HTTP | None | N/A | Stateless request/response |
| WebSocket /ws | Server PING | 30s | Detect dead connections |
| Relay | Agent ANNOUNCE | 60s | Stay registered, update endpoints |

**Relay cleanup:** Agents not announcing for 120s are removed from registry.

### Worker Isolation

Each request calls your function to get a **fresh agent instance**:

```python
# Request A and B arrive simultaneously
# Each calls create_agent() and gets its own fresh agent
# No interference, no race conditions
```

### State Control

You control what's isolated vs shared via closure:

```python
# Isolated state (default, safest) - create tools inside:
def create_agent():
    browser = BrowserTool()  # Fresh per request
    return Agent("assistant", tools=[browser])

# Shared state (advanced) - create tools outside:
browser = BrowserTool()  # Expensive resource, shared across requests
def create_agent():
    return Agent("assistant", tools=[browser])
```

For horizontal scaling, use uvicorn `workers`:

```python
host(create_agent, workers=4)  # 4 OS processes, each with isolated agents
```

---

## HTTP API

### POST /input

Submit input. Creates a session, returns session_id.

```bash
curl -X POST http://localhost:8000/input \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Translate hello to Spanish"}'
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "done",
  "result": "Hola",
  "duration_ms": 1250,
  "session": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "messages": [...],
    "trace": [...],
    "turn": 1
  }
}
```

#### Multi-turn Conversations

To continue a conversation, pass the `session` from the previous response:

```bash
# First request
curl -X POST http://localhost:8000/input \
  -H "Content-Type: application/json" \
  -d '{"prompt": "My name is John"}'

# Response includes session
# {"result": "Nice to meet you, John!", "session": {...}}

# Second request - pass session back
curl -X POST http://localhost:8000/input \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is my name?",
    "session": {...}
  }'

# Agent remembers: "Your name is John"
```

**Request format:**
```json
{
  "prompt": "What is my name?",
  "session": {                    // Optional - pass previous session to continue
    "session_id": "abc-123",      // Server-generated, included in session
    "messages": [...],
    "trace": [...],
    "turn": 1
  }
}
```

**Note:** `session_id` is always generated by the server. For new conversations, omit `session`. For continuations, pass the entire `session` object from the previous response.

**Response format:**
```json
{
  "session_id": "abc-123",
  "status": "done",
  "result": "Your name is John",
  "duration_ms": 850,
  "session": {                    // Always returned - save for next request
    "session_id": "abc-123",
    "messages": [...],
    "trace": [...],
    "turn": 2
  }
}
```

### GET /sessions/{session_id}

Fetch session result anytime.

```bash
curl http://localhost:8000/sessions/550e8400-e29b-41d4-a716-446655440000
```

**Response (running):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running"
}
```

**Response (done):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "done",
  "result": "Hola",
  "duration_ms": 1250
}
```

### GET /sessions

List recent sessions.

```bash
curl http://localhost:8000/sessions
```

**Response:**
```json
{
  "sessions": [
    {"session_id": "abc-123", "status": "done", "created": 1702234567},
    {"session_id": "def-456", "status": "running", "created": 1702234570}
  ]
}
```

### GET /health

Health check for load balancers.

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "agent": "translator",
  "uptime": 3600
}
```

### GET /info

Agent capabilities and metadata.

```bash
curl http://localhost:8000/info
```

**Response:**
```json
{
  "name": "translator",
  "address": "0x3d4017c3...",
  "tools": ["translate", "detect_language"],
  "trust": "careful",
  "version": "0.4.1"
}
```

### GET /docs

Interactive UI to test your agent in the browser.

```
http://localhost:8000/docs
```

### GET /admin/logs (Requires API Key)

Fetch agent activity logs (plain text). Requires `OPENONION_API_KEY` authentication.

```bash
curl http://localhost:8000/admin/logs \
  -H "Authorization: Bearer YOUR_OPENONION_API_KEY"
```

**Response:**
```
2024-01-15 10:23:45 [translator] Processing: Translate hello
2024-01-15 10:23:46 [translator] Tool: translate_text executed (450ms)
2024-01-15 10:23:46 [translator] Result: Hola
```

### GET /admin/sessions (Requires API Key)

Fetch eval sessions from `.co/evals` as JSON array. Requires `OPENONION_API_KEY` authentication.

```bash
curl http://localhost:8000/admin/sessions \
  -H "Authorization: Bearer YOUR_OPENONION_API_KEY"
```

**Response:**
```json
{
  "sessions": [
    {
      "name": "translator",
      "created": "2024-01-15T10:23:45Z",
      "updated": "2024-01-15T10:23:46Z",
      "total_cost": 0.0012,
      "total_tokens": 215,
      "turns": [
        {"role": "user", "content": "Translate hello to Spanish"},
        {"role": "assistant", "content": "Hola"}
      ]
    }
  ]
}
```

**Note:** These endpoints require setting `OPENONION_API_KEY` as an environment variable when running your agent. The same key must be used to authenticate requests.

---

## WebSocket API

WebSocket provides real-time communication with automatic keep-alive and session recovery.

### Connect

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");
```

### Send INPUT

```javascript
ws.send(JSON.stringify({
  type: "INPUT",
  prompt: "Translate hello to Spanish",
  session: {
    session_id: "550e8400-e29b-41d4-a716-446655440000"  // Optional: for session continuity
  }
}));
```

### Receive Messages

```javascript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === "PING") {
    // Server keep-alive check (every 30s)
    ws.send(JSON.stringify({ type: "PONG" }));
  } else if (msg.type === "OUTPUT") {
    console.log("Result:", msg.result);
    console.log("Session ID:", msg.session_id);
  } else if (msg.type === "ERROR") {
    console.error("Error:", msg.message);
  } else {
    // tool_call, tool_result, thinking, ask_user, approval_needed, etc.
    console.log("Event:", msg);
  }
};
```

### Message Types

| Type | Direction | Purpose |
|------|-----------|---------|
| INPUT | Client → Agent | Send prompt with optional session |
| OUTPUT | Agent → Client | Final result + session data |
| PING | Agent → Client | Connection keep-alive (every 30s) |
| PONG | Client → Agent | Acknowledge keep-alive |
| tool_call | Agent → Client | Tool started |
| tool_result | Agent → Client | Tool completed |
| thinking | Agent → Client | Agent is processing |
| ask_user | Agent → Client | Agent needs input |
| approval_needed | Agent → Client | Tool approval required |
| ERROR | Agent → Client | Error message |

### Connection Keep-Alive

The server automatically sends **PING** messages every 30 seconds to keep the connection alive and detect dead connections:

```javascript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === "PING") {
    // Respond immediately to keep connection alive
    ws.send(JSON.stringify({ type: "PONG" }));
  }
};
```

**Why it matters:**
- Keeps connection alive through proxies and firewalls
- Detects dead connections within 60 seconds
- Prevents silent connection failures

### Session Recovery

If your WebSocket disconnects (network failure, timeout, page refresh), you can recover the result using the session_id:

**1. Generate and save session_id before connecting:**
```javascript
const sessionId = crypto.randomUUID();
localStorage.setItem('active_session', sessionId);
```

**2. Include session_id in INPUT:**
```javascript
ws.send(JSON.stringify({
  type: "INPUT",
  prompt: "Long running task...",
  session: { session_id: sessionId }
}));
```

**3. If connection drops, poll for result:**
```javascript
ws.onerror = async () => {
  // Connection failed, try to recover result
  const response = await fetch(`http://localhost:8000/sessions/${sessionId}`);
  const data = await response.json();

  if (data.status === "done") {
    console.log("Recovered result:", data.result);
  } else if (data.status === "running") {
    // Still processing, poll again after delay
    setTimeout(() => pollForResult(sessionId), 10000);
  }
};
```

**Session lifecycle:**
- Results stored for **24 hours** (configurable via `result_ttl`)
- Status can be `"running"` or `"done"`
- Supports recovery after network failures, timeouts, or page refreshes

---

## Design: Stateless Sessions

ConnectOnion uses **client-managed sessions** for multi-turn conversations. This section explains why.

### Why Full `session` Instead of Just `messages`?

You might expect an API like Anthropic or OpenAI that only passes `messages`:

```json
// What Anthropic/OpenAI do
{"messages": [...]}
```

But ConnectOnion passes the full session:

```json
// What ConnectOnion does
{"session": {"messages": [...], "trace": [...], "turn": 2}}
```

**The reason:** ConnectOnion is not just an LLM API wrapper. It's an agent framework with:

| Feature | Needs Session Data |
|---------|-------------------|
| Activity logging | `trace` - tool executions, timings |
| Turn tracking | `turn` - conversation turn count |
| XRay debugging | Full execution context |
| Session replay | Complete session history |

If we stripped down to just `messages`, we'd lose:
- Execution trace (which tools ran, how long they took)
- Turn count (for accurate logging)
- Debugging context (for XRay inspection)

**ConnectOnion's value is debugging and observability.** The full session preserves that.

### Why Client-Managed State?

The server doesn't store your session. You store it, you send it back. Like:

| Pattern | How It Works |
|---------|--------------|
| **JWT tokens** | Server gives you a token, you send it with each request |
| **Game save files** | Game gives you save data, you store it, you load it |
| **ConnectOnion sessions** | Server gives you session, you store it, you send it back |

**Benefits:**

1. **Infinitely scalable** - No server-side session storage
2. **Client transparency** - You can inspect the session, see exactly what's happening
3. **Coherent logs** - Server logs preserve turn count, trace
4. **Easy debugging** - Session contains full execution history
5. **No session cleanup** - No TTL, no expiry, no "session not found" errors

### Comparison

| API | Approach | State Storage |
|-----|----------|---------------|
| Anthropic Messages API | `messages` array | Client |
| OpenAI Chat API | `messages` array | Client |
| OpenAI Assistants API | `thread_id` | Server |
| **ConnectOnion** | `session` object | Client |

We chose client-managed state like Anthropic/OpenAI's Messages API, but with the full session object to preserve ConnectOnion's debugging features.

### When to Use Sessions

```python
# Single request - no session needed
{"prompt": "Translate hello to Spanish"}

# Multi-turn conversation - pass session
{"prompt": "What did I ask you?", "session": {...}}

# Start fresh - omit session
{"prompt": "New conversation"}
```

**Simple rule:** Save the `session` from each response. Pass it back if you want to continue.

---

## Project Structure

When you run `host(agent)`, these files are used:

```
your-project/
├── agent.py                  # Your agent code
├── .co/                      # ConnectOnion data folder
│   ├── session_results.jsonl # Session result storage (created by host)
│   ├── logs/                 # Activity logs (existing)
│   └── sessions/             # Session YAML (full conversation history)
└── .env                      # API keys (optional)
```

**On the network:**

```
┌─────────────────────────────────────────────────────────────┐
│                        Your Agent                            │
│                      host(agent)                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   HTTP Server (localhost:8000)                               │
│   ├── POST /input          ← Submit prompts                  │
│   ├── GET  /sessions/{id}  ← Fetch results                   │
│   ├── GET  /sessions       ← List sessions                   │
│   ├── GET  /health         ← Health check                    │
│   ├── GET  /info           ← Agent info                      │
│   ├── GET  /docs           ← Interactive UI                  │
│   ├── GET  /admin/logs     ← Activity logs (API key auth)    │
│   ├── GET  /admin/sessions ← Session logs (API key auth)     │
│   └── WS   /ws             ← Real-time WebSocket             │
│                                                              │
│   P2P Relay Connection                                       │
│   └── wss://oo.openonion.ai/ws/announce                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Session Result Storage

Results are stored locally in `.co/session_results.jsonl` (JSON Lines format):

```jsonl
{"session_id":"550e8400","prompt":"Translate hello","status":"running","created":1702234567,"expires":1702320967}
{"session_id":"550e8400","prompt":"Translate hello","status":"done","result":"Hola","created":1702234567,"expires":1702320967}
```

**Why `.co/` folder?**
- Consistent with `.co/logs/` and `.co/evals/` (existing patterns)
- Project-specific (each project has its own results)
- Already in `.gitignore`
- Easy to find (in project directory)

**Why JSON Lines?**
- Human readable (`cat session_results.jsonl`)
- Append-only (safe for multiple workers)
- Single file (easy to manage)
- Queryable (`grep "550e8400" session_results.jsonl`)

**Benefits:**
- Connection drops? Fetch result later via `GET /sessions/{session_id}`
- Client restarts? Results still there
- Debug issues? Read the file directly
- Multiple workers? Append-only = no race conditions

### TTL Expiry

Each result has an `expires` timestamp. Default: 24 hours after creation.

```python
host(agent)                     # Default: 24h TTL
host(agent, result_ttl=3600)    # 1 hour
host(agent, result_ttl=604800)  # 7 days
```

Expired results are automatically cleaned up. Running sessions are never cleaned even if expired.

### View Results

```bash
# See all results
cat .co/session_results.jsonl

# Find specific session
grep "550e8400" .co/session_results.jsonl | tail -1

# See running sessions
grep '"status":"running"' .co/session_results.jsonl

# Pretty print
cat .co/session_results.jsonl | jq .
```

---

## Authentication (Signed Requests)

For secure communication, requests can be signed with Ed25519.

### Signed Request Format

```json
{
  "payload": {
    "prompt": "Translate hello",
    "to": "0xAgentPublicKey",
    "timestamp": 1702234567
  },
  "from": "0xClientPublicKey",
  "signature": "0x..."
}
```

### How Signing Works

```python
import json
from nacl.signing import SigningKey

# Sign the payload directly
payload = {"prompt": "...", "to": "...", "timestamp": ...}
canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
signature = signing_key.sign(canonical.encode()).signature.hex()
```

### Authentication Modes

| Trust Level | Required Auth |
|-------------|---------------|
| `open` | None (anonymous OK) |
| `careful` | Signature recommended |
| `strict` | Signature required |

---

## The `trust` Parameter

Trust controls **who can access your agent**. All forms of trust use a trust agent behind the scenes.

See [Trust in ConnectOnion](/docs/concepts/trust.md) for the complete trust system documentation.

### 1. Trust Level (string)

Pre-configured trust agents for common scenarios:

```python
host(agent, trust="open")      # Accept all (development)
host(agent, trust="careful")   # Recommend signature, accept unsigned (default)
host(agent, trust="strict")    # Require valid signature (production)
```

| Level | Behavior |
|-------|----------|
| `open` | Accept all requests, no verification |
| `careful` | Recommend signature, accept unsigned requests |
| `strict` | Require identity and valid signature |

### 2. Trust Policy (natural language)

Express requirements in plain English - an LLM evaluates each request:

```python
host(agent, trust="""
I trust requests that:
- Come from known contacts with good history
- Have valid signatures
- Are on my whitelist OR from local network

I reject requests that:
- Come from blacklisted addresses
- Have no identity in production
""")

# Or from a file
host(agent, trust="./trust_policy.md")
```

### 3. Trust Agent (custom)

Full control with your own verification agent:

```python
guardian = Agent(
    "my_guardian",
    tools=[check_whitelist, verify_identity, check_reputation],
    system_prompt="""
        You verify requests before allowing interaction.
        Return ACCEPT or REJECT with reason.
    """
)

host(agent, trust=guardian)
```

### Environment-Based Defaults

```python
# No trust parameter needed - auto-detected!
host(agent)

# CONNECTONION_ENV=development → trust="open"
# CONNECTONION_ENV=test        → trust="careful"
# CONNECTONION_ENV=staging     → trust="careful"
# CONNECTONION_ENV=production  → trust="strict"
```

---

## Trust Flow

```
Request arrives
     │
     ▼
┌─────────────────┐
│ Blacklist?      │─── Yes ──▶ REJECT (403 forbidden)
└─────────────────┘
     │ No
     ▼
┌─────────────────┐
│ Whitelist?      │─── Yes ──▶ ACCEPT (bypass trust agent)
└─────────────────┘
     │ No
     ▼
┌─────────────────┐
│ Signed request? │─── Yes ──▶ Verify signature
└─────────────────┘              │
     │ No                        ├─ Invalid ──▶ REJECT (401)
     │                           │
     ▼                           ▼
┌─────────────────────────────────────┐
│ Trust Agent evaluates request       │
│                                     │
│  - Level?  → Pre-configured agent   │
│  - Policy? → LLM interprets policy  │
│  - Agent?  → Custom agent decides   │
│                                     │
│  Input: prompt, identity, sig_valid │
│  Output: ACCEPT or REJECT           │
└─────────────────────────────────────┘
     │
     ├─ ACCEPT ──▶ Execute agent.input(prompt)
     └─ REJECT ──▶ Return 403 forbidden
```

---

## Progress Updates (Custom)

The framework provides event hooks. You decide what progress to send.

```python
from connectonion import Agent, host, after_each_tool

def send_progress(agent):
    # Your custom progress logic
    iteration = agent.current_session["iteration"]
    print(f"Progress: iteration {iteration}")
    # Or send via your own WebSocket, webhook, etc.

agent = Agent("worker", on_events=[after_each_tool(send_progress)])
host(agent)
```

Available events:
- `after_user_input` - After receiving input
- `before_llm` - Before each LLM call
- `after_llm` - After each LLM call
- `before_each_tool` - Before each tool execution
- `after_each_tool` - After each tool execution

---

## Progressive Disclosure

### Level 0: Just Works

```python
host(create_agent)
```

### Level 1: Trust Control

```python
host(create_agent, trust="strict")
```

### Level 2: Access Control

```python
host(create_agent, blacklist=["0xbad..."], whitelist=["0xgood..."])
```

### Level 3: Production Scaling

```python
host(create_agent, workers=4, port=8000)  # 4 uvicorn workers
```

Each worker is an OS process with isolated memory. Within each worker, each request calls `create_agent()` for a fresh instance.

### Level 4: Custom Trust Logic

```python
host(create_agent, trust=my_guardian_agent)
```

---

## Accessing Your Agent

### HTTP (Simple)

```python
import requests

# Single request
response = requests.post("http://localhost:8000/input", json={
    "prompt": "Translate hello to Spanish"
})
print(response.json()["result"])  # "Hola"
```

### HTTP (Multi-turn)

```python
import requests

# First request
r1 = requests.post("http://localhost:8000/input", json={
    "prompt": "My name is John"
})
session = r1.json()["session"]  # Save session

# Second request - pass session back
r2 = requests.post("http://localhost:8000/input", json={
    "prompt": "What is my name?",
    "session": session  # Continue conversation
})
print(r2.json()["result"])  # "Your name is John"
session = r2.json()["session"]  # Update session for next request
```

### WebSocket (Real-time)

```python
import websockets
import json

async with websockets.connect("ws://localhost:8000/ws") as ws:
    await ws.send(json.dumps({"type": "INPUT", "prompt": "Translate hello"}))

    while True:
        msg = json.loads(await ws.recv())
        if msg["type"] == "OUTPUT":
            print(msg["result"])
            break
        elif msg["type"] == "ERROR":
            raise RuntimeError(msg.get("message", "Unknown error"))
        else:
            print("Event:", msg)
```

### P2P Relay (From Anywhere)

```python
from connectonion import connect

translator = connect("0x3d4017c3...660c")
result = translator.input("Translate hello to Spanish")
```

---

## Development vs Production

### Development

```python
host(create_agent, reload=True, trust="open")
```

- Auto-reloads on code changes
- No authentication required

### Production

```python
host(create_agent, workers=4, trust="strict")
```

- Multiple workers for parallel requests (OS-level isolation)
- Each request calls `create_agent()` for fresh instance (request-level isolation)
- Strict authentication and limits

---

## Deployment

### Direct

```bash
python myagent.py
```

### Standard Tooling

```python
# myagent.py
from connectonion import Agent
from connectonion.network import host, create_app

def create_agent():
    return Agent("translator", tools=[translate])

# Export ASGI app for uvicorn/gunicorn
app = create_app(create_agent)

if __name__ == "__main__":
    host(create_agent)
```

```bash
# Uvicorn
uvicorn myagent:app --workers 4

# Gunicorn
gunicorn myagent:app -w 4 -k uvicorn.workers.UvicornWorker
```

### Docker

```dockerfile
FROM python:3.11-slim
RUN pip install connectonion
COPY myagent.py .
CMD ["python", "myagent.py"]
```

```yaml
# docker-compose.yml
services:
  agent:
    build: .
    ports:
      - "8000:8000"
    environment:
      - CONNECTONION_ENV=production
```

### Reverse Proxy (Caddy)

```
# Caddyfile
agent.example.com {
    reverse_proxy localhost:8000
}
```

### systemd Service

```ini
# /etc/systemd/system/myagent.service
[Unit]
Description=My ConnectOnion Agent
After=network.target

[Service]
User=app
WorkingDirectory=/app
ExecStart=/usr/bin/python myagent.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable myagent
sudo systemctl start myagent
```

---

## API Reference

### host()

```python
def host(
    create_agent: Callable[[], Agent],
    trust: Union[str, Agent] = "careful",
    blacklist: list = None,
    whitelist: list = None,
    port: int = 8000,
    workers: int = 1,
    result_ttl: int = 86400,
    relay_url: str = "wss://oo.openonion.ai/ws/announce",
    reload: bool = False,
) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `create_agent` | `Callable[[], Agent]` | required | Function that returns a fresh Agent instance |
| `trust` | `str` or `Agent` | `"careful"` | Trust level, policy, or agent |
| `blacklist` | `list` | `None` | Addresses to always reject |
| `whitelist` | `list` | `None` | Addresses to always accept |
| `port` | `int` | `8000` | HTTP port |
| `workers` | `int` | `1` | Number of uvicorn worker processes |
| `result_ttl` | `int` | `86400` | How long server keeps results (24h) |
| `relay_url` | `str` | production | P2P relay server |
| `reload` | `bool` | `False` | Auto-reload on changes |

### create_app()

```python
from connectonion.network import create_app

def create_agent():
    return Agent("assistant", tools=[search])

app = create_app(
    create_agent: Callable[[], Agent],
    trust: Union[str, Agent] = "careful",
    blacklist: list = None,
    whitelist: list = None,
    result_ttl: int = 86400,
) -> ASGIApp
```

Returns ASGI app for use with uvicorn/gunicorn directly.

---

## Examples

### Minimal

```python
from connectonion import Agent, host

def create_agent():
    return Agent("helper", tools=[search])

host(create_agent)
```

### With Trust

```python
host(create_agent, trust="strict")
```

### With Access Control

```python
host(create_agent, blacklist=["0xbad..."], whitelist=["0xpartner..."])
```

### Production

```python
host(create_agent, workers=4, trust="strict", reload=False)
```

### Custom Trust Policy

```python
host(create_agent, trust="Only accept from known contacts with >10 successful tasks")
```

### Development

```python
host(create_agent, reload=True, trust="open")
```

---

## Comparison with Other Frameworks

| Framework | To Deploy |
|-----------|-----------|
| FastAPI | Learn uvicorn, ASGI, workers |
| Django | `runserver` vs gunicorn |
| LangServe | FastAPI + uvicorn |
| PydanticAI | Build everything yourself |
| **ConnectOnion** | `host(agent)` |

**We hide the complexity. You just host.**
