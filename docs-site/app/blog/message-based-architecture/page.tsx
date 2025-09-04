import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export default function MessageBasedArchitecturePage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <Link href="/blog" className="inline-flex items-center gap-2 text-purple-400 hover:text-purple-300 mb-8 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to Blog
      </Link>
      
      <article className="prose prose-invert max-w-none">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent mb-4">
          Why We Choose Message-Based Architecture Over Session-Based Protocols
        </h1>
        
        <div className="text-gray-400 mb-8">
          <time>September 4, 2025</time> • Architecture Decision
        </div>
        
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6 mb-8">
          <p className="text-lg text-gray-300 leading-relaxed m-0">
            AI agents don't fit the client-server model. They handle parallel tasks, restart anytime, 
            and work behind NAT. Message-based architecture, like email, solves all these problems elegantly.
          </p>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-12 mb-4">The Problem with Sessions</h2>
        
        <p className="text-gray-300 leading-relaxed mb-4">
          Session-based protocols (HTTP, gRPC, WebSockets) were designed for client-server interactions where:
        </p>
        
        <ul className="space-y-2 text-gray-300 mb-6">
          <li>• Order matters</li>
          <li>• State is maintained</li>
          <li>• Connections are persistent</li>
          <li>• Operations are sequential</li>
        </ul>
        
        <p className="text-gray-300 leading-relaxed">
          AI agents don't fit this model. They naturally handle multiple tasks in parallel, 
          may restart at any time, and often can't maintain direct connections due to NAT.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Why Message-Based Wins</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div className="bg-gray-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-purple-400 mb-3">Natural Parallelism</h3>
            <p className="text-gray-300 text-sm">
              Each task gets a unique ID. Agents can handle hundreds of concurrent tasks 
              without managing session state or connection pools.
            </p>
          </div>
          
          <div className="bg-gray-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-purple-400 mb-3">Resilience By Default</h3>
            <p className="text-gray-300 text-sm">
              Messages don't require persistent connections. If an agent crashes, messages queue. 
              If the network fails, messages retry.
            </p>
          </div>
          
          <div className="bg-gray-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-purple-400 mb-3">NAT Traversal Simplicity</h3>
            <p className="text-gray-300 text-sm">
              Messages route through relays without complex hole-punching. 
              The sender doesn't need to know if the recipient is behind NAT.
            </p>
          </div>
          
          <div className="bg-gray-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-purple-400 mb-3">50-Year Proven Model</h3>
            <p className="text-gray-300 text-sm">
              Email has survived because message-based architecture is fundamentally correct 
              for asynchronous, distributed communication.
            </p>
          </div>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Our Message Format</h2>
        
        <div className="bg-gray-800 rounded-lg p-4 font-mono text-sm mb-6">
          {`{
  type: "TASK",
  from: <sender_pubkey>,
  to: <recipient_pubkey>,
  
  // Correlation
  task_id: <unique_task_identifier>,
  thread_id: <optional_conversation_context>,
  
  // Payload
  task_type: "request" | "response" | "error",
  encrypted_payload: <encrypted_with_recipient_key>,
  
  // Metadata
  timestamp: <when_sent>,
  ttl: <message_expiry>,
  priority: "high" | "normal" | "low",
  
  // Security
  signature: <sign(all_above_fields)>
}`}
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">The Unix Philosophy Applied</h2>
        
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6 mb-6">
          <p className="text-gray-300 leading-relaxed">
            Like Unix pipes, each agent is a filter that processes messages. 
            Composition is natural, parallelism is free, and the mental model is simple. 
            No complex state machines, no session management, just messages with IDs.
          </p>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Real-World Comparison</h2>
        
        <div className="space-y-4 mb-8">
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
            <h3 className="text-red-400 font-semibold mb-2">❌ Session-Based (HTTP/WebSocket)</h3>
            <div className="font-mono text-sm text-gray-400">
              <div>1. Open connection</div>
              <div>2. Authenticate</div>
              <div>3. Send request</div>
              <div>4. Wait for response</div>
              <div>5. Handle disconnection</div>
              <div>6. Reconnect</div>
              <div>7. Re-authenticate</div>
              <div>8. Restore state...</div>
            </div>
            <p className="text-gray-500 text-xs mt-2">Complex, stateful, fragile</p>
          </div>
          
          <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
            <h3 className="text-green-400 font-semibold mb-2">✅ Message-Based (Our Approach)</h3>
            <div className="font-mono text-sm text-gray-400">
              <div>1. Send message with task_id</div>
              <div>2. Continue with other work</div>
              <div>3. Receive response when ready</div>
            </div>
            <p className="text-gray-500 text-xs mt-2">Simple, stateless, resilient</p>
          </div>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Handling Parallel Tasks</h2>
        
        <div className="bg-gray-800 rounded-lg p-4 font-mono text-sm mb-6">
          <span className="text-gray-500"># Agent can handle many tasks simultaneously</span><br/>
          tasks = {`{
  "task_001": processing_weather(),
  "task_002": analyzing_document(),
  "task_003": searching_web(),
  "task_004": generating_report()
}`}<br/><br/>
          <span className="text-gray-500"># Each completes independently</span><br/>
          <span className="text-blue-400">async for</span> result <span className="text-blue-400">in</span> task_results:<br/>
          &nbsp;&nbsp;send_response(task_id=result.id, data=result.data)
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          No session juggling. No connection pools. Just messages flowing independently.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">NAT and Firewall Traversal</h2>
        
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <p className="text-gray-300 mb-4">With sessions, NAT is a nightmare:</p>
          <ul className="space-y-2 text-gray-400 text-sm">
            <li>• Need STUN/TURN servers</li>
            <li>• Complex hole-punching</li>
            <li>• Persistent connection maintenance</li>
            <li>• Frequent reconnection logic</li>
          </ul>
          
          <p className="text-gray-300 mt-4 mb-4">With messages, it just works:</p>
          <ul className="space-y-2 text-green-400 text-sm">
            <li>• Messages route through relays</li>
            <li>• No persistent connections needed</li>
            <li>• Works through any firewall</li>
            <li>• Natural queuing and retry</li>
          </ul>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">The Email Analogy</h2>
        
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6 mb-6">
          <p className="text-gray-300 leading-relaxed mb-4">
            Email has survived 50 years because it got the fundamentals right:
          </p>
          <ul className="space-y-2 text-gray-300">
            <li>• <strong className="text-white">Asynchronous:</strong> Send and forget</li>
            <li>• <strong className="text-white">Resilient:</strong> Retries and queuing built-in</li>
            <li>• <strong className="text-white">Stateless:</strong> Each message is self-contained</li>
            <li>• <strong className="text-white">Simple:</strong> Anyone can understand the model</li>
          </ul>
          <p className="text-gray-400 text-sm mt-4">
            AI agents have the same requirements. Why reinvent what works?
          </p>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Two-Layer Separation</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div className="bg-gray-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-purple-400 mb-3">Public Discovery Layer</h3>
            <p className="text-gray-300 text-sm mb-2">
              ANNOUNCE and FIND messages are unencrypted broadcasts for transparency.
            </p>
            <p className="text-gray-400 text-xs">
              Organizations can audit capabilities and network activity.
            </p>
          </div>
          
          <div className="bg-gray-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-purple-400 mb-3">Private Collaboration Layer</h3>
            <p className="text-gray-300 text-sm mb-2">
              TASK messages carry encrypted payloads between agents.
            </p>
            <p className="text-gray-400 text-xs">
              Actual work remains confidential while discovery stays transparent.
            </p>
          </div>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Summary</h2>
        
        <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg p-6 border border-purple-500/20">
          <p className="text-lg text-gray-300 leading-relaxed mb-4">
            The ConnectOnion protocol embraces message-based architecture because it perfectly 
            matches how AI agents actually work: parallel task processing, resilient to failures, 
            and simple to understand.
          </p>
          <p className="text-gray-400">
            With public keys as addresses and messages as the communication primitive, 
            the protocol provides just enough infrastructure for agents to find and collaborate 
            with each other, without the complexity of session management or the overhead 
            of persistent connections.
          </p>
        </div>
      </article>
    </div>
  )
}