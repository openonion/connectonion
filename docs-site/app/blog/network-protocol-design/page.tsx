'use client'

import { useState } from 'react'
import CopyButton from '../../../components/CopyButton'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'
import { ContentNavigation } from '../../../components/ContentNavigation'

export default function NetworkProtocolDesignBlog() {

  const content = `# Designing the ConnectOnion Network Protocol: From Complexity to Clarity

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

The solution? Message-based architecture, like email:`

  const codeExample1 = `# Not this (session-based):
connection = connect_to_agent()
response = connection.call("translate", text)
connection.close()

# But this (message-based):
send_message(agent_pubkey, task_id="abc123", request="translate", text=text)
# ... agent processes asynchronously ...
receive_message(task_id="abc123", response=translated_text)`

  const content2 = `Each message carries its own correlation ID. No sessions to manage. No connection state. Just messages flowing between agents.

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
Agents only announce when developers explicitly call \`announce()\`. No hidden network activity, no automatic broadcasts. Developers stay in control.

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

The best protocol isn't the most sophisticated - it's the one that gets out of the way and lets agents do their work.`

  const fullContent = content + '\n\n```python\n' + codeExample1 + '\n```\n\n' + content2

  return (
    <div className="w-full">
      <main className="p-4 lg:p-8 lg:px-16 pb-20">
          <article className="prose prose-invert max-w-none">
            <div className="mb-8 flex justify-between items-start">
              <div>
                <h1 className="text-4xl lg:text-6xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent mb-4">
                  Designing the ConnectOnion Network Protocol: From Complexity to Clarity
                </h1>
                <p className="text-gray-300 text-lg">December 2024</p>
              </div>
              <CopyMarkdownButton content={fullContent} />
            </div>

            <div className="mt-8 space-y-6 text-gray-200">
              <p className="text-lg leading-relaxed">
                When we set out to design a network protocol for AI agents to collaborate, we started with grand ambitions and complex architectures. Through iterative refinement and hard lessons, we arrived at something much simpler and more powerful. This is the story of how we got there.
              </p>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">The Initial Vision: Too Much, Too Soon</h2>
              <p>We began by studying existing protocols - MCP (Model Context Protocol), gRPC, and various P2P systems. Our first designs were ambitious:</p>
              <ul className="list-disc list-inside space-y-3 ml-4 text-gray-300">
                <li>Complex identity systems with cryptographic proofs</li>
                <li>Multiple message types for every possible scenario</li>
                <li>Sophisticated trust models with reputation scores</li>
                <li>Session-based connections like HTTP/gRPC</li>
              </ul>
              <p>It felt comprehensive. It also felt wrong.</p>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">The First Breakthrough: Public Keys Are Just Addresses</h2>
              <p>The pivotal moment came when we realized we were overthinking identity. Public keys don't need to represent identity or trust - they're just addresses, like phone numbers or IP addresses.</p>
              <p>This insight simplified everything:</p>
              <ul className="list-disc list-inside space-y-3 ml-4 text-gray-300">
                <li>No complex PKI infrastructure needed</li>
                <li>No identity verification protocols</li>
                <li>No certificate authorities</li>
                <li>Just addresses for routing messages</li>
              </ul>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">Messages Over Sessions: Why Email Got It Right</h2>
              <p>We initially assumed we needed session-based connections like HTTP or gRPC. But AI agents don't work like web browsers - they handle hundreds of parallel tasks, each potentially taking minutes or hours to complete.</p>
              <p>The solution? Message-based architecture, like email:</p>
              
              <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-6 my-6 relative group">
                <CopyButton text={codeExample1} />
                <pre className="text-sm overflow-x-auto font-mono">
                  <code className="text-purple-300">{codeExample1}</code>
                </pre>
              </div>

              <p>Each message carries its own correlation ID. No sessions to manage. No connection state. Just messages flowing between agents.</p>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">The Two-Layer Revelation: Transparency AND Privacy</h2>
              <p>Organizations need transparency to audit AI agent behavior. But actual work needs privacy. We struggled with this tension until we realized: separate them into two layers.</p>
              
              <div className="grid md:grid-cols-2 gap-6 my-8">
                <div className="bg-gradient-to-br from-purple-900/20 to-transparent border border-purple-500/20 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-purple-300 mb-4">Public Discovery Layer (ANNOUNCE/FIND)</h3>
                  <ul className="space-y-2">
                    <li>• Unencrypted broadcasts</li>
                    <li>• Shows what agents exist and their capabilities</li>
                    <li>• Organizations can monitor and audit</li>
                    <li>• Like a public phone book</li>
                  </ul>
                </div>
                <div className="bg-gradient-to-br from-pink-900/20 to-transparent border border-pink-500/20 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-pink-300 mb-4">Private Work Layer (TASK)</h3>
                  <ul className="space-y-2">
                    <li>• Encrypted point-to-point messages</li>
                    <li>• Actual work remains confidential</li>
                    <li>• Like private phone calls</li>
                  </ul>
                </div>
              </div>

              <p>This gives organizations the oversight they need without compromising the privacy of actual work.</p>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">Relay Servers: Just a Lookup Service</h2>
              <p>We went through several iterations on relay servers:</p>
              <ol className="list-decimal list-inside space-y-3 ml-4 text-gray-300">
                <li><strong>First design</strong>: Full proxy servers (too centralized)</li>
                <li><strong>Second design</strong>: Complex NAT traversal with STUN/TURN (too complicated)</li>
                <li><strong>Final design</strong>: Simple lookup service</li>
              </ol>
              <p className="mt-4">The relay just stores current IP addresses for public keys. When an agent's IP changes, it updates the relay. When another agent needs to connect, it asks the relay for the current IP, then connects directly.</p>
              <p>No data flows through the relay. It's just a phone book that updates when people move.</p>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">Transport Layer: Meet Users Where They Are</h2>
              <p>We learned that TCP on custom ports gets blocked by corporate firewalls. Our solution:</p>
              <ul className="list-disc list-inside space-y-3 ml-4 text-gray-300">
                <li><strong>WebSocket</strong> for agent ↔ relay (works everywhere)</li>
                <li><strong>TCP/UDP</strong> for agent ↔ agent (performance)</li>
                <li><strong>HTTP/HTTPS</strong> as fallback (when TCP is blocked)</li>
              </ul>
              <p>Agents try multiple transports until one works. Simple, pragmatic, effective.</p>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">The Simplicity Principle</h2>
              <p>Throughout this journey, we kept returning to one principle: <strong>keep simple things simple, make complicated things possible</strong>.</p>
              <p>Our final protocol reflects this:</p>
              <ul className="list-disc list-inside space-y-3 ml-4 text-gray-300">
                <li><strong>Simple</strong>: Agents announce themselves, find others, exchange messages</li>
                <li><strong>Possible</strong>: Scale to billions, work through NAT, maintain privacy</li>
              </ul>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">Key Design Decisions</h2>
              
              <div className="space-y-6">
                <div>
                  <h3 className="text-xl font-semibold text-purple-300 mb-3">1. ANNOUNCE = Heartbeat = Discovery</h3>
                  <p>We started with separate HEARTBEAT and ANNOUNCE messages. Then realized: they're the same thing. One message type, multiple purposes.</p>
                </div>
                
                <div>
                  <h3 className="text-xl font-semibold text-purple-300 mb-3">2. Behavioral Trust Over Cryptographic Trust</h3>
                  <p>We don't verify identities. We verify behavior. If an agent successfully completes tasks, it becomes a "contact". Trust through proven work, not certificates.</p>
                </div>
                
                <div>
                  <h3 className="text-xl font-semibold text-purple-300 mb-3">3. Developer-Controlled Broadcasting</h3>
                  <p>Agents only announce when developers explicitly call <code className="bg-gray-800/50 text-purple-300 px-2 py-1 rounded font-mono text-sm">announce()</code>. No hidden network activity, no automatic broadcasts. Developers stay in control.</p>
                </div>
                
                <div>
                  <h3 className="text-xl font-semibold text-purple-300 mb-3">4. No Global State</h3>
                  <p>Each agent only knows its local neighborhood. No global directory, no consensus required. The network scales infinitely because there's nothing global to coordinate.</p>
                </div>
              </div>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">What We Didn't Build (And Why)</h2>
              <ul className="list-disc list-inside space-y-3 ml-4 text-gray-300">
                <li><strong>Blockchain</strong>: Adds complexity without solving our actual problems</li>
                <li><strong>Consensus protocols</strong>: We don't need global agreement</li>
                <li><strong>Complex PKI</strong>: Public keys are just addresses, not identities</li>
                <li><strong>Persistent connections</strong>: Messages are better for async work</li>
                <li><strong>Reputation systems</strong>: Local behavioral tracking is sufficient</li>
              </ul>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">The Result: Boring Technology That Works</h2>
              <p>Our final protocol is almost boring in its simplicity:</p>
              <ol className="list-decimal list-inside space-y-3 ml-4 text-gray-300">
                <li>Agents announce their capabilities and IP addresses</li>
                <li>Other agents discover them through broadcasts or queries</li>
                <li>Agents exchange messages directly (or via relay if needed)</li>
                <li>Trust builds through successful collaboration</li>
              </ol>
              <p className="mt-4">No magic. No breakthrough cryptography. Just proven patterns assembled thoughtfully.</p>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">Lessons Learned</h2>
              <ol className="list-decimal list-inside space-y-3 ml-4 text-gray-300">
                <li><strong>Start with the user experience, work backwards to the protocol</strong></li>
                <li><strong>Question every assumption</strong> - Do we really need sessions? Identity? Consensus?</li>
                <li><strong>Embrace "boring" solutions</strong> - They're boring because they work</li>
                <li><strong>Separate concerns</strong> - Public discovery vs private work</li>
                <li><strong>Design for the common case</strong> - Direct connections when possible, relays when necessary</li>
              </ol>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">Looking Forward</h2>
              <p>The protocol will evolve, but the principles remain:</p>
              <ul className="list-disc list-inside space-y-3 ml-4 text-gray-300">
                <li>Keep it simple</li>
                <li>Make it work</li>
                <li>Don't add complexity without clear benefit</li>
                <li>Trust through behavior, not cryptography</li>
                <li>Developer control over network activity</li>
              </ul>
              
              <div className="bg-gradient-to-r from-purple-900/20 to-pink-900/20 border-l-4 border-purple-400 p-6 rounded-r-lg my-8">
                <p className="mb-4 font-medium text-purple-200">We chose message-based architecture not because it's trendy, but because it matches how AI agents actually work: parallel, asynchronous, resilient.</p>
                
                <p className="mb-4 font-medium text-purple-200">We chose public keys as addresses not because we love cryptography, but because they're unforgeable unique identifiers that require no central authority.</p>
                
                <p className="font-medium text-purple-200">We chose simplicity not because we couldn't build something complex, but because we learned that simple systems are the ones that survive and scale.</p>
              </div>

              <h2 className="text-3xl font-bold text-purple-400 mt-12 mb-6 pb-2 border-b border-gray-800">The ConnectOnion Way</h2>
              <p>Our network protocol embodies the ConnectOnion philosophy:</p>
              <ul className="list-disc list-inside space-y-3 ml-4 text-gray-300">
                <li><strong>Simple by default</strong> - Basic operations are trivial</li>
                <li><strong>Powerful when needed</strong> - Complex scenarios are possible</li>
                <li><strong>Transparent where it matters</strong> - Public discovery for auditing</li>
                <li><strong>Private where it counts</strong> - Encrypted work for confidentiality</li>
                <li><strong>Decentralized but practical</strong> - P2P with optional infrastructure</li>
              </ul>
              
              <p className="mt-6">The best protocol isn't the most sophisticated - it's the one that gets out of the way and lets agents do their work.</p>

              <div className="border-t border-gray-800 mt-16 pt-8">
                <div className="bg-gradient-to-r from-purple-900/10 to-pink-900/10 border border-purple-500/20 rounded-lg p-6 mb-6">
                  <h3 className="text-lg font-bold text-purple-300 mb-3">📖 Complete Technical Specification</h3>
                  <p className="text-gray-300 mb-3">
                    This article covers the design philosophy and evolution of our network protocol. For the complete technical specification including message formats, data structures, and implementation details, see:
                  </p>
                  <a href="https://github.com/connectonion/connectonion/blob/main/docs/design-decisions/004-designing-agent-network-protocol.md" 
                     className="inline-flex items-center gap-2 text-purple-400 hover:text-purple-300 font-medium transition-colors">
                    <span>Full Network Protocol Documentation</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>
                <p className="text-sm text-gray-400 italic">
                  The ConnectOnion network protocol is open source and available at{' '}
                  <a href="https://github.com/wu-changxing/connectonion" className="text-purple-400 hover:text-purple-300 hover:underline transition-colors">
                    github.com/wu-changxing/connectonion
                  </a>. 
                  We welcome contributions and feedback as we continue to refine and improve the protocol.
                </p>
              </div>
              
              {/* Navigation */}
              <ContentNavigation />
            </div>
          </article>
        </main>
      </div>
  )
}