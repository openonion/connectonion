# Multi-Agent Networking

Connect and collaborate between agents with automatic reliability and recovery.

## Core Concepts

- [host.md](host.md) - Make agents network-accessible with `host()`
- [connect.md](connect.md) - Connect to remote agents with `connect()`
- [connection.md](connection.md) - Stream events and communicate with clients

## Key Features

### 🔄 Automatic Connection Recovery
- WebSocket failures automatically fall back to HTTP polling
- Page refresh doesn't lose your work
- Results recoverable for 24 hours

### 💓 Built-in Keep-Alive
- Server sends PING every 30 seconds
- Client automatically responds with PONG
- Dead connections detected within 60 seconds

### ⏱️ Extended Timeout
- Default 10-minute timeout for long-running tasks
- Configurable per request
- Works even if agent takes hours (via polling)

### 📦 Session Persistence
- Results stored server-side for 24 hours
- Session ID automatically managed
- localStorage (browser) survives page refreshes

## Protocol Specifications

- [protocol/agent-relay-protocol.md](protocol/agent-relay-protocol.md) - Agent relay protocol spec
- [protocol/announce-message.md](protocol/announce-message.md) - Service announcement protocol
