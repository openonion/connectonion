# Designing the ConnectOnion Network Protocol: From Complexity to Clarity

*December 2024*

When we set out to design a network protocol for AI agents to collaborate, we started with grand ambitions and complex architectures. Through iterative refinement and hard lessons, we arrived at something much simpler and more powerful. This is the story of how we got there.

## The Initial Vision: Too Much, Too Soon

We began by studying existing protocols - MCP (Model Context Protocol), gRPC, and various P2P systems. Our first designs were ambitious:

- Complex identity systems with cryptographic proofs
- Multiple message types for every possible scenario  
- Sophisticated trust models with reputation scores
- Session-based connections like HTTP/gRPC

It felt comprehensive. It also felt wrong.

## The First Breakthrough: Public Keys Are Just Addresses

The pivotal moment came when we realized we were overthinking identity. Public keys don't need to represent identity or trust - they're just addresses, like phone numbers or IP addresses. 

This insight simplified everything:
- No complex PKI infrastructure needed
- No identity verification protocols
- No certificate authorities
- Just addresses for routing messages

## Messages Over Sessions: Why Email Got It Right

We initially assumed we needed session-based connections like HTTP or gRPC. But AI agents don't work like web browsers - they handle hundreds of parallel tasks, each potentially taking minutes or hours to complete.

The solution? Message-based architecture, like email:

```python
# Not this (session-based):
connection = connect_to_agent()
response = connection.call("translate", text)
connection.close()

# But this (message-based):
send_message(agent_pubkey, task_id="abc123", request="translate", text=text)
# ... agent processes asynchronously ...
receive_message(task_id="abc123", response=translated_text)
```

Each message carries its own correlation ID. No sessions to manage. No connection state. Just messages flowing between agents.

### Why Message-Based Wins

**Natural Parallelism**: Each task gets a unique ID. Agents can handle hundreds of concurrent tasks without managing session state or connection pools. Responses arrive asynchronously and are correlated by task ID.

**Resilience By Default**: Messages don't require persistent connections. If an agent crashes, messages queue at relays. If the network fails, messages retry. No session state to rebuild, no connection pools to manage.

**NAT Traversal Simplicity**: Messages route through relays without complex hole-punching or session maintenance. The sender doesn't need to know if the recipient is behind NAT - messages find their way.

**50-Year Proven Model**: Email has survived because message-based architecture is fundamentally correct for asynchronous, distributed communication. AI agents have the same requirements: async operation, distributed nodes, unreliable networks.

### The Unix Philosophy Applied
Like Unix pipes, each agent is a filter that processes messages. Composition is natural, parallelism is free, and the mental model is simple. No complex state machines, no session management, just messages with IDs.

## The Two-Layer Revelation: Transparency AND Privacy

Organizations need transparency to audit AI agent behavior. But actual work needs privacy. We struggled with this tension until we realized: separate them into two layers.

**Public Discovery Layer (ANNOUNCE/FIND):**
- Unencrypted broadcasts
- Shows what agents exist and their capabilities
- Organizations can monitor and audit
- Like a public phone book

**Private Work Layer (TASK):**
- Encrypted point-to-point messages
- Actual work remains confidential
- Like private phone calls

This gives organizations the oversight they need without compromising the privacy of actual work.

## Relay Servers: Just a Lookup Service

We went through several iterations on relay servers:

1. **First design**: Full proxy servers (too centralized)
2. **Second design**: Complex NAT traversal with STUN/TURN (too complicated)
3. **Final design**: Simple lookup service

The relay just stores current IP addresses for public keys. When an agent's IP changes, it updates the relay. When another agent needs to connect, it asks the relay for the current IP, then connects directly. 

No data flows through the relay. It's just a phone book that updates when people move.

### Relay as Infrastructure

Relay nodes serve as message routers and connection points:
- **Message Relay**: Forward messages between agents that cannot directly connect (NAT traversal)
- **Presence Tracking**: Know which agents are currently connected (in memory only)
- **Initial Discovery**: Help new agents find their first peers

Relays maintain no permanent state and can be run by anyone. At scale, relays form a hierarchical network similar to CDN or DNS infrastructure.

## Transport Layer: Meet Users Where They Are

We learned that TCP on custom ports gets blocked by corporate firewalls. Our solution:

- **WebSocket** for agent ↔ relay (works everywhere)
- **TCP/UDP** for agent ↔ agent (performance)
- **HTTP/HTTPS** as fallback (when TCP is blocked)

Agents try multiple transports until one works. Simple, pragmatic, effective.

### Connection Flow
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

## Protocol Messages

### Public Discovery Messages

#### ANNOUNCE Message
Purpose: Public broadcast of agent existence, capabilities, network endpoints, and liveness.

**Data Structure:**
```json
{
  "type": "ANNOUNCE",
  "pubkey": "<sender's public key>",
  "timestamp": "<unix timestamp>",
  "sequence": "<incrementing counter>",
  
  // Network Endpoints (for connectivity)
  "endpoints": [
    "tcp://73.42.18.9:8001",      // Public IP address
    "tcp://192.168.1.100:8001",   // Local LAN IP  
    "relay://abc123.connectonion.io"  // Relay lookup (returns current IP)
  ],
  "nat_type": "none" | "full_cone" | "restricted" | "symmetric",
  
  // Capabilities
  "prompt_summary": "<system prompt description>",
  "tools": ["<list of available tools>"],
  
  // Liveness
  "uptime": "<seconds since start>",
  "last_activity": {
    "type": "<tool_call | task_complete>",
    "timestamp": "<when>",
    "tool": "<which tool if applicable>"
  },
  
  // Status
  "status": "active" | "idle" | "busy",
  "load": "<0.0 to 1.0>",
  
  // Metadata
  "version": "<agent version>",
  "model": "<LLM model used>",
  "state_hash": "<hash for change detection>"
}
```

**Characteristics:**
- Unencrypted for transparency
- Single-hop forwarding maximum
- Sent on developer trigger (startup, task completion, changes, IP address change)

#### FIND Message
Purpose: Query network for specific capabilities.

**Data Structure:**
```json
{
  "type": "FIND",
  "pubkey": "<requester's public key>",
  "query_id": "<unique query identifier>",
  "capability": "<natural language description>",
  "ttl": "<hop counter, typically 3-4>",
  "timestamp": "<unix timestamp>"
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
```json
{
  "type": "TASK",
  "from": "<sender pubkey>",
  "to": "<recipient pubkey>",
  
  // Correlation
  "task_id": "<unique task identifier>",
  "thread_id": "<optional conversation context>",
  
  // Payload
  "task_type": "request" | "response" | "error",
  "encrypted_payload": "<encrypted with recipient's public key>",
  
  // Metadata
  "timestamp": "<when sent>",
  "ttl": "<message expiry>",
  "priority": "high" | "normal" | "low",
  
  // Security
  "signature": "<sign(all above fields)>"
}
```

**Why Message-Based:**
- **Parallel by Design**: Each task has unique ID, enabling concurrent operations
- **Stateless**: No session management, agents can restart without losing work
- **NAT-Friendly**: Works through relays without persistent connections
- **Simple Mental Model**: Like email with threading and signatures
- **Resilient**: Messages can be queued, retried, and delivered asynchronously

## Network Topology

### Agent Nodes
Standard participants in the network. Each agent maintains connections to other agents, divided into:
- **Contacts**: Agents with established collaborative history
- **Strangers**: Agents discovered but not yet verified

### Data Storage

#### Contact Records
Information about agents with established collaboration:

```json
{
  "pubkey": "<public key>",
  
  // Network information
  "endpoints": ["<known connection methods>"],
  "last_seen": "<timestamp>",
  
  // Collaboration history
  "successful_tasks": "<count>",
  "failed_tasks": "<count>",
  "last_collaboration": "<timestamp>",
  
  // Performance metrics
  "avg_response_time": "<milliseconds>",
  "reliability_score": "<0.0 to 1.0>"
}
```

Storage: Persistent, limited to ~150 entries (Dunbar's number)

#### Stranger Cache
Temporary information about discovered agents:

```json
{
  "pubkey": "<public key>",
  
  // Discovery information
  "discovered_via": "<which contact>",
  "first_heard": "<timestamp>",
  "last_heard": "<timestamp>",
  
  // Claimed capabilities (unverified)
  "prompt_summary": "<their claim>",
  "tools": ["<claimed tools>"]
}
```

Storage: Ephemeral, maximum 500 entries, auto-expire after 1 hour

#### Path Cache
Routing information for message delivery:

```json
{
  "target_pubkey": "<destination>",
  "next_hop": "<immediate neighbor to route through>",
  "confidence": "<0.0 to 1.0>",
  "expires_at": "<timestamp>"
}
```

Storage: Memory only, 5-15 minute TTL

#### Endpoint Claims
Self-signed assertions about how to connect:

```json
{
  "pubkey": "<claiming agent>",
  "transport": "tcp" | "udp" | "websocket" | "bluetooth",
  "endpoint": "<connection string>",
  "issued_at": "<timestamp>",
  "expires_at": "<timestamp>",
  "signature": "<signed by claiming agent>"
}
```

Validation: Must be signed by claimed pubkey, must not be expired

## The Simplicity Principle

Throughout this journey, we kept returning to one principle: **keep simple things simple, make complicated things possible**.

Our final protocol reflects this:

- **Simple**: Agents announce themselves, find others, exchange messages
- **Possible**: Scale to billions, work through NAT, maintain privacy

## Key Design Decisions

### 1. ANNOUNCE = Heartbeat = Discovery
We started with separate HEARTBEAT and ANNOUNCE messages. Then realized: they're the same thing. One message type, multiple purposes.

### 2. Behavioral Trust Over Cryptographic Trust
We don't verify identities. We verify behavior. If an agent successfully completes tasks, it becomes a "contact". Trust through proven work, not certificates.

### 3. Developer-Controlled Broadcasting
Agents only announce when developers explicitly call `announce()`. No hidden network activity, no automatic broadcasts. Developers stay in control.

### 4. No Global State
Each agent only knows its local neighborhood. No global directory, no consensus required. The network scales infinitely because there's nothing global to coordinate.

## Message Forwarding

### Single-Hop Rule
ANNOUNCE messages forward at most one hop. This prevents exponential flooding while allowing immediate neighbors to learn about second-degree connections.

### TTL-Based Propagation
FIND messages propagate based on TTL, decremented at each hop. This allows controlled network-wide search.

### Selective Forwarding
Agents forward messages based on:
- Sender relationship (contact vs stranger)
- Message relevance
- Local rate limits
- Change significance (for ANNOUNCEs)

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
- ANNOUNCE: Maximum 1 per minute
- FIND: Maximum 10 per minute
- Forward budget: 100 messages per minute

### Natural Throttling
- Activity-based announcements (not periodic)
- Single-hop forwarding
- TTL limits
- Selective forwarding

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
- Message size: ANNOUNCE ~1KB, FIND ~200 bytes
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

## What We Didn't Build (And Why)

- **Blockchain**: Adds complexity without solving our actual problems
- **Consensus protocols**: We don't need global agreement
- **Complex PKI**: Public keys are just addresses, not identities
- **Persistent connections**: Messages are better for async work
- **Reputation systems**: Local behavioral tracking is sufficient

## The Result: Boring Technology That Works

Our final protocol is almost boring in its simplicity:

1. Agents announce their capabilities and IP addresses
2. Other agents discover them through broadcasts or queries
3. Agents exchange messages directly (or via relay if needed)
4. Trust builds through successful collaboration

No magic. No breakthrough cryptography. Just proven patterns assembled thoughtfully.

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

## Lessons Learned

1. **Start with the user experience, work backwards to the protocol**
2. **Question every assumption** - Do we really need sessions? Identity? Consensus?
3. **Embrace "boring" solutions** - They're boring because they work
4. **Separate concerns** - Public discovery vs private work
5. **Design for the common case** - Direct connections when possible, relays when necessary

## Looking Forward

The protocol will evolve, but the principles remain:

- Keep it simple
- Make it work
- Don't add complexity without clear benefit
- Trust through behavior, not cryptography
- Developer control over network activity

We chose message-based architecture not because it's trendy, but because it matches how AI agents actually work: parallel, asynchronous, resilient.

We chose public keys as addresses not because we love cryptography, but because they're unforgeable unique identifiers that require no central authority.

We chose simplicity not because we couldn't build something complex, but because we learned that simple systems are the ones that survive and scale.

## The ConnectOnion Way

Our network protocol embodies the ConnectOnion philosophy:

- **Simple by default** - Basic operations are trivial
- **Powerful when needed** - Complex scenarios are possible  
- **Transparent where it matters** - Public discovery for auditing
- **Private where it counts** - Encrypted work for confidentiality
- **Decentralized but practical** - P2P with optional infrastructure

The best protocol isn't the most sophisticated - it's the one that gets out of the way and lets agents do their work.

---

*The ConnectOnion network protocol is open source and available at [github.com/connectonion/connectonion](https://github.com/connectonion/connectonion). We welcome contributions and feedback as we continue to refine and improve the protocol.*