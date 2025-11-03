# Agent Serving - Making Your Agent Network-Ready

The `agent.serve()` method transforms your local agent into a network-accessible service that can handle long-running tasks and be debugged remotely.

## Quick Start

```python
# agent.py
from connectonion import Agent

def translate(text: str, to_lang: str = "es") -> str:
    """Translate text to another language."""
    return translation_result

agent = Agent(
    name="translator",
    tools=[translate],
    system_prompt="You are a helpful translator."
)

if __name__ == "__main__":
    agent.serve()  # That's it!
```

Run it:
```bash
python agent.py
```

Output:
```
════════════════════════════════════════
  🟢 Agent Online
  Public Key: 0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
════════════════════════════════════════

  Debug Interface:
  🔗 https://oo.openonion.ai/debug/0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c

  Protocol URL:
  co://0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c

  [Waiting for connections...]
════════════════════════════════════════
```

## How Agent Serving Works

When you call `agent.serve()`:

1. **Generates/loads Ed25519 keypair** - Your agent's cryptographic identity
2. **Starts message loop** - Listens for incoming TASK messages
3. **Connects to relay** - For NAT traversal and message routing
4. **Provides debug interface** - Web-based testing at oo.openonion.ai

## The Public Key as Address

Your agent's address is its Ed25519 public key in hex format:
```
0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
```

This is:
- **The actual public key** (not a hash like Ethereum)
- **Used for message verification** (every message is signed)
- **Your agent's unique identity** (unforgeable)
- **The routing address** (how messages find your agent)

## Debug Interface

Every served agent gets a debug console at:
```
https://oo.openonion.ai/debug/[your_public_key]
```

The debug console provides:
- Interactive message sending
- Real-time activity monitoring
- Protocol message inspection
- Performance metrics

## Long-Running Tasks

The serve architecture is designed for tasks that take 20+ minutes:

### Task Flow
1. **Client sends TASK message** → Gets task_id immediately
2. **Agent processes** → Works asynchronously in background
3. **Client checks status** → Polls with task_id
4. **Agent completes** → Result stored and retrievable

### Message Format
```python
# Incoming TASK message
{
  "type": "TASK",
  "from": "0xclient_public_key...",
  "to": "0xyour_agent_public_key...",
  "task_id": "task_ABC123",
  "task_type": "request",
  "encrypted_payload": "...",
  "signature": "..."
}

# Your agent's response
{
  "type": "TASK",
  "from": "0xyour_agent_public_key...",
  "to": "0xclient_public_key...",
  "task_id": "task_ABC123",
  "task_type": "response",
  "encrypted_payload": "...",
  "signature": "..."
}
```

## Protocol URL

Your agent gets a protocol URL:
```
co://0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
```

This URL:
- Opens debug interface when clicked
- Can be used by other agents to connect
- Works as universal agent locator

## Configuration

```python
agent.serve(
    # Relay connection
    relay="wss://relay.connectonion.io",  # Default relay

    # Capacity
    max_concurrent=10,     # Parallel task limit
    timeout=1200,         # 20 minutes default

    # Debugging
    debug=True,           # Enable web debugger
)
```

## What Happens Behind the Scenes

### 1. Key Management
```python
# Automatically handled
- Generate Ed25519 keypair if not exists
- Load from ~/.connectonion/keys/ if exists
- Public key becomes your address
```

### 2. Network Connection
```python
# Connect to relay via WebSocket
- Establish persistent connection
- Handle reconnection automatically
- Route messages through relay
```

### 3. Message Loop
```python
# Process incoming messages
while True:
    message = await receive_message()

    if message.type == "TASK":
        task_id = message.task_id
        result = await process_task(message.payload)
        send_response(task_id, result)
```

## Testing Your Served Agent

### Web Testing
Open the debug URL in any browser for interactive testing.

### Command Line
```bash
# Using protocol URL
co test co://0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c

# Submit task
co task submit 0x3d4017... "translate hello to spanish"

# Check status
co task status task_ABC123
```

### Python Testing
```python
from connectonion import connect

# Connect to agent using address
translator = connect("0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
result = translator.input("Translate 'Hello' to Spanish")
```

## Monitoring

Terminal dashboard shows real-time activity:

```
════════════════════════════════════════
  Agent Status: 🟢 Online
  Public Key: 0x3d40...660c

  Stats Today:
  • Tasks: 142
  • Avg Response: 1.2s
  • Success Rate: 99.3%

  Active Tasks: 4/10
  Queue: 2 pending

  Recent Activity:
  14:23:15 task_123 ✓ translate (1.1s)
  14:23:20 task_125 ⟳ analyze (45% complete)
════════════════════════════════════════
```

## Best Practices

1. **Let serve() handle everything** - Don't manually manage keys or connections
2. **Use the debug URL** - Test thoroughly before sharing your agent
3. **Monitor the dashboard** - Watch for performance issues
4. **Set appropriate timeouts** - Based on your task duration
5. **Trust the protocol** - Messages are automatically signed and verified

## Summary

`agent.serve()` transforms your agent into a network service with:
- Ed25519 public key as address
- Automatic relay connection
- Built-in debug interface
- Long task support (20+ minutes)
- Zero configuration required

The public key IS your address - no translation needed!