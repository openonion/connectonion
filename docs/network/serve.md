# Agent Serving

> Make your agent accessible over the network. One line of code.

---

## Quick Start (60 Seconds)

```python
from connectonion import Agent

def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"

agent = Agent("helper", tools=[search])

# Make it network-accessible
agent.serve()
```

**Output:**
```
Agent 'helper' serving at: 0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
Connected to relay: wss://oo.openonion.ai/ws/announce
Waiting for connections...
```

**That's it.** Your agent is now accessible from anywhere.

---

## What Just Happened?

When you called `agent.serve()`:

1. **Generated Ed25519 keys** → Saved to `.co/keys/helper/`
2. **Connected to relay server** → WebSocket at `wss://oo.openonion.ai/ws/announce`
3. **Announced presence** → Sent ANNOUNCE message with public key
4. **Started listening** → Waits for INPUT messages

Your agent's **address** is its Ed25519 public key:
```
0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
```

---

## Testing Your Served Agent

### From Another Python Script

```python
from connectonion import connect

# Connect using the agent's address
remote = connect("0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")

# Use it like a local agent
result = remote.input("Search for Python docs")
print(result)
```

**Output:**
```
Results for: Python docs
```

### From Command Line

```bash
# Start serving (Terminal 1)
python agent.py

# Connect from another terminal (Terminal 2)
python -c "
from connectonion import connect
agent = connect('0x3d40...660c')
print(agent.input('test'))
"
```

---

## How It Works

### The Message Flow

```
Client                    Relay Server                 Your Agent
  |                            |                            |
  |--- INPUT message --------->|                            |
  |                            |--- INPUT message --------->|
  |                            |                            |
  |                            |                   [Process task]
  |                            |                            |
  |                            |<-- OUTPUT message ---------|
  |<-- OUTPUT message ---------|                            |
  |                            |                            |
```

### Message Format

When someone sends a task to your agent:

```python
# INPUT message (what your agent receives)
{
  "type": "INPUT",
  "from": "0xclient_public_key...",
  "task": "Search for Python docs",
  "relay_url": "wss://oo.openonion.ai/ws/announce"
}

# OUTPUT message (what your agent sends back)
{
  "type": "OUTPUT",
  "to": "0xclient_public_key...",
  "result": "Results for: Python docs"
}
```

All messages are automatically signed with your agent's private key and verified by the relay.

---

## Configuration

### Custom Relay Server

```python
# Use a different relay server
agent.serve(relay_url="ws://localhost:8000/ws/announce")
```

### Custom Keys Location

```python
# Keys are automatically saved to: .co/keys/{agent_name}/
# - private_key.pem
# - public_key.pem

# The agent loads these on subsequent runs
agent.serve()  # Uses existing keys if found
```

---

## Complete Example

```python
from connectonion import Agent

# Tool 1: Web search
def search(query: str) -> str:
    """Search the web."""
    import requests
    # Actual search implementation
    return f"Search results for {query}"

# Tool 2: Save to file
def save_file(filename: str, content: str) -> str:
    """Save content to a file."""
    with open(filename, 'w') as f:
        f.write(content)
    return f"Saved to {filename}"

# Create agent
agent = Agent(
    name="research_assistant",
    tools=[search, save_file],
    system_prompt="You are a research assistant. Search and save findings."
)

# Serve it
print(f"Starting {agent.name}...")
agent.serve()
```

**Terminal output:**
```
Starting research_assistant...
Agent 'research_assistant' serving at: 0x7a8f...9b2c
Connected to relay: wss://oo.openonion.ai/ws/announce

Keys saved to: .co/keys/research_assistant/
  - private_key.pem
  - public_key.pem

Waiting for connections...
```

**Test from another script:**
```python
from connectonion import connect

# Connect to the research assistant
assistant = connect("0x7a8f...9b2c")

# Use it
result = assistant.input("Search for AI trends and save to trends.txt")
print(result)
```

**Output:**
```
I've searched for AI trends and saved the findings to trends.txt.
```

---

## What Happens Behind the Scenes

### 1. Key Generation (First Run Only)

```python
# Automatic on first serve()
import nacl.signing

signing_key = nacl.signing.SigningKey.generate()
verify_key = signing_key.verify_key

# Saved to .co/keys/{agent_name}/
# - private_key.pem (Ed25519 signing key)
# - public_key.pem (Ed25519 verify key)
```

### 2. WebSocket Connection

```python
# Connect to relay
ws = websocket.connect("wss://oo.openonion.ai/ws/announce")

# Send ANNOUNCE message
announce_msg = {
    "type": "ANNOUNCE",
    "public_key": "0x7a8f...9b2c",
    "timestamp": 1234567890,
    "signature": "..."  # Signed with private key
}
ws.send(json.dumps(announce_msg))
```

### 3. Message Loop

```python
# Simplified version of what happens
while True:
    message = ws.recv()

    if message["type"] == "INPUT":
        # Process the task
        result = agent.input(message["task"])

        # Send OUTPUT back
        output_msg = {
            "type": "OUTPUT",
            "to": message["from"],
            "result": result
        }
        ws.send(json.dumps(output_msg))

    elif message["type"] == "HEARTBEAT":
        # Respond to keep connection alive
        ws.send(json.dumps({"type": "HEARTBEAT_ACK"}))
```

---

## Common Patterns

### 1. Serve Multiple Agents

```python
# Each agent gets its own address
agent1 = Agent("searcher", tools=[search])
agent2 = Agent("writer", tools=[write])

# Serve them (in separate processes/threads)
import threading

t1 = threading.Thread(target=agent1.serve)
t2 = threading.Thread(target=agent2.serve)

t1.start()
t2.start()

t1.join()
t2.join()
```

### 2. Serve with Error Handling

```python
from connectonion import Agent

agent = Agent("helper", tools=[search])

while True:
    agent.serve()
```

The `serve()` method will automatically reconnect if the connection drops.

### 3. Development vs Production

```python
import os

# Use local relay for development
if os.getenv("ENV") == "production":
    relay_url = "wss://oo.openonion.ai/ws/announce"
else:
    relay_url = "ws://localhost:8000/ws/announce"

agent.serve(relay_url=relay_url)
```

---

## Security

### Ed25519 Cryptography

Every message is signed with your agent's private key:

```python
# Automatic signing
message = {"type": "OUTPUT", "result": "..."}
signature = signing_key.sign(json.dumps(message).encode())

# Relay verifies with public key
verify_key.verify(signature)  # Raises exception if invalid
```

### Key Storage

Keys are stored in `.co/keys/{agent_name}/`:
- **private_key.pem** - Keep this secret! Never commit to git.
- **public_key.pem** - This is your agent's address, safe to share.

Add to `.gitignore`:
```
.co/
```

---

## Troubleshooting

### "Connection refused"

The relay server might be down or unreachable:

```python
# Try local relay server
agent.serve(relay_url="ws://localhost:8000/ws/announce")

# Or wait and retry
import time
while True:
    try:
        agent.serve()
    except Exception as e:
        print(f"Error: {e}, retrying in 5s...")
        time.sleep(5)
```

### "Keys not found"

First run generates keys automatically. If you deleted them:

```python
# Just serve again, new keys will be generated
agent.serve()
```

### "Address already in use"

An agent with the same name is already serving:

```python
# Use a different name
agent = Agent("helper_2", tools=[search])
agent.serve()

# Or stop the other agent first
```

---

## Learn More

- **[connect.md](connect.md)** - Connect to remote agents
- **[Agent](concepts/agent.md)** - Core Agent documentation
- **[protocol/agent-relay-protocol.md](protocol/agent-relay-protocol.md)** - Protocol specification

---

## Summary

`agent.serve()` makes your agent network-accessible:

- **One line of code** - `agent.serve()`
- **Automatic key generation** - Ed25519 cryptographic identity
- **Relay connection** - WebSocket to `wss://oo.openonion.ai/ws/announce`
- **Public key address** - `0x3d40...660c` is your agent's unique address
- **Zero configuration** - Just call `serve()` and it works

**Simple case:**
```python
agent.serve()
```

**Custom relay:**
```python
agent.serve(relay_url="ws://localhost:8000/ws/announce")
```

That's it. Now go make your agents network-accessible.
