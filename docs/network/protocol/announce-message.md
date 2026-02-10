# ANNOUNCE Message Specification

The ANNOUNCE message broadcasts agent presence and connectivity information to the network.

## Message Structure

```json
{
  "type": "ANNOUNCE",
  "address": "0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
  "timestamp": 1234567890,
  "summary": "I translate text between 100+ languages with cultural context",
  "endpoints": [
    "http://localhost:8000",
    "ws://localhost:8000/ws",
    "http://192.168.1.50:8000",
    "ws://192.168.1.50:8000/ws",
    "http://73.42.18.9:8000",
    "ws://73.42.18.9:8000/ws"
  ],
  "relay": "wss://oo.openonion.ai",
  "signature": "0xabc123..."
}
```

## Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Always "ANNOUNCE" |
| `address` | string | Yes | Agent's public address (0x + hex encoded Ed25519 public key) |
| `timestamp` | number | Yes | Unix timestamp to prevent replay attacks |
| `summary` | string | Yes | Natural language description of agent capabilities |
| `endpoints` | array | Yes | Direct connection URLs (http and ws) |
| `relay` | string | No | Fallback relay server URL |
| `signature` | string | Yes | Ed25519 signature of all fields |

## Endpoints Format

Endpoints are full URLs that clients can use directly:

- `http://localhost:8000` - HTTP API
- `ws://localhost:8000/ws` - WebSocket
- `http://192.168.1.50:8000` - Local network HTTP
- `ws://192.168.1.50:8000/ws` - Local network WebSocket

Order: localhost first, then local network, then public IP.

## Relay Field

Separate from endpoints - fallback when direct connections fail.

## Endpoint Discovery

```python
from connectonion.network.announce import get_endpoints

endpoints = get_endpoints(8000)
# ["http://localhost:8000", "ws://localhost:8000/ws", ...]
```

Discovery sources:
- **localhost** - Always included
- **Local IPs** - Via `ifaddr` (WiFi, Ethernet, etc.)
- **Public IP** - Via `ipify` service

## Minimal Valid Example

```json
{
  "type": "ANNOUNCE",
  "address": "0x3d40...",
  "timestamp": 1234567890,
  "summary": "",
  "endpoints": [
    "http://localhost:8000",
    "ws://localhost:8000/ws"
  ],
  "relay": "wss://oo.openonion.ai",
  "signature": "0x..."
}
```

## Optional Fields

Additional fields can be added at root level when needed:

```json
{
  "type": "ANNOUNCE",
  "address": "0x3d40...",
  "timestamp": 1234567890,
  "summary": "I translate text",
  "endpoints": ["http://localhost:8000", "ws://localhost:8000/ws"],
  "relay": "wss://oo.openonion.ai",

  "nat_type": "restricted",     // For NAT traversal
  "wifi_ssid": "HomeNetwork",   // For local discovery
  "tools": ["translate"],       // For detailed matching

  "signature": "..."
}
```

## When to Send

1. Agent starts up
2. Every 60 seconds while running
3. When capabilities change
4. Before shutting down (optional)

## Size Considerations

- Typical size: ~400 bytes
- Maximum recommended: 1KB
- Network overhead: 400KB/min for 1000 agents

## Signature Generation

```python
# 1. Remove signature field
message_dict = {k: v for k, v in announce.items() if k != "signature"}

# 2. Serialize deterministically
message_bytes = json.dumps(message_dict, sort_keys=True).encode()

# 3. Sign with Ed25519 private key
signature = signing_key.sign(message_bytes).signature.hex()

# 4. Add signature to message
announce["signature"] = "0x" + signature
```

## Design Rationale

- **No status field**: Being online is implied by sending ANNOUNCE
- **No sequence number**: Timestamp provides ordering and replay prevention
- **Address not pubkey**: Clarifies it's used for routing, not just identity
- **Summary not capabilities**: Natural language from system prompt is more flexible
- **Relay as separate field**: Direct endpoints vs fallback relay are conceptually different

This minimal design keeps messages small while providing everything needed for discovery and connection.

## Future Support (TODO)

- `tcp://` - Direct TCP connections
- `udp://` - UDP connections
- `quic://` - QUIC protocol