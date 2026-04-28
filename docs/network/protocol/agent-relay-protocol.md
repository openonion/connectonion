# Agent-Relay Connection Protocol

This document specifies the WebSocket-based protocol for agent registration, discovery, and connection establishment.

## Developer Experience

**Developers only need one thing: the agent's address**

```python
from connectonion import connect

# Connect to any agent using just their address
translator = connect("0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
result = translator.input("Translate 'Hello world' to Spanish")
# Returns: "Hola mundo"
```

**What happens behind the scenes:**

1. **Query Relay**: Gets agent's endpoints and network info
2. **Smart Connection**: Tries local network → public IP → relay
3. **Automatic Optimization**: Uses fastest available path
4. **Transparent Failover**: Switches to relay if direct fails
5. **Simple Interface**: Returns agent ready to use

The framework handles everything automatically:
- Discovery via relay (like DNS lookup)
- Direct connection establishment (like WebRTC)
- Protocol selection (TCP when possible, relay when needed)
- Automatic failover (seamless switching)
- Reconnection on failure (self-healing)

## Overview

The relay server (`oo.openonion.ai`) acts as a directory service where agents:
1. Register their presence via WebSocket
2. Discover other agents
3. Exchange connection information for direct communication

## Connection Lifecycle

### 1. Establishing Connection

The relay provides two WebSocket endpoints by function:

- **`wss://oo.openonion.ai/announce`** - Agents announce their presence here
- **`wss://oo.openonion.ai/lookup`** - Clients look up agent info here

### 2. Agent Registration via `/announce`

Agents connect to the announce endpoint and stay connected:

```json
{
  "type": "ANNOUNCE",
  "address": "0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
  "timestamp": 1234567890,
  "summary": "I translate text between 100+ languages",
  "endpoints": [
    "tcp://192.168.1.100:8001",
    "tcp://73.42.18.9:8001"
  ],
  "signature": "0xabc123..."
}
```

### 3. Heartbeat & Keep-Alive

**Application-level heartbeat (ANNOUNCE):**
- Agent re-sends ANNOUNCE every 60 seconds
- Updates capability/endpoint information
- Confirms agent is still active
- Agents not announcing for 120s are removed from registry

**Note:** WebSocket protocol-level PING/PONG frames are **disabled** (`ping_interval=None`) because Cloudflare terminates the WebSocket connection at the edge and opens a new one to the origin. Protocol-level PING frames sent by the agent reach Cloudflare but are not forwarded to the relay origin, causing the library to falsely detect the connection as dead after ~40s. The ANNOUNCE heartbeat serves the same keep-alive purpose at the application layer.

### 4. Disconnection

When WebSocket closes:
- Agent removed from active registry
- No longer discoverable
- All associated data cleared from memory

## Message Types

### ANNOUNCE (Agent → Relay)

Registers or updates agent information.

```json
{
  "type": "ANNOUNCE",
  "address": "0x...",
  "timestamp": 1234567890,
  "summary": "Natural language description of capabilities",
  "endpoints": ["tcp://ip:port", ...],
  "signature": "0x..."
}
```

**Relay Processing:**
1. Verify signature
2. Store/update in memory
3. Associate with WebSocket connection
4. No response sent (success assumed)

### FIND (Client → Relay via `/lookup`)

Query for agents with specific capabilities.

```json
{
  "type": "FIND",
  "query": "translate text to spanish",
  "from": "0xRequesterAddress...",
  "timestamp": 1234567890
}
```

**Relay Response:**

```json
{
  "type": "AGENTS",
  "query": "translate text to spanish",
  "agents": [
    {
      "address": "0xAgentAddress...",
      "summary": "I translate text between languages",
      "endpoints": [
        "tcp://192.168.1.100:8001",
        "tcp://73.42.18.9:8001"
      ],
      "last_seen": 1234567880
    }
  ],
  "timestamp": 1234567890
}
```

### GET_AGENT (Client → Relay via `/lookup`)

Query specific agent by address.

```json
{
  "type": "GET_AGENT",
  "address": "0xTargetAgent...",
  "from": "0xRequesterAddress...",
  "timestamp": 1234567890
}
```

**Relay Response:**

```json
{
  "type": "AGENT_INFO",
  "agent": {
    "address": "0xTargetAgent...",
    "summary": "I translate text",
    "endpoints": ["tcp://192.168.1.100:8001"],
    "last_seen": 1234567880,
    "online": true
  }
}
```

**If agent not found:**

```json
{
  "type": "AGENT_INFO",
  "agent": null,
  "error": "Agent not found or offline"
}
```

### ERROR (Relay → Agent)

Sent when relay cannot process a message.

```json
{
  "type": "ERROR",
  "error": "Invalid signature",
  "original_type": "ANNOUNCE",
  "timestamp": 1234567890
}
```

## Connection Establishment Flow

### Complete `connect()` Flow

When a developer calls `connect("0x3d40...")`, the following sequence happens:

```
Client                     Relay                      Target Agent
   |                         |                             |
   |-- Connect to /lookup -->|                             |
   |                         |                             |
   |-- GET_AGENT request -->|                             |
   |   (address: 0x3d40...)  |                             |
   |                         |                             |
   |<-- AGENT_INFO ---------|                             |
   |   (endpoints, NAT type) |                             |
   |                         |                             |
   |-- Disconnect ---------->|                             |
   |                         |                             |
   |-- Try Direct TCP ---------------------------------->|
   |   (using endpoints)     |                             |
   |                         |                             |
   |   If direct fails:      |                             |
   |-- Connect to relay ---->|                             |
   |-- RELAY_TO_AGENT ------>|-- Forward to agent ------->|
   |                         |<-- Response from agent ----|
   |<-- Forward response ----|                             |
```

### Step 1: Query Agent Information

The client first connects to `/lookup` to get the target agent's connection details:

```
Client → Relay (via /lookup): GET_AGENT
{
  "type": "GET_AGENT",
  "address": "0x3d40..."
}

Relay → Client: AGENT_INFO
{
  "type": "AGENT_INFO",
  "agent": {
    "address": "0x3d40...",
    "endpoints": [
      "tcp://192.168.1.100:8001",  # Local network
      "tcp://73.42.18.9:8001"      # Public IP
    ],
    "nat_type": "restricted",       # For NAT traversal
    "wifi_ssid": "HomeNetwork",     # For local network detection
    "online": true
  }
}

Client → Relay: Disconnect from /lookup
```

### Step 2: Connection Priority Strategy

The client attempts connections in order of likelihood and speed:

1. **Local Network First** (fastest, if on same WiFi)
   - Check if wifi_ssid matches
   - Try local IP endpoints (192.168.x.x, 10.x.x.x)

2. **Public IP Direct** (if NAT allows)
   - Try public IP endpoints
   - Success depends on NAT type

3. **NAT Traversal** (if both behind NAT)
   - Use STUN-like coordination through relay
   - Simultaneous connection attempts

4. **Relay Fallback** (always works)
   - Route all messages through relay
   - Higher latency but guaranteed delivery

### Step 3: Direct Connection Attempt

```
Client                                              Agent B
   |                                                    |
   |-- TCP Connect to 192.168.1.100:8001 ------------->|
   |<-- TCP Accept -------------------------------------|
   |                                                    |
   |-- Direct TASK Message ---------------------------->|
   |<-- Direct TASK Response ---------------------------|
```

### Step 4: Fallback to Relay (if direct fails)

```
Client                     Relay                     Agent B
   |                         |                          |
   |-- RELAY_TO_AGENT ------>|                          |
   |   to: "0x3d40..."       |                          |
   |   payload: {...}        |-- Forward to Agent ----->|
   |                         |<-- Response -------------|
   |<-- Forward Response ----|                          |
```

## NAT Traversal Strategies

### NAT Type Detection

The relay helps detect NAT types during ANNOUNCE:

| NAT Type | Can Receive Connections | Strategy |
|----------|------------------------|----------|
| **No NAT / Full Cone** | Yes, from anyone | Direct connection works |
| **Restricted Cone** | Only from contacted IPs | Coordination required |
| **Port Restricted** | Only from contacted IP:port | Precise coordination |
| **Symmetric** | Different port for each destination | Usually requires relay |

### Connection Strategies by NAT Combination

#### Both on Same Local Network
- **Strategy**: Direct local IP connection
- **Detection**: Same wifi_ssid or subnet
- **Success Rate**: ~100%

#### One or Both Have Public IP (No NAT)
- **Strategy**: Direct TCP connection
- **Detection**: Public endpoint accessible
- **Success Rate**: ~100%

#### Both Behind NAT (Same Type)
- **Strategy**: STUN-like hole punching
- **Process**:
  1. Both agents contact relay
  2. Relay coordinates simultaneous connection
  3. Both attempt connection at same time
- **Success Rate**: ~70% for cone NATs

#### Symmetric NAT Involved
- **Strategy**: Relay required
- **Reason**: Port prediction impossible
- **Success Rate**: 100% via relay

### Smart Endpoint Selection

The client prioritizes endpoints based on network analysis:

```
Priority Order:
1. localhost (same machine) - 0ms latency
2. Local network (same WiFi) - 1-5ms latency
3. Direct public IP - 10-50ms latency
4. NAT traversal - 20-100ms latency
5. Relay fallback - 50-200ms latency
```

## Relay Server Behavior

### Memory Storage

The relay maintains in-memory registry:

```python
agents = {
  "0xAgentAddress...": {
    "summary": "...",
    "endpoints": [...],
    "websocket": <WebSocket object>,
    "last_announce": timestamp,
    "last_ping": timestamp
  }
}
```

### Cleanup Policy

Agents are removed when:
1. WebSocket disconnects
2. No ANNOUNCE received for 120 seconds

### Discovery Matching

For FIND queries, relay:
1. Performs semantic similarity on summaries
2. Returns top 10 matches
3. Prioritizes recently active agents

## Security Considerations

### Signature Verification

All ANNOUNCE messages must be signed:
1. Remove signature field from message
2. Serialize remaining fields (deterministic JSON)
3. Verify Ed25519 signature matches public key (address)

### Rate Limiting

- ANNOUNCE: Max 1 per 10 seconds per agent
- FIND: Max 10 per minute per agent
- GET_AGENT: Max 100 per minute per agent

### Privacy

- Relay only stores minimal information
- No message content is logged
- Endpoints can be omitted for privacy

## Implementation Notes

### WebSocket Configuration

- ANNOUNCE heartbeat: 60 seconds
- Protocol-level PING: disabled (Cloudflare incompatible)
- Message size limit: 64KB
- Stale agent cleanup: 120 seconds without ANNOUNCE
- Automatic reconnection with exponential backoff

### Recommended Client Behavior

1. Connect to relay on startup
2. Send ANNOUNCE immediately
3. Send ANNOUNCE every 60 seconds (application-level heartbeat)
4. Implement reconnection logic
5. Cache discovered agents locally

### Direct Connection Strategy

When connecting to another agent:
1. Try local IPs first (same network)
2. Try public IP (if available)
3. Fall back to relay-forwarded messages
4. Cache successful routes

## Example Implementation

### Agent Connection to `/announce`

```python
async def connect_to_relay():
    ws = await websocket.connect("wss://oo.openonion.ai/announce")

    # Send initial ANNOUNCE
    await ws.send(json.dumps({
        "type": "ANNOUNCE",
        "address": my_address,
        "summary": my_summary,
        "endpoints": gather_endpoints(),
        "timestamp": int(time.time()),
        "signature": sign_message(...)
    }))

    # Start announce loop
    asyncio.create_task(announce_loop(ws))

    # Handle messages
    async for message in ws:
        await handle_relay_message(json.loads(message))
```

### Using Remote Agents

```python
# Simple usage with connect()
from connectonion import connect

async def use_translator():
    # Connect to remote agent
    translator = connect("0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")

    # Use it naturally
    result = translator.input("Translate 'Hello world' to Spanish")
    return result
```

### Finding Agents by Capability

```python
async def find_agent(capability):
    # Connect to lookup endpoint
    ws = await websocket.connect("wss://oo.openonion.ai/lookup")

    await ws.send(json.dumps({
        "type": "FIND",
        "query": capability,
        "from": my_address,
        "timestamp": int(time.time())
    }))

    response = await wait_for_response("AGENTS")
    await ws.close()  # Disconnect after getting response
    return response["agents"]
```

## Session Proxy Forwarding

When a client cannot connect directly to an agent, the relay acts as a **transparent message proxy**. The relay forwards messages as-is — it does not parse, modify, or strip any fields.

### How It Works

The relay provides two client-facing WebSocket endpoints:

- **`/ws/announce`** — Agents register here (long-lived connection)
- **`/ws/input`** — Clients connect here to reach agents

```
Client                        Relay                         Agent
  |                             |                              |
  |-- WS connect /ws/input ---->|                              |
  |-- CONNECT {session_id} ---->|                              |
  |                             |-- forward via /ws/announce ->|
  |                             |                              |-- loopback WS to /ws
  |                             |                              |-- CONNECT → local /ws
  |                             |<-- CONNECTED {session_id} ---|
  |<-- CONNECTED ---------------|                              |
  |                             |                              |
  |-- INPUT {session_id} ------>|                              |
  |                             |-- forward ------------------>|
  |                             |                              |-- INPUT → local /ws
  |                             |<-- STREAM_DELTA {session_id}-|
  |<-- STREAM_DELTA ------------|                              |
  |                             |<-- OUTPUT {session_id} ------|
  |<-- OUTPUT ------------------|                              |
```

### session_id Routing

Every message carries a `session_id` field. This is the sole routing key:

- **Relay (`/ws/input`)**: Maps `session_id → client WebSocket`. Forwards agent responses to the correct client.
- **Relay (`/ws/announce`)**: Maps `session_id → agent WebSocket`. Forwards client messages to the correct agent.
- **Agent (`serve_loop`)**: Maps `session_id → asyncio.Queue`. Dispatches to per-session `_run_session` coroutines.

Messages without `session_id` (except ERROR type) are considered protocol violations and will crash the handler.

### Agent-Side: Loopback Architecture

When the agent receives a message via the relay's announce WebSocket, `serve_loop` routes it by `session_id`:

1. **New session**: Creates an `asyncio.Queue` and spawns `_run_session` as a background task.
2. **Existing session**: Puts the message into the session's queue.

`_run_session` opens a **loopback WebSocket** to `ws://127.0.0.1:{port}/ws` (the agent's own local endpoint). This reuses the full WebSocket protocol handler (`websocket.py`) without reimplementing CONNECT/INPUT/streaming/OUTPUT logic.

Two pump coroutines bridge the relay and local WebSocket:

- **`pump_relay_to_local`**: Reads from the session queue → forwards to local `/ws`
- **`pump_local_to_relay`**: Reads from local `/ws` → forwards back to relay announce WebSocket

All streaming events (STREAM_DELTA, TOOL_CALL, etc.) include `session_id` injected by `_pipe_ws_io` in `websocket.py`, so the relay can route responses to the correct client without any field manipulation.

### Why Loopback Instead of Direct IO

The agent's WebSocket protocol handler (`websocket.py`) implements CONNECT authentication, session merge, streaming, and all event types. Rather than duplicating this logic in the relay path, `_run_session` creates a local WebSocket connection and forwards messages through it. The protocol handler doesn't know whether the connection came from a direct client or via relay — it's the same code path.

## Summary

This protocol provides:
- Simple agent registration via WebSocket
- Efficient in-memory discovery
- Direct agent-to-agent connections
- Transparent relay proxy with session_id routing
- Automatic cleanup of inactive agents

The relay acts as both a directory service (discovery) and a transparent message proxy (when direct connection isn't possible). It never modifies message content — routing is based solely on `session_id`.