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

## Transport Layer: Meet Users Where They Are

We learned that TCP on custom ports gets blocked by corporate firewalls. Our solution:

- **WebSocket** for agent ↔ relay (works everywhere)
- **TCP/UDP** for agent ↔ agent (performance)
- **HTTP/HTTPS** as fallback (when TCP is blocked)

Agents try multiple transports until one works. Simple, pragmatic, effective.

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