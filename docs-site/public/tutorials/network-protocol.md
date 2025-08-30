# ConnectOnion Network Protocol

Minimal peer-to-peer protocol using public keys as network addresses.

## Core Design

### Public Keys as Addresses
Public keys serve as network addresses, similar to IP addresses in TCP/IP. They provide a unique, unforgeable way to route messages between agents. No identity claims, no trust assumptions - just addressing.

### Message-Based Architecture
The protocol uses stateless, message-based communication similar to email. Each message is self-contained with a unique task ID for correlation. This design naturally supports parallel operations, resilience to failures, and works seamlessly across NAT boundaries. Unlike session-based protocols (HTTP/gRPC), agents don't maintain connection state - they simply exchange signed messages.

### Two-Layer Separation
**Public Discovery Layer**: ANNOUNCE and FIND messages are unencrypted broadcasts for transparency. Organizations can audit capabilities and network activity.
**Private Collaboration Layer**: TASK messages carry encrypted payloads between agents. Actual work remains confidential while discovery stays transparent.

### Developer-Controlled Broadcasting
Agents announce themselves only when developers explicitly call the announce() function. No automatic broadcasts, no hidden network activity.

## Network Topology

### Agent Nodes
Standard participants in the network. Each agent maintains connections to other agents, divided into:
- **Contacts**: Agents with established collaborative history
- **Strangers**: Agents discovered but not yet verified

### Relay Nodes
Infrastructure nodes that serve as message routers and connection points:
- **Message Relay**: Forward messages between agents that cannot directly connect (NAT traversal)
- **Presence Tracking**: Know which agents are currently connected (in memory only)
- **Initial Discovery**: Help new agents find their first peers

Relays maintain no permanent state and can be run by anyone. At scale, relays form a hierarchical network similar to CDN or DNS infrastructure.

## Protocol Messages

### Public Discovery Messages

#### ANNOUNCE Message
Purpose: Public broadcast of agent existence, capabilities, network endpoints, and liveness.

**Data Structure:**
```
{
  type: "ANNOUNCE",
  pubkey: <sender's public key>,
  timestamp: <unix timestamp>,
  sequence: <incrementing counter>,
  
  // Network Endpoints (for connectivity)
  endpoints: [
    "tcp://73.42.18.9:8001",      // Public IP address
    "tcp://192.168.1.100:8001",   // Local LAN IP  
    "relay://abc123.connectonion.io"  // Relay lookup (returns current IP)
  ],
  nat_type: "none" | "full_cone" | "restricted" | "symmetric",
  
  // Capabilities
  prompt_summary: <system prompt description>,
  tools: [<list of available tools>],
  
  // Liveness
  uptime: <seconds since start>,
  last_activity: {
    type: <"tool_call" | "task_complete">,
    timestamp: <when>,
    tool: <which tool if applicable>
  },
  
  // Status
  status: "active" | "idle" | "busy",
  load: <0.0 to 1.0>,
  
  // Metadata
  version: <agent version>,
  model: <LLM model used>,
  state_hash: <hash for change detection>
}
```

**Characteristics:**
- Unencrypted for transparency
- Single-hop forwarding maximum
- Sent on developer trigger (startup, task completion, changes, IP address change)

#### FIND Message
Purpose: Query network for specific capabilities.

**Data Structure:**
```
{
  type: "FIND",
  pubkey: <requester's public key>,
  query_id: <unique query identifier>,
  capability: <natural language description>,
  ttl: <hop counter, typically 3-4>,
  timestamp: <unix timestamp>
}
```

**Characteristics:**
- Propagates through network (TTL-limited)
- Small size for efficient flooding
- Responses return via ANNOUNCE

### Private Collaboration Messages

#### TASK Message
Purpose: Carry actual work between agents.

**Data Structure:**
```
{
  type: "TASK",
  from: <sender pubkey>,
  to: <recipient pubkey>,
  
  // Correlation
  task_id: <unique task identifier>,
  thread_id: <optional conversation context>,
  
  // Payload
  task_type: "request" | "response" | "error",
  encrypted_payload: <encrypted with recipient's public key>,
  
  // Metadata
  timestamp: <when sent>,
  ttl: <message expiry>,
  priority: "high" | "normal" | "low",
  
  // Security
  signature: <sign(all above fields)>
}
```

**Why Message-Based:**
- **Parallel by Design**: Each task has unique ID, enabling concurrent operations
- **Stateless**: No session management, agents can restart without losing work
- **NAT-Friendly**: Works through relays without persistent connections
- **Simple Mental Model**: Like email with threading and signatures
- **Resilient**: Messages can be queued, retried, and delivered asynchronously

## Data Storage

### Contact Records

Information about agents with established collaboration:

```
{
  pubkey: <public key>,
  
  // Network information
  endpoints: [<known connection methods>],
  last_seen: <timestamp>,
  
  // Collaboration history
  successful_tasks: <count>,
  failed_tasks: <count>,
  last_collaboration: <timestamp>,
  
  // Performance metrics
  avg_response_time: <milliseconds>,
  reliability_score: <0.0 to 1.0>
}
```

Storage: Persistent, limited to ~150 entries (Dunbar's number)

### Stranger Cache

Temporary information about discovered agents:

```
{
  pubkey: <public key>,
  
  // Discovery information
  discovered_via: <which contact>,
  first_heard: <timestamp>,
  last_heard: <timestamp>,
  
  // Claimed capabilities (unverified)
  prompt_summary: <their claim>,
  tools: [<claimed tools>]
}
```

Storage: Ephemeral, maximum 500 entries, auto-expire after 1 hour

### Path Cache

Routing information for message delivery:

```
{
  target_pubkey: <destination>,
  next_hop: <immediate neighbor to route through>,
  confidence: <0.0 to 1.0>,
  expires_at: <timestamp>
}
```

Storage: Memory only, 5-15 minute TTL

### Endpoint Claims

Self-signed assertions about how to connect:

```
{
  pubkey: <claiming agent>,
  transport: "tcp" | "udp" | "websocket" | "bluetooth",
  endpoint: <connection string>,
  issued_at: <timestamp>,
  expires_at: <timestamp>,
  signature: <signed by claiming agent>
}
```

Validation: Must be signed by claimed pubkey, must not be expired

## Message Forwarding

### Single-Hop Rule
HEARTBEAT messages forward at most one hop. This prevents exponential flooding while allowing immediate neighbors to learn about second-degree connections.

### TTL-Based Propagation
NEED messages propagate based on TTL, decremented at each hop. This allows controlled network-wide search.

### Selective Forwarding
Agents forward messages based on:
- Sender relationship (contact vs stranger)
- Message relevance
- Local rate limits
- Change significance (for HEARTBEATs)

### Deduplication
Message IDs tracked in a rolling window (5 minutes) to prevent forwarding the same message twice.

## Network Entry

### Via Relay Nodes
New agents can use relay nodes for address lookup:
1. Agents announce their current IP addresses directly
2. If IP changes or isn't included, relay provides lookup service
3. Relay returns current endpoints for any public key
4. Clients connect directly using returned endpoints

### Relay as Lookup Service
The relay server serves as a simple directory:
- Stores mapping of public key → current IP addresses
- Returns endpoints when queried by public key
- Does NOT proxy actual agent-to-agent traffic
- Optional paid service for guaranteed availability (future)

### Relay Discovery
Relays can be discovered through:
- Default relay server (provided by ConnectOnion)
- Environment variables for custom relays
- DNS TXT records

## Rate Limiting

### Per-Agent Limits
- HEARTBEAT: Maximum 1 per minute
- NEED: Maximum 10 per minute
- Forward budget: 100 messages per minute

### Natural Throttling
- Activity-based announcements (not periodic)
- Single-hop forwarding
- TTL limits
- Selective forwarding

## Transport Layer

### Multi-Transport Support

**Relay Communication (Agent ↔ Relay):**
- WebSocket/WSS (firewall-friendly, persistent connection)
- Used for: address lookup, NAT traversal coordination
- Always works through corporate/university firewalls

**Direct Agent-to-Agent Communication:**
- TCP (primary data transfer, reliable)
- UDP (discovery broadcasts, hole-punching)
- HTTP/HTTPS (fallback when TCP blocked)

**Connection Flow:**
1. Agent connects to relay via WebSocket for address lookup
2. Relay returns target agent's direct endpoints
3. Agents attempt direct connection via TCP/UDP
4. Fallback to HTTP if TCP/UDP blocked by firewall

### Connection Priority
1. Direct connection to known endpoint
2. Recently successful transport
3. UDP hole punching attempt
4. Relay-mediated connection
5. Queue for later delivery

## Memory Requirements

### Typical Agent Storage
- Contacts: 150 entries × 1KB = 150KB
- Strangers: 500 entries × 200 bytes = 100KB  
- Path cache: 1000 entries × 64 bytes = 64KB
- Message IDs: 10,000 entries × 32 bytes = 320KB
- **Total: ~650KB to 2MB typical**

### Relay Storage (Memory Only)
- Active connections: 100 bytes per connection
- 10,000 connections = 1MB
- 100,000 connections = 10MB
- **No persistent storage required**

## Protocol Properties

### Scalability
- No global state required
- Each agent knows only local neighborhood
- Natural clustering by collaboration
- Supports billions of agents

### Performance
- Message size: HEARTBEAT ~1KB, NEED ~200 bytes
- Discovery time: 200-500ms typical
- Direct message: <50ms
- Network diameter: ~6 hops (small world)

### Resilience
- No single point of failure
- Natural redundancy through multiple paths
- Automatic expiration of stale data
- Self-healing through gossip

### Privacy
- No global directory
- Only next-hop stored in routing
- Connections visible only to participants
- No mandatory broadcasts

## Implementation Notes

### Message Serialization
Messages should be serialized using MessagePack or JSON for interoperability.

### Cryptographic Requirements
- Ed25519 for public keys (32 bytes)
- Signatures on endpoint claims
- No encryption at protocol level (application concern)

### Time Synchronization
Protocol assumes loose time synchronization (within 5 minutes) for TTL and expiration.

### Connection Persistence
Connections to contacts should be kept alive when possible to reduce discovery overhead.

## Why Message-Based Architecture

### The Problem with Sessions
Session-based protocols (HTTP, gRPC, WebSockets) were designed for client-server interactions where:
- Order matters
- State is maintained
- Connections are persistent
- Operations are sequential

AI agents don't fit this model. They naturally handle multiple tasks in parallel, may restart at any time, and often can't maintain direct connections due to NAT.

### Why Message-Based Wins

**Natural Parallelism**
Each task gets a unique ID. Agents can handle hundreds of concurrent tasks without managing session state or connection pools. Responses arrive asynchronously and are correlated by task ID.

**Resilience By Default**
Messages don't require persistent connections. If an agent crashes, messages queue at relays. If the network fails, messages retry. No session state to rebuild, no connection pools to manage.

**NAT Traversal Simplicity**
Messages route through relays without complex hole-punching or session maintenance. The sender doesn't need to know if the recipient is behind NAT - messages find their way.

**50-Year Proven Model**
Email has survived because message-based architecture is fundamentally correct for asynchronous, distributed communication. AI agents have the same requirements: async operation, distributed nodes, unreliable networks.

### The Unix Philosophy Applied
Like Unix pipes, each agent is a filter that processes messages. Composition is natural, parallelism is free, and the mental model is simple. No complex state machines, no session management, just messages with IDs.

## Summary

The ConnectOnion protocol embraces message-based architecture because it perfectly matches how AI agents actually work: parallel task processing, resilient to failures, and simple to understand. 

Public discovery happens transparently through ANNOUNCE/FIND broadcasts, while private work flows through encrypted TASK messages. This separation gives organizations the auditing they need while preserving the confidentiality of actual work.

With public keys as addresses and messages as the communication primitive, the protocol provides just enough infrastructure for agents to find and collaborate with each other, without the complexity of session management or the overhead of persistent connections.