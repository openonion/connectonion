# IO

> Communicate with clients from hosted agents. Same events, works locally and hosted.

---

## Quick Start (60 Seconds)

```python
from connectonion import Agent, host, after_llm, before_each_tool

@after_llm
def on_thinking(agent):
    if agent.io:
        agent.io.log("thinking")

@before_each_tool
def on_tool(agent):
    if agent.io:
        tool = agent.current_session['pending_tool']
        agent.io.log("tool_call", name=tool['name'], arguments=tool['arguments'])

agent = Agent("helper", tools=[search], on_events=[on_thinking, on_tool])
host(agent)
```

**That's it.** Your agent now communicates with connected clients.

---

## The Core Concept

When you `host()` an agent, each request gets an `io`:

```
Local execution:    agent.io = None
Hosted execution:   agent.io = IO to client
```

Same events. Same code. Just check `if agent.io:`.

---

## Two-Layer API

```
┌─────────────────────────────────────────────────────────────┐
│  HIGH-LEVEL API (2 methods)                                 │
│  ──────────────────────────                                 │
│  io.log(type, **data)          → one-way notify             │
│  io.request_approval(tool, args) → bool (two-way)           │
├─────────────────────────────────────────────────────────────┤
│  LOW-LEVEL API (2 methods)                                  │
│  ─────────────────────────                                  │
│  io.send(event)                → send any event             │
│  io.receive()                  → get response               │
└─────────────────────────────────────────────────────────────┘
```

**High-level**: `log()` for notifications, `request_approval()` for permissions
**Low-level**: `send()` / `receive()` for custom needs

---

## The IO Interface

```python
class IO:
    """IO to client for real-time communication."""

    # ═══════════════════════════════════════════════════════
    # LOW-LEVEL API (Primitives)
    # ═══════════════════════════════════════════════════════

    def send(self, event: dict) -> None:
        """Send any event to client."""

    def receive(self) -> dict:
        """Receive response from client."""

    # ═══════════════════════════════════════════════════════
    # HIGH-LEVEL API (Patterns)
    # ═══════════════════════════════════════════════════════

    def log(self, event_type: str, **data) -> None:
        """One-way notification to client.

        Common event types: thinking, tool_call, tool_result, complete, error
        """
        self.send({"type": event_type, **data})

    def request_approval(self, tool: str, arguments: dict) -> bool:
        """Two-way: request permission, wait for response."""
        self.send({"type": "approval_needed", "tool": tool, "arguments": arguments})
        response = self.receive()
        return response.get("approved", False)
```

---

## Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  LOCAL EXECUTION                                            │
│  ───────────────                                            │
│  agent = Agent("helper", on_events=[...])                   │
│  agent.io = None  ← Always None locally                     │
│  agent.input("hello")                                       │
│  → Events fire                                              │
│  → Handlers check: if agent.io: (skip)                      │
│                                                             │
│  HOSTED EXECUTION                                           │
│  ────────────────                                           │
│  host(agent)                                                │
│     │                                                       │
│     ├─→ Client connects (WebSocket)                         │
│     │                                                       │
│     ├─→ agent = copy.deepcopy(agent_template)               │
│     │                                                       │
│     ├─→ agent.io = IO(ws)  ← Injected                       │
│     │                                                       │
│     ├─→ agent.input(prompt)                                 │
│     │      → Events fire                                    │
│     │      → if agent.io: ✓                                 │
│     │      → agent.io.log("thinking")                       │
│     │                                                       │
│     └─→ Request completes, io closed                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## High-Level API Examples

### Notify Events

```python
from connectonion import Agent, host, after_llm, after_each_tool, on_complete

@after_llm
def on_thinking(agent):
    if agent.io:
        agent.io.log("thinking")

@after_each_tool
def on_result(agent):
    if agent.io:
        trace = agent.current_session['trace'][-1]
        agent.io.log("tool_result", name=trace['tool_name'], result=trace['result'])

@on_complete
def on_done(agent):
    if agent.io:
        agent.io.log("complete", result=agent.current_session['result'])

agent = Agent("helper", tools=[search], on_events=[on_thinking, on_result, on_done])
host(agent)
```

### Tool Approval

```python
from connectonion import Agent, host, before_each_tool

class ToolRejected(Exception):
    pass

DANGEROUS_TOOLS = ["delete_file", "send_email", "run_shell"]

@before_each_tool
def check_approval(agent):
    if not agent.io:
        return

    tool = agent.current_session['pending_tool']

    # Notify tool is starting
    agent.io.log("tool_call", name=tool['name'], arguments=tool['arguments'])

    # Request approval for dangerous tools
    if tool['name'] in DANGEROUS_TOOLS:
        if not agent.io.request_approval(tool['name'], tool['arguments']):
            raise ToolRejected(f"User rejected {tool['name']}")

agent = Agent("helper", tools=[delete_file], on_events=[check_approval])
host(agent)
```

---

## Low-Level API Examples

For custom events and interactions:

```python
@after_llm
def custom_progress(agent):
    if agent.io:
        # Custom event type
        agent.io.send({
            "type": "progress",
            "percent": 50,
            "stage": "analyzing"
        })

@before_each_tool
def custom_interaction(agent):
    if not agent.io:
        return

    tool = agent.current_session['pending_tool']

    # Ask user to choose
    agent.io.send({
        "type": "choice",
        "question": "Which method?",
        "options": ["fast", "thorough"]
    })
    response = agent.io.receive()
    method = response.get("choice", "fast")

    # Modify tool arguments based on choice
    tool['arguments']['method'] = method
```

---

## Event Protocol

### Server → Client

```typescript
// Common events (via log())
{ type: "thinking" }
{ type: "tool_call", name: string, arguments: object }
{ type: "tool_result", name: string, result: string }
{ type: "complete", result: string }
{ type: "error", message: string }

// Approval request (via request_approval())
{ type: "approval_needed", tool: string, arguments: object }

// Custom events (via send())
{ type: "your_custom_type", ...data }
```

### Client → Server

```typescript
// Approval response
{ approved: boolean }

// Custom response
{ ...your_data }
```

---

## Client-Side (JavaScript)

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onmessage = async (event) => {
    const msg = JSON.parse(event.data);

    switch (msg.type) {
        case "thinking":
            showSpinner();
            break;

        case "tool_call":
            appendMessage(`Calling ${msg.name}...`);
            break;

        case "tool_result":
            appendMessage(`${msg.name}: ${msg.result}`);
            break;

        case "complete":
            hideSpinner();
            appendMessage(msg.result);
            break;

        case "error":
            showError(msg.message);
            break;

        case "approval_needed":
            const approved = await showApprovalDialog(msg.tool, msg.arguments);
            ws.send(JSON.stringify({ approved }));
            break;
    }
};

// Send prompt
ws.send(JSON.stringify({ type: "INPUT", prompt: "Search for Python docs" }));
```

---

## React Hook

```typescript
import { useState, useEffect, useCallback } from 'react';

function useAgent(wsUrl: string) {
    const [events, setEvents] = useState([]);
    const [pendingApproval, setPendingApproval] = useState(null);
    const [ws, setWs] = useState(null);

    useEffect(() => {
        const socket = new WebSocket(wsUrl);

        socket.onmessage = (e) => {
            const event = JSON.parse(e.data);
            setEvents(prev => [...prev, event]);

            if (event.type === 'approval_needed') {
                setPendingApproval(event);
            }
        };

        setWs(socket);
        return () => socket.close();
    }, [wsUrl]);

    const send = useCallback((prompt) => {
        ws?.send(JSON.stringify({ type: 'INPUT', prompt }));
    }, [ws]);

    const approve = useCallback((approved) => {
        if (pendingApproval) {
            ws?.send(JSON.stringify({ approved }));
            setPendingApproval(null);
        }
    }, [ws, pendingApproval]);

    return { events, pendingApproval, send, approve };
}
```

### Usage

```tsx
function AgentChat() {
    const { events, pendingApproval, send, approve } = useAgent("ws://localhost:8000/ws");

    return (
        <div>
            {events.map((e, i) => (
                <EventMessage key={i} event={e} />
            ))}

            {pendingApproval && (
                <ApprovalDialog
                    tool={pendingApproval.tool}
                    onApprove={() => approve(true)}
                    onReject={() => approve(false)}
                />
            )}

            <ChatInput onSend={send} />
        </div>
    );
}
```

---

## Available Events

| Event | When It Fires | Typical Usage |
|-------|---------------|---------------|
| `after_llm` | After each LLM response | `log("thinking")` |
| `before_each_tool` | Before each tool executes | `log("tool_call", ...)`, `request_approval(...)` |
| `after_each_tool` | After each tool completes | `log("tool_result", ...)` |
| `on_complete` | After agent finishes | `log("complete", ...)` |
| `on_error` | When tool fails | `log("error", ...)` |

---

## Complete Example

```python
from connectonion import (
    Agent, host,
    after_llm, before_each_tool, after_each_tool, on_complete, on_error
)

class ToolRejected(Exception):
    pass

DANGEROUS_TOOLS = ["delete_file", "send_email"]

@after_llm
def on_thinking(agent):
    if agent.io:
        agent.io.log("thinking")

@before_each_tool
def on_tool_start(agent):
    if not agent.io:
        return

    tool = agent.current_session['pending_tool']
    agent.io.log("tool_call", name=tool['name'], arguments=tool['arguments'])

    if tool['name'] in DANGEROUS_TOOLS:
        if not agent.io.request_approval(tool['name'], tool['arguments']):
            raise ToolRejected(tool['name'])

@after_each_tool
def on_tool_end(agent):
    if agent.io:
        trace = agent.current_session['trace'][-1]
        agent.io.log(
            "tool_result",
            name=trace['tool_name'],
            result=trace['result'],
            status=trace['status']
        )

@on_complete
def on_done(agent):
    if agent.io:
        agent.io.log("complete", result=agent.current_session['result'])

@on_error
def on_fail(agent):
    if agent.io:
        trace = agent.current_session['trace'][-1]
        agent.io.log("error", message=trace.get('error', 'Unknown error'))

agent = Agent(
    "helper",
    tools=[search, delete_file],
    on_events=[on_thinking, on_tool_start, on_tool_end, on_done, on_fail]
)

host(agent)
```

---

## Local vs Hosted

Same handlers work in both contexts:

```python
@after_llm
def my_handler(agent):
    # Runs in BOTH local and hosted mode
    print(f"Iteration {agent.current_session['iteration']}")

    # Only runs when hosted
    if agent.io:
        agent.io.log("thinking")

# Local - io is None, skips log
agent = Agent("helper", on_events=[my_handler])
agent.input("hello")

# Hosted - io exists, sends to client
host(agent)
```

---

## Custom Adapters

Implement your own IO for custom transports:

```python
from connectonion.network import IO

class SlackIO(IO):
    """Send events to Slack channel."""

    def __init__(self, slack_client, channel_id):
        self._slack = slack_client
        self._channel = channel_id

    def send(self, event: dict):
        self._slack.chat_postMessage(
            channel=self._channel,
            text=f"{event['type']}: {event.get('result', event.get('name', ''))}"
        )

    def receive(self) -> dict:
        # Implementation depends on your Slack setup
        pass

    # High-level methods automatically use send/receive

# Use custom adapter
agent.io = SlackIO(slack_client, "#agent-events")
agent.input("do something")
```

---

## Summary

| Layer | Methods | For |
|-------|---------|-----|
| **High-level** | `log(type, **data)`, `request_approval(tool, args)` | Daily use (2 methods) |
| **Low-level** | `send(event)`, `receive()` | Custom events (2 methods) |

**The pattern:**

```python
if agent.io:
    # One-way notifications
    agent.io.log("thinking")
    agent.io.log("tool_call", name="search", arguments={"q": "python"})

    # Two-way permission request
    if not agent.io.request_approval("delete", {"path": "/tmp/x"}):
        raise ToolRejected()

    # Custom events (low-level)
    agent.io.send({"type": "custom", "data": {...}})
    response = agent.io.receive()
```

**4 methods total. Simple things simple. Complicated things possible.**

---

## Learn More

- **[host.md](host.md)** - Host agents over HTTP/WebSocket
- **[connect.md](connect.md)** - Connect to remote agents

