import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export default function AgentAddressFormatPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <Link href="/blog" className="inline-flex items-center gap-2 text-purple-400 hover:text-purple-300 mb-8 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to Blog
      </Link>
      
      <article className="prose prose-invert max-w-none">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent mb-4">
          Why We Choose Hex-Encoded Ed25519 Over Ethereum Addresses
        </h1>
        
        <div className="text-gray-400 mb-8">
          <time>September 3, 2025</time> • Design Decision
        </div>
        
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6 mb-8">
          <p className="text-lg text-gray-300 leading-relaxed m-0">
            When designing agent network identities, we chose hex-encoded Ed25519 public keys with a 0x prefix. 
            Familiar to developers, fast for agents, and honest about what it represents.
          </p>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-12 mb-4">The Address Format Dilemma</h2>
        
        <p className="text-gray-300 leading-relaxed">
          Every network needs addresses. TCP/IP has IP addresses. Ethereum has wallet addresses. 
          ConnectOnion agents need their own addressing scheme. The question: what format serves both humans and machines?
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Why Not Ethereum Format?</h2>
        
        <p className="text-gray-300 leading-relaxed mb-4">
          Ethereum addresses (20 bytes, checksummed) are familiar to crypto developers. But using them creates confusion:
        </p>
        
        <ul className="space-y-2 text-gray-300">
          <li>• Users expect Ethereum compatibility that doesn't exist</li>
          <li>• 20 bytes loses security compared to full 32-byte keys</li>
          <li>• Checksumming adds complexity without real benefit for agents</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Why Not Base58 (Bitcoin/Solana)?</h2>
        
        <p className="text-gray-300 leading-relaxed mb-4">
          Base58 is human-friendly - no confusing characters like 0/O or l/1. But:
        </p>
        
        <ul className="space-y-2 text-gray-300">
          <li>• Requires base conversion (computational overhead)</li>
          <li>• Variable length complicates parsing</li>
          <li>• Not native to any programming language</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Why Ed25519?</h2>
        
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <h3 className="text-lg font-semibold text-purple-400 mb-3">Performance</h3>
          <p className="text-gray-300">
            Ed25519: ~70,000 signatures/second<br/>
            Secp256k1: ~20,000 signatures/second<br/>
            <span className="text-green-400">3.5x faster for agent communications</span>
          </p>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <h3 className="text-lg font-semibold text-purple-400 mb-3">Security</h3>
          <p className="text-gray-300">
            • Deterministic signatures (same input → same signature)<br/>
            • Resistant to timing attacks<br/>
            • No random number generator vulnerabilities
          </p>
        </div>

        <div className="bg-gray-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-purple-400 mb-3">Simplicity</h3>
          <p className="text-gray-300">
            • Fixed 32-byte keys and 64-byte signatures<br/>
            • Simple, clean API<br/>
            • Battle-tested in SSH, Signal, and more
          </p>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Our Format: Honest and Fast</h2>
        
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-4 font-mono text-sm mb-6">
          <span className="text-purple-400">0x</span><span className="text-gray-300">2b9def...7a3fdf</span>
        </div>
        
        <p className="text-gray-300 leading-relaxed mb-4">
          • <strong className="text-white">0x prefix:</strong> Signals "this is cryptographic material"<br/>
          • <strong className="text-white">64 hex chars:</strong> The full Ed25519 public key<br/>
          • <strong className="text-white">66 total chars:</strong> Fixed length, easy to validate
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Developer Experience</h2>
        
        <div className="bg-gray-800 rounded-lg p-4 font-mono text-sm mb-6">
          <span className="text-gray-500"># Generate</span><br/>
          <span className="text-purple-400">address</span> = <span className="text-green-400">"0x"</span> + public_key.hex()<br/>
          <br/>
          <span className="text-gray-500"># Validate</span><br/>
          <span className="text-blue-400">if</span> address.startswith(<span className="text-green-400">"0x"</span>) <span className="text-blue-400">and</span> len(address) == <span className="text-orange-400">66</span>:<br/>
          &nbsp;&nbsp;public_key = bytes.fromhex(address[<span className="text-orange-400">2</span>:])
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          No special libraries. No base conversions. No checksums. Just hex encoding that every language supports natively.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Visual Truncation</h2>
        
        <p className="text-gray-300 leading-relaxed mb-4">
          For display, we show: <code className="bg-gray-800 px-2 py-1 rounded">0x2b9d...3fdf</code>
        </p>
        
        <p className="text-gray-300 leading-relaxed">
          First 6 chars + last 4 chars = enough visual distinction for humans while keeping displays clean.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">The Philosophy</h2>
        
        <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg p-6 border border-purple-500/20">
          <p className="text-lg text-gray-300 leading-relaxed m-0">
            Don't pretend to be something you're not. Our addresses aren't Ethereum addresses. 
            They're not Bitcoin addresses. They're ConnectOnion agent addresses - 
            hex-encoded Ed25519 public keys, fast for agents and familiar to developers.
          </p>
        </div>
      </article>
    </div>
  )
}