/*
  DESIGN ISSUES TO FIX:
  
  1. **Missing Core Components** (Priority: HIGH)
     - No breadcrumb navigation like other pages
     - Missing copy-all-content button (CLAUDE.md requirement)
     - No page header structure matching other docs
     - Fix: Add breadcrumb, CopyMarkdownButton, standardize header
  
  2. **Information Architecture** (Priority: HIGH)
     - Trust levels buried in nested cards
     - No visual hierarchy between trust forms
     - Missing quick reference or cheat sheet
     - Fix: Create trust level comparison table, visual decision tree, quick ref card
  
  3. **Code Examples** (Priority: MEDIUM)
     - Examples don't show real-world scenarios
     - Missing error cases and edge cases
     - No progression from simple to complex
     - Fix: Add realistic examples, show error handling, progressive complexity
  
  4. **Visual Design** (Priority: MEDIUM)
     - Trust level colors (green/yellow/red) not accessible
     - Grid layout doesn't work on tablet sizes
     - Sidebar content hidden on mobile
     - Fix: Use accessible color palette, responsive grid, mobile-first sidebar
  
  5. **Navigation Flow** (Priority: LOW)
     - No clear next steps after reading
     - Missing links to related concepts
     - No integration with PageNavigation component
     - Fix: Add "What's next" section, cross-link to related docs, add navigation
*/

'use client'

import CodeWithResult from '../../components/CodeWithResult'
import { Shield, Users, Code, Zap, CheckCircle, TrendingUp, AlertCircle, BookOpen } from 'lucide-react'
import Link from 'next/link'
import { ContentNavigation } from '../../components/ContentNavigation'


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
                      <span className="text-gray-300">Verified agents only (production)</span>
                    </div>
                  </div>
                </div>

                {/* Trust Rules */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                    <span className="text-purple-400">2.</span> Trust Rules (Dict)
                  </h3>
                  <p className="text-gray-400 mb-4">Fine-grained control with custom rules:</p>
                  <CodeWithResult
                    code={`trust_rules = {
    "allow": ["agent1", "agent2"],     # Whitelist
    "deny": ["untrusted_agent"],       # Blacklist  
    "require_auth": True,               # Authentication
    "test_timeout": 30,                 # Test duration
    "max_interactions": 100             # Rate limiting
}

agent = Agent("secure", trust=trust_rules)`}
                    fileName="custom_trust.py"
                  />
                </div>

                {/* Trust Functions */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                    <span className="text-purple-400">3.</span> Trust Functions
                  </h3>
                  <p className="text-gray-400 mb-4">Dynamic trust evaluation with custom logic:</p>
                  <CodeWithResult
                    code={`def custom_trust(agent_name: str, context: dict) -> bool:
    """Evaluate trust based on custom logic"""
    if context.get("environment") == "production":
        return agent_name in VERIFIED_AGENTS
    return True  # Open in development

agent = Agent("dynamic", trust=custom_trust)`}
                    fileName="dynamic_trust.py"
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
              <div className="bg-gradient-to-br from-green-900/20 to-blue-900/20 border border-green-800/50 rounded-lg p-6">
                <p className="text-gray-300 mb-4">
                  Trust works both ways in ConnectOnion:
                </p>
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <h4 className="font-semibold text-white mb-2">Outbound Trust</h4>
                    <p className="text-sm text-gray-400">Who I trust to use</p>
                    <code className="text-xs block mt-2 text-green-400">need("service", trust="...")</code>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <h4 className="font-semibold text-white mb-2">Inbound Trust</h4>
                    <p className="text-sm text-gray-400">Who can use me</p>
                    <code className="text-xs block mt-2 text-blue-400">Agent(..., trust="...")</code>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Trust Decision Helper */}
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Shield className="w-5 h-5 text-purple-400" />
                Choose Your Trust Level
              </h3>
              <div className="space-y-3">
                <div className="p-3 bg-gray-800/50 rounded-lg">
                  <p className="text-sm font-medium text-white mb-1">Development?</p>
                  <p className="text-xs text-gray-400">Use <code className="text-green-400">open</code></p>
                </div>
                <div className="p-3 bg-gray-800/50 rounded-lg">
                  <p className="text-sm font-medium text-white mb-1">Testing/Staging?</p>
                  <p className="text-xs text-gray-400">Use <code className="text-yellow-400">tested</code></p>
                </div>
                <div className="p-3 bg-gray-800/50 rounded-lg">
                  <p className="text-sm font-medium text-white mb-1">Production?</p>
                  <p className="text-xs text-gray-400">Use <code className="text-red-400">strict</code></p>
                </div>
              </div>
            </div>

            {/* Common Patterns */}
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Common Patterns</h3>
              <ul className="space-y-2 text-sm">
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-400 mt-0.5" />
                  <span className="text-gray-300">Progressive trust elevation</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-400 mt-0.5" />
                  <span className="text-gray-300">Environment-based trust</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-400 mt-0.5" />
                  <span className="text-gray-300">Mutual authentication</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-400 mt-0.5" />
                  <span className="text-gray-300">Rate limiting & quotas</span>
                </li>
              </ul>
            </div>

            {/* Warning */}
            <div className="bg-yellow-900/20 border border-yellow-800 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-yellow-400 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-yellow-200 mb-1">Security Note</p>
                  <p className="text-xs text-yellow-300/80">
                    Always use <code>strict</code> trust in production environments to prevent unauthorized access.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <ContentNavigation />
      </div>
    </div>
  )
}