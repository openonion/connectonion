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
    "tcp://192.168.1.100:8001",
    "tcp://73.42.18.9:8001",
    "relay://relay.connectonion.io"
  ],
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
| `endpoints` | array | Yes | Connection endpoints in priority order |
| `signature` | string | Yes | Ed25519 signature of all fields |

## Endpoints Format

Endpoints use URI scheme for self-documentation:

- `tcp://192.168.1.100:8001` - Local network direct connection
- `tcp://73.42.18.9:8001` - Public IP direct connection
- `relay://relay.connectonion.io` - WebSocket relay (always works)

Order matters - first endpoint is preferred, last is fallback.

## Minimal Valid Example

```json
{
  "type": "ANNOUNCE",
  "address": "0x3d40...",
  "timestamp": 1234567890,
  "summary": "",
  "endpoints": [
    "tcp://127.0.0.1:8001",
    "relay://relay.connectonion.io"
  ],
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
  "endpoints": [...],

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

This minimal design keeps messages small while providing everything needed for discovery and connection.