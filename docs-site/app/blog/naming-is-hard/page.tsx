import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export default function NamingIsHardPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <Link href="/blog" className="inline-flex items-center gap-2 text-purple-400 hover:text-purple-300 mb-8 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to Blog
      </Link>
      
      <article className="prose prose-invert max-w-none">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent mb-4">
          Why We Call It "Address" Instead of "Identity"
        </h1>
        
        <div className="text-gray-400 mb-8">
          <time>September 3, 2025</time> • Design Decision
        </div>
        
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6 mb-8">
          <p className="text-lg text-gray-300 leading-relaxed m-0">
            Naming is hard. We spent days debating whether to call it an "address" or "identity". 
            The answer came from asking: what mental model serves developers best?
          </p>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-12 mb-4">The Identity Trap</h2>
        
        <p className="text-gray-300 leading-relaxed mb-4">
          "Identity" sounds sophisticated. It implies persistence, uniqueness, authenticity. But it also carries baggage:
        </p>
        
        <ul className="space-y-2 text-gray-300 mb-6">
          <li>• Identity suggests claims about who or what something is</li>
          <li>• Identity systems usually involve trust, verification, attestation</li>
          <li>• Identity feels permanent and heavy</li>
        </ul>
        
        <p className="text-gray-300 leading-relaxed">
          When a developer sees "identity", they expect complexity: identity providers, OIDC flows, 
          JWT tokens, claims, scopes. They expect bureaucracy.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">The Beauty of "Address"</h2>
        
        <p className="text-gray-300 leading-relaxed mb-4">
          Everyone understands addresses. Your house has one. Your email has one. Your server has one. 
          An address is simply <strong className="text-white">where to find something</strong>.
        </p>
        
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <h3 className="text-lg font-semibold text-purple-400 mb-3">Addresses are:</h3>
          <ul className="space-y-2 text-gray-300">
            <li>• <strong className="text-white">Functional:</strong> They route messages</li>
            <li>• <strong className="text-white">Simple:</strong> Just a string that points somewhere</li>
            <li>• <strong className="text-white">Temporary:</strong> Can be changed or discarded</li>
            <li>• <strong className="text-white">Neutral:</strong> No claims about identity or trust</li>
          </ul>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">The Mental Model Test</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
            <h3 className="text-red-400 font-semibold mb-2">❌ With "Identity"</h3>
            <p className="text-gray-400 text-sm">
              "Generate an identity for the agent"<br/>
              "Verify the agent's identity"<br/>
              "The agent's identity is..."
            </p>
            <p className="text-gray-500 text-xs mt-2">Feels heavy, permanent, complex</p>
          </div>
          
          <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
            <h3 className="text-green-400 font-semibold mb-2">✅ With "Address"</h3>
            <p className="text-gray-400 text-sm">
              "Generate an address for the agent"<br/>
              "Send message to this address"<br/>
              "The agent's address is..."
            </p>
            <p className="text-gray-500 text-xs mt-2">Feels simple, functional, clear</p>
          </div>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Prior Art Supports "Address"</h2>
        
        <div className="space-y-4 mb-8">
          <div className="bg-gray-800 rounded-lg p-4">
            <strong className="text-purple-400">Ethereum:</strong>
            <span className="text-gray-300 ml-2">Wallet address (not wallet identity)</span>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <strong className="text-purple-400">Bitcoin:</strong>
            <span className="text-gray-300 ml-2">Bitcoin address (not Bitcoin identity)</span>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <strong className="text-purple-400">TCP/IP:</strong>
            <span className="text-gray-300 ml-2">IP address (not computer identity)</span>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <strong className="text-purple-400">Email:</strong>
            <span className="text-gray-300 ml-2">Email address (not email identity)</span>
          </div>
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          The pattern is clear: networks use addresses for routing, not identities for authentication.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">The Code Tells the Truth</h2>
        
        <div className="bg-gray-800 rounded-lg p-4 font-mono text-sm mb-6">
          <span className="text-gray-500"># What we generate</span><br/>
          address = <span className="text-green-400">"0x"</span> + public_key.hex()<br/>
          <br/>
          <span className="text-gray-500"># What it does</span><br/>
          send_message(to=<span className="text-purple-400">address</span>, content=data)<br/>
          <br/>
          <span className="text-gray-500"># What it doesn't do</span><br/>
          <span className="text-red-400 line-through"># verify_identity(address)</span><br/>
          <span className="text-red-400 line-through"># get_claims(address)</span><br/>
          <span className="text-red-400 line-through"># trust_score(address)</span>
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          It's just a public key. It routes messages. It doesn't make claims. 
          That's an address, not an identity.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">When We Almost Used "Identity"</h2>
        
        <p className="text-gray-300 leading-relaxed mb-4">
          For 48 hours, our code used <code className="bg-gray-800 px-2 py-1 rounded">agent_identity</code>. 
          Then a user asked:
        </p>
        
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 mb-6">
          <p className="text-yellow-300 italic">
            "For people not familiar with agent development, it will be confusing what is address"
          </p>
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          They were right, but backwards. People unfamiliar with crypto understand "address" perfectly. 
          It's "identity" that confuses them. Everyone has mailed a letter. Not everyone has contemplated 
          digital identity systems.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">The Final Decision</h2>
        
        <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg p-6 border border-purple-500/20">
          <p className="text-lg text-gray-300 leading-relaxed mb-4">
            We call it an <strong className="text-white">address</strong> because that's what it is: 
            a way to reach an agent. Nothing more, nothing less.
          </p>
          <p className="text-gray-400">
            If we add identity features later (reputation, attestations, trust scores), those will be 
            separate layers built on top of addresses. The address just gets you there. 
            What you find when you arrive is a different question.
          </p>
        </div>
      </article>
    </div>
  )
}