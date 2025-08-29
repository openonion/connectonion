'use client'

import { CopyPromptButton } from '../../components/CopyPromptButton'
import CodeWithResult from '../../components/CodeWithResult'
import { Shield, Users, Code, Zap, CheckCircle, TrendingUp, AlertCircle, BookOpen } from 'lucide-react'
import Link from 'next/link'


export default function TrustPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Hero Section */}
      <div className="relative overflow-hidden bg-gradient-to-b from-purple-900/20 to-gray-950">
        <div className="absolute inset-0 bg-grid-white/[0.02] bg-[size:32px_32px]" />
        <div className="relative max-w-6xl mx-auto px-8 py-16">
          <div className="flex items-start justify-between gap-8">
            <div>
              <div className="text-sm text-purple-400 font-medium mb-3">Core Feature</div>
              <h1 className="text-4xl lg:text-5xl font-bold mb-4 bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
                Trust in ConnectOnion
              </h1>
              <p className="text-xl text-gray-300 max-w-3xl">
                Flexible, bidirectional trust configuration for agent interactions
              </p>
            </div>
            <CopyPromptButton />
          </div>

          {/* Why Trust Blog Link */}
          <Link 
            href="/blog/trust-keyword"
            className="inline-flex items-center gap-2 mt-6 px-4 py-2 bg-purple-900/30 border border-purple-800 rounded-lg hover:bg-purple-900/50 transition-colors group"
          >
            <BookOpen className="w-4 h-4 text-purple-400" />
            <span className="text-sm text-purple-300">Read: Why we chose "trust" as our keyword</span>
            <span className="text-purple-400 group-hover:translate-x-1 transition-transform">→</span>
          </Link>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-6xl mx-auto px-8 py-12">
        <div className="grid lg:grid-cols-3 gap-8">
          {/* Quick Start */}
          <div className="lg:col-span-2 space-y-8">
            <section>
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <Zap className="w-6 h-6 text-yellow-400" />
                Quick Start
              </h2>
              <CodeWithResult
                code={`from connectonion import Agent, need

# Simple trust levels
translator = need("translate", trust="strict")   # Production: verified only
analyzer = need("analyze", trust="tested")       # Default: test first
scraper = need("scrape", trust="open")          # Development: trust all

# For your own agent
agent = Agent(
    name="my_service",
    tools=[process_data],
    trust="strict"  # Who can use my services
)`}
                fileName="trust_config.py"
                result={`>>> translator = need("translate", trust="strict")
>>> print(translator)
<Agent: translate (strict trust)>

>>> agent = Agent(name="my_service", tools=[process_data], trust="strict")
>>> print(f"Agent {agent.name} configured with strict trust policy")`}
              />
            </section>

            {/* Three Forms */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <Code className="w-6 h-6 text-blue-400" />
                Three Forms of Trust
              </h2>
              <div className="space-y-4">
                {/* Trust Levels */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                    <span className="text-purple-400">1.</span> Trust Levels (String)
                  </h3>
                  <p className="text-gray-400 mb-4">Simple predefined levels for common scenarios:</p>
                  <div className="space-y-2">
                    <div className="flex items-center gap-3 p-3 bg-gray-800/50 rounded">
                      <span className="font-mono text-green-400">open</span>
                      <span className="text-gray-400">→</span>
                      <span className="text-gray-300">Trust everyone (development)</span>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-gray-800/50 rounded">
                      <span className="font-mono text-yellow-400">tested</span>
                      <span className="text-gray-400">→</span>
                      <span className="text-gray-300">Test before trusting (default)</span>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-gray-800/50 rounded">
                      <span className="font-mono text-red-400">strict</span>
                      <span className="text-gray-400">→</span>
                      <span className="text-gray-300">Only verified/whitelisted (production)</span>
                    </div>
                  </div>
                </div>

                {/* Trust Policy */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                    <span className="text-purple-400">2.</span> Trust Policy (Natural Language)
                  </h3>
                  <p className="text-gray-400 mb-4">Express complex requirements in plain English:</p>
                  <CodeWithResult
                    code={`trust = """
I trust agents that:
- Pass capability tests
- Respond within 500ms
- Are on my whitelist OR from local network
"""

translator = need("translate", trust=trust)`}
                    fileName="natural_language_trust.py"
                    className="mt-4"
                  />
                </div>

                {/* Trust Agent */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                    <span className="text-purple-400">3.</span> Trust Agent
                  </h3>
                  <p className="text-gray-400 mb-4">For maximum control, use a custom trust agent with verification tools</p>
                  <CodeWithResult
                    code={`trust_agent = Agent(
    name="my_guardian",
    tools=[check_whitelist, verify_capability],
    system_prompt="You verify other agents before allowing interaction."
)

# Use it for your services
my_agent = Agent(
    name="my_service",
    tools=[process_payment],
    trust=trust_agent  # Guardian protects your agent
)`}
                    fileName="trust_agent.py"
                    className="mt-4"
                  />
                </div>
              </div>
            </section>

            {/* Bidirectional Trust */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <Users className="w-6 h-6 text-green-400" />
                Bidirectional Trust
              </h2>
              <div className="bg-gradient-to-br from-purple-900/20 to-pink-900/20 border border-purple-800 rounded-lg p-6">
                <p className="text-gray-300 mb-4">
                  The same <span className="font-mono bg-purple-900/50 px-1.5 py-0.5 rounded">trust</span> parameter 
                  works in both directions:
                </p>
                
                <CodeWithResult
                  code={`from connectonion import Agent, need, share

# Alice creates a translation service
alice = Agent(
    name="alice_translator",
    tools=[translate],
    trust="tested"  # Test users before serving them
)
share(alice)  # Make Alice available to others

# Bob looks for a translator
translator = need(
    "translate to Spanish",
    trust="strict"  # Bob only uses verified services
)

# What happens:
# 1. Bob's trust agent evaluates Alice (strict check)
# 2. Alice's trust agent evaluates Bob (test required)
# 3. Both must approve for connection to succeed`}
                  fileName="bidirectional_trust.py"
                  result={`>>> share(alice)
Agent 'alice_translator' shared on network

>>> translator = need("translate to Spanish", trust="strict")
Evaluating agent: alice_translator
✓ Verified agent credentials
✓ Passed capability test
✓ Response time: 245ms

>>> translator.input("Hello world")
"Hola mundo"`}
                  className="mt-4"
                />
                
                <div className="mt-4 p-3 bg-purple-900/30 border border-purple-700 rounded">
                  <p className="text-sm text-purple-300 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4" />
                    Both trust requirements must be satisfied for interaction!
                  </p>
                </div>
              </div>
            </section>

            {/* Progressive Trust */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <TrendingUp className="w-6 h-6 text-blue-400" />
                Progressive Trust Building
              </h2>
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                <p className="text-gray-300 mb-4">Trust grows through successful interactions:</p>
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-yellow-500/20 flex items-center justify-center">
                      <span className="text-yellow-400 text-sm">1</span>
                    </div>
                    <div>
                      <div className="font-semibold text-white">First Encounter</div>
                      <div className="text-sm text-gray-400">Agent is tested before use</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center">
                      <span className="text-blue-400 text-sm">2</span>
                    </div>
                    <div>
                      <div className="font-semibold text-white">Successful Interactions</div>
                      <div className="text-sm text-gray-400">Agent automatically added to verified list</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center">
                      <span className="text-green-400 text-sm">3</span>
                    </div>
                    <div>
                      <div className="font-semibold text-white">Future Encounters</div>
                      <div className="text-sm text-gray-400">Skip testing, already verified</div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1 space-y-6">
            {/* Environment Defaults */}
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Shield className="w-5 h-5 text-purple-400" />
                Environment Defaults
              </h3>
              <div className="space-y-3 text-sm">
                <div className="flex items-start gap-3">
                  <div className="w-2 h-2 rounded-full bg-green-400 mt-1.5" />
                  <div>
                    <div className="text-white font-medium">Development</div>
                    <div className="text-gray-400">localhost, Jupyter → <code>open</code></div>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="w-2 h-2 rounded-full bg-yellow-400 mt-1.5" />
                  <div>
                    <div className="text-white font-medium">Testing</div>
                    <div className="text-gray-400">test_*.py files → <code>tested</code></div>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="w-2 h-2 rounded-full bg-red-400 mt-1.5" />
                  <div>
                    <div className="text-white font-medium">Production</div>
                    <div className="text-gray-400">Default → <code>strict</code></div>
                  </div>
                </div>
              </div>
            </div>

            {/* Best Practices */}
            <div className="bg-gradient-to-br from-yellow-900/20 to-orange-900/20 border border-yellow-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-yellow-400" />
                Security Best Practices
              </h3>
              <ol className="space-y-2 text-sm">
                <li className="flex items-start gap-2">
                  <span className="text-yellow-400 font-bold">1.</span>
                  <span className="text-gray-300">Always use <code className="text-red-400">strict</code> in production</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-yellow-400 font-bold">2.</span>
                  <span className="text-gray-300">Test sensitive operations</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-yellow-400 font-bold">3.</span>
                  <span className="text-gray-300">Whitelist critical services</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-yellow-400 font-bold">4.</span>
                  <span className="text-gray-300">Monitor trust decisions</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-yellow-400 font-bold">5.</span>
                  <span className="text-gray-300">Regular audits</span>
                </li>
              </ol>
            </div>

            {/* Common Patterns */}
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Common Patterns</h3>
              <div className="space-y-3">
                <div>
                  <div className="text-sm font-medium text-purple-400 mb-1">Mixed Trust</div>
                  <pre className="text-xs text-gray-400 overflow-x-auto">
                    <code>{`scraper = need("scrape", trust="open")
analyzer = need("analyze", trust="tested")
payment = need("payment", trust="strict")`}</code>
                  </pre>
                </div>
              </div>
            </div>

            {/* Related Links */}
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Learn More</h3>
              <div className="space-y-3">
                <Link href="/blog/trust-keyword" className="block text-sm text-purple-400 hover:text-purple-300 transition-colors">
                  → Why we chose "trust"
                </Link>
                <Link href="/examples" className="block text-sm text-purple-400 hover:text-purple-300 transition-colors">
                  → Trust in Examples
                </Link>
                <Link href="/threat-model" className="block text-sm text-purple-400 hover:text-purple-300 transition-colors">
                  → Security Threat Model
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}