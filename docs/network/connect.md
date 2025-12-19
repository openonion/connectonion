# Connect to Remote Agents

> Use any agent, anywhere, as if it were local.

---

## Quick Start (60 Seconds)

```python
from connectonion import connect

# Connect to a remote agent
remote_agent = connect("0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")

# Use it like a local agent
result = remote_agent.input("Search for Python documentation")
print(result)
```

**Output:**
```
I found extensive Python documentation at docs.python.org covering tutorials,
library reference, and language specifications.
```

**That's it.** Use remote agents with one function call.

---

## What Just Happened?

When you called `connect(address)`:

1. **Created proxy agent** → Acts like a local Agent instance
2. **Connected to relay** → WebSocket at `wss://oo.openonion.ai/ws/announce`
3. **Sent INPUT message** → Routed to the remote agent
4. **Received OUTPUT** → Got the result back

All of this happens transparently. The remote agent looks and acts like a local one.

---

## Complete Example

### Terminal 1: Start a Serving Agent

```python
# serve_agent.py
from connectonion import Agent, host

def calculate(expression: str) -> str:
    """Perform calculations."""
    return str(eval(expression))

def get_weather(city: str) -> str:
    """Get weather information."""
    return f"Weather in {city}: Sunny, 72°F"

agent = Agent(
    "assistant",
    tools=[calculate, get_weather],
    system_prompt="You are a helpful assistant."
)

print("Starting agent...")
host(agent)  # HTTP server + P2P relay
```

**Output:**
```
Starting agent...
╭──────────── Agent 'assistant' ────────────╮
│ POST http://localhost:8000/input          │
│ Address: 0x7a8f9d4c...                    │
│ Relay:   wss://oo.openonion.ai/ws/announce│
╰───────────────────────────────────────────╯
```

### Terminal 2: Connect and Use

```python
# use_agent.py
from connectonion import connect

# Connect using the agent's address
assistant = connect("0x7a8f9d4c2b1e3f5a6c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b")

# Use it
result1 = assistant.input("What is 42 * 17?")
print(result1)
# Output: The result of 42 * 17 is 714.

result2 = assistant.input("What's the weather in Seattle?")
print(result2)
# Output: Weather in Seattle: Sunny, 72°F
```

---

## API Reference

### connect(agent_address, keys, relay_url)

Connect to a remote serving agent.

**Parameters:**
- `agent_address` (str, required): Ed25519 public key of the remote agent (hex format with 0x prefix)
- `keys` (dict, optional): Signing keys from `address.load()` - required for `trust="strict"` agents
- `relay_url` (str, optional): Relay server URL. Defaults to `"wss://oo.openonion.ai/ws/announce"`

**Returns:**
- `RemoteAgent`: Proxy object that behaves like a local Agent

**Example:**
```python
from connectonion import connect, address

# Connect with default relay
agent = connect("0x7a8f...")

# Connect with signing (for strict trust agents)
keys = address.load(Path(".co"))
agent = connect("0x7a8f...", keys=keys)

# Connect with custom relay
agent = connect("0x7a8f...", relay_url="ws://localhost:8000/ws/announce")
```

### RemoteAgent Methods

**`input(prompt, timeout=30.0)`** - Sync version (standard Python scripts)
```python
result = agent.input("Hello")
```

**`input_async(prompt, timeout=30.0)`** - Async version (Jupyter notebooks, async code)
```python
result = await agent.input_async("Hello")
```

**`reset_conversation()`** - Clear session and start fresh
```python
agent.reset_conversation()
```

> **Note:** `input()` cannot be used inside async contexts (Jupyter notebooks, async functions).
> Use `await agent.input_async()` instead. You'll get a clear error message if you try.

---

## Using Remote Agents

Once connected, remote agents work exactly like local ones:

### Single Task

```python
remote = connect("0x7a8f...")

result = remote.input("Translate 'hello' to Spanish")
print(result)
```

### Multi-Turn Conversation

```python
remote = connect("0x7a8f...")

# Turn 1
response1 = remote.input("Calculate 100 + 50")
# "The result is 150"

# Turn 2 - remembers context
response2 = remote.input("Multiply that by 2")
# "The result is 300"
```

The remote agent maintains conversation state across multiple `input()` calls.

---

## How It Works

### Message Flow

```
Your Code          Relay Server          Remote Agent
   |                     |                      |
   |-- INPUT ----------->|                      |
   |                     |-- INPUT ------------>|
   |                     |                      |
   |                     |             [Process task]
   |                     |                      |
   |                     |<-- OUTPUT -----------|
   |<-- OUTPUT ----------|                      |
   |                     |                      |
```

### Under the Hood

```python
# What connect() does internally
def connect(agent_address, relay_url=DEFAULT_RELAY):
    # 1. Create WebSocket connection to relay
    ws = websocket.create_connection(relay_url)

    # 2. Return proxy that forwards input() calls
    class RemoteAgent:
        def input(self, prompt):
            # Send INPUT message
            msg = {
                "type": "INPUT",
                "to": agent_address,
                "task": prompt
            }
            ws.send(json.dumps(msg))

            # Wait for OUTPUT response
            response = ws.recv()
            return json.loads(response)["result"]

    return RemoteAgent()
```

---

## Configuration

### Default Relay (Production)

```python
# Uses wss://oo.openonion.ai/ws/announce by default
agent = connect("0x7a8f...")
```

### Local Relay (Development)

```python
# Connect to local relay server
agent = connect("0x7a8f...", relay_url="ws://localhost:8000/ws/announce")
```

### Environment-Based

```python
import os

relay_url = os.getenv(
    "RELAY_URL",
    "wss://oo.openonion.ai/ws/announce"
)

agent = connect("0x7a8f...", relay_url=relay_url)
```

---

## Common Patterns

### 1. Connect to Multiple Agents

```python
from connectonion import connect

# Connect to specialized agents
searcher = connect("0xaaa...")
writer = connect("0xbbb...")
reviewer = connect("0xccc...")

# Use them together
research = searcher.input("Research AI trends")
draft = writer.input(f"Write article about: {research}")
final = reviewer.input(f"Review and improve: {draft}")

print(final)
```

### 2. Retry on Connection Failure

```python
import time
from connectonion import connect

def connect_with_retry(address, max_retries=3):
    for attempt in range(max_retries):
        try:
            return connect(address)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Connection failed, retrying... ({attempt + 1}/{max_retries})")
                time.sleep(2)
            else:
                raise

agent = connect_with_retry("0x7a8f...")
```

### 3. Agent Pool

```python
from connectonion import connect

# Pool of identical agents for load balancing
agent_addresses = [
    "0xaaa...",
    "0xbbb...",
    "0xccc..."
]

agents = [connect(addr) for addr in agent_addresses]

# Simple round-robin
def get_agent():
    agent = agents.pop(0)
    agents.append(agent)
    return agent

# Use different agent each time
result1 = get_agent().input("Task 1")
result2 = get_agent().input("Task 2")
result3 = get_agent().input("Task 3")
```

---

## Real-World Example: Distributed Workflow

```python
from connectonion import Agent, connect

# Local orchestrator agent
def run_workflow(task: str) -> str:
    """Run distributed workflow."""

    # Connect to remote specialized agents
    researcher = connect("0xaaa...")
    analyst = connect("0xbbb...")
    writer = connect("0xccc...")

    # Step 1: Research
    research = researcher.input(f"Research: {task}")

    # Step 2: Analyze
    analysis = analyst.input(f"Analyze this data: {research}")

    # Step 3: Write report
    report = writer.input(f"Write report based on: {analysis}")

    return report

# Local agent with access to remote agents via tool
orchestrator = Agent("orchestrator", tools=[run_workflow])

# User just talks to local agent, it uses remote ones automatically
result = orchestrator.input("Create a report on AI market trends")
print(result)
```

---

## Testing

### Test Remote Connection

```python
from connectonion import connect

def test_connection(address):
    """Test if remote agent is reachable."""
    try:
        agent = connect(address)
        response = agent.input("ping")
        print(f"✓ Connected to {address}")
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"✗ Failed to connect to {address}")
        print(f"Error: {e}")
        return False

# Test
test_connection("0x7a8f...")
```

### Integration Test

```python
import pytest
from connectonion import Agent, connect, host
import threading
import time

def test_network_connection():
    """Test serving and connecting to an agent."""

    # Create and serve agent in background
    def serve():
        agent = Agent("test", tools=[lambda x: f"Echo: {x}"])
        host(agent, relay_url="ws://localhost:8000/ws/announce")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    # Wait for agent to start
    time.sleep(2)

    # Connect and test
    remote = connect(
        "0x...",  # Agent's public key
        relay_url="ws://localhost:8000/ws/announce"
    )

    result = remote.input("test message")
    assert "Echo: test message" in result
```

---

## Error Handling

### Agent Not Found

```python
from connectonion import connect

try:
    agent = connect("0xinvalid...")
except Exception as e:
    print(f"Agent not found: {e}")
    # Handle: maybe agent is offline, try later
```

### Connection Timeout

```python
import socket

try:
    agent = connect("0x7a8f...", relay_url="ws://unreachable:8000/ws/announce")
except socket.timeout:
    print("Connection timed out")
    # Handle: use backup relay or local fallback
```

### Network Errors

```python
from connectonion import connect

def safe_connect(address):
    """Connect with error handling."""
    try:
        return connect(address)
    except ConnectionError:
        print("Network error, using local agent instead")
        from connectonion import Agent
        return Agent("fallback", tools=[...])

agent = safe_connect("0x7a8f...")
```

---

## Comparison: Local vs Remote

### Local Agent

```python
from connectonion import Agent

# Create local agent
agent = Agent("local", tools=[search, calculate])

# Use it
result = agent.input("Search and calculate")
```

**Pros:**
- No network latency
- Works offline
- Full control

**Cons:**
- Limited to one machine
- No sharing
- Scales vertically only

### Remote Agent

```python
from connectonion import connect

# Connect to remote agent
agent = connect("0x7a8f...")

# Use it
result = agent.input("Search and calculate")
```

**Pros:**
- Access from anywhere
- Share across team
- Scales horizontally
- Specialized agents

**Cons:**
- Network latency
- Requires connectivity
- Depends on remote availability

---

## Learn More

- **[host.md](host.md)** - Make your agents network-accessible with `host()`
- **[Agent](concepts/agent.md)** - Core Agent documentation
- **[protocol/agent-relay-protocol.md](protocol/agent-relay-protocol.md)** - Protocol specification

---

## Summary

`connect(address)` creates a proxy to a remote agent:

- **One function call** - `connect("0x7a8f...")`
- **Works like local agents** - Same `.input()` interface
- **Automatic relay connection** - Defaults to `wss://oo.openonion.ai/ws/announce`
- **Multi-turn conversations** - Remote agent maintains state
- **Zero configuration** - Just provide the address

**Simple case:**
```python
agent = connect("0x7a8f...")
result = agent.input("task")
```

**Custom relay:**
```python
agent = connect("0x7a8f...", relay_url="ws://localhost:8000/ws/announce")
result = agent.input("task")
```

That's it. Now go use remote agents as if they were local.
