'use client'

import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'
import { Shield, Users, Code, Zap, CheckCircle, TrendingUp, AlertCircle, BookOpen } from 'lucide-react'
import Link from 'next/link'

const trustContent = `# Trust in ConnectOnion

The \`trust\` parameter provides flexible, bidirectional trust configuration for agent interactions.

## Quick Start

\`\`\`python
from connectonion import Agent, need

# Simple trust levels
translator = need("translate", trust="strict")   # Production: verified only
analyzer = need("analyze", trust="tested")       # Default: test first
scraper = need("scrape", trust="open")          # Development: trust all

# For your own agent
agent = Agent(
    name="my_service",
    tools=[process_data],
    trust="strict"  # Who can use my services
)
\`\`\`

## Three Forms of Trust

### 1. Trust Levels (String)

Simple predefined levels for common scenarios:

\`\`\`python
# Development - trust everyone
agent = need("service", trust="open")

# Default - test before trusting
agent = need("service", trust="tested")

# Production - only verified/whitelisted
agent = need("service", trust="strict")
\`\`\`

### 2. Trust Policy (Natural Language)

Express complex requirements in plain English:

\`\`\`python
# Inline policy
translator = need("translate", trust="""
    I trust agents that:
    - Pass capability tests
    - Respond within 500ms
    - Are on my whitelist OR from local network
""")

# From file
translator = need("translate", trust="./trust_policy.md")
\`\`\`

### 3. Trust Agent

For maximum control, use a custom trust agent:

\`\`\`python
# Create a trust agent with verification tools
trust_agent = Agent(
    name="my_guardian",
    tools=[
        check_whitelist,
        verify_capability,
        measure_response_time,
        check_reputation
    ],
    system_prompt="""
        You verify other agents before allowing interaction.
        Be strict with payment processors, relaxed with read-only services.
    """
)

# Use it for your agent
my_agent = Agent(
    name="my_service",
    tools=[process_payment],
    trust=trust_agent  # My guardian protects me
)

# And for discovering services
payment = need("payment processor", trust=trust_agent)
\`\`\`

## Bidirectional Trust

The same \`trust\` parameter works in both directions:

\`\`\`python
# As a SERVICE provider (who can use me?)
alice_agent = Agent(
    name="alice_translator",
    tools=[translate],
    trust="tested"  # Users must pass my tests
)

# As a SERVICE consumer (who do I trust?)
translator = need("translate", trust="strict")  # I only use verified services

# Both trust requirements must be satisfied for interaction!
\`\`\`

## Progressive Trust Building

Trust grows through successful interactions:

\`\`\`python
# First encounter - requires testing
translator = need("translate", trust="tested")
# → Agent is tested before use

# After successful interactions
# → Agent automatically added to "verified" list

# Future encounters
translator = need("translate", trust="tested")
# → Skip testing, already verified
\`\`\`

## Environment-Based Defaults

ConnectOnion automatically adjusts trust based on environment:

\`\`\`python
# No trust parameter needed - auto-detected!
translator = need("translate")

# In development (localhost, Jupyter)
# → Defaults to trust="open"

# In test files (test_*.py)
# → Defaults to trust="tested"

# In production
# → Defaults to trust="strict"

# Override when needed
translator = need("translate", trust="open")  # Force open even in production
\`\`\`

## Common Patterns

### Development Mode
\`\`\`python
# Trust everyone for rapid development
connectonion.set_default_trust("open")
\`\`\`

### Production Mode
\`\`\`python
# Strict verification for production
payment = need("payment processor", trust="strict")
sensitive = need("data processor", trust="strict")
\`\`\`

### Mixed Trust
\`\`\`python
# Different trust for different services
scraper = need("web scraper", trust="open")      # Low risk
analyzer = need("analyze data", trust="tested")   # Medium risk
payment = need("process payment", trust="strict") # High risk
\`\`\`

## Security Best Practices

1. **Production = Strict**: Always use \`trust="strict"\` in production
2. **Test Sensitive Operations**: Payment, data modification, etc.
3. **Whitelist Critical Services**: Manually verify and whitelist
4. **Monitor Trust Decisions**: Log all trust evaluations
5. **Regular Audits**: Review whitelist and trust policies`

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
            <CopyMarkdownButton content={trustContent} className="flex-shrink-0" />
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
              <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                <div className="bg-gray-800 px-4 py-2 border-b border-gray-700">
                  <span className="text-xs text-gray-400">Python</span>
                </div>
                <pre className="p-6 overflow-x-auto">
                  <code className="text-sm text-gray-300">{`from connectonion import Agent, need

# Simple trust levels
translator = need("translate", trust="strict")   # Production: verified only
analyzer = need("analyze", trust="tested")       # Default: test first
scraper = need("scrape", trust="open")          # Development: trust all

# For your own agent
agent = Agent(
    name="my_service",
    tools=[process_data],
    trust="strict"  # Who can use my services
)`}</code>
                </pre>
              </div>
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
                  <pre className="p-4 bg-gray-800/50 rounded overflow-x-auto">
                    <code className="text-sm text-gray-300">{`trust = """
I trust agents that:
- Pass capability tests
- Respond within 500ms
- Are on my whitelist OR from local network
"""`}</code>
                  </pre>
                </div>

                {/* Trust Agent */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                    <span className="text-purple-400">3.</span> Trust Agent
                  </h3>
                  <p className="text-gray-400 mb-4">For maximum control, use a custom trust agent with verification tools</p>
                  <pre className="p-4 bg-gray-800/50 rounded overflow-x-auto">
                    <code className="text-sm text-gray-300">{`trust_agent = Agent(
    name="my_guardian",
    tools=[check_whitelist, verify_capability],
    system_prompt="You verify other agents..."
)`}</code>
                  </pre>
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
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-purple-400 mb-2">As Service Provider</h4>
                    <p className="text-sm text-gray-300 mb-2">"Who can use me?"</p>
                    <pre className="text-xs text-gray-400 overflow-x-auto">
                      <code>{`Agent(name="alice", trust="tested")`}</code>
                    </pre>
                  </div>
                  <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-purple-400 mb-2">As Service Consumer</h4>
                    <p className="text-sm text-gray-300 mb-2">"Who do I trust?"</p>
                    <pre className="text-xs text-gray-400 overflow-x-auto">
                      <code>{`need("service", trust="strict")`}</code>
                    </pre>
                  </div>
                </div>
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