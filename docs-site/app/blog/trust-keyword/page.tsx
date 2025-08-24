'use client'

import { useState } from 'react'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'
import { ArrowLeft, CheckCircle, XCircle, TrendingUp, Users, Shield, Code, MessageSquare, Lightbulb } from 'lucide-react'
import Link from 'next/link'

const blogContent = `# Why We Chose "Trust" - The Story Behind ConnectOnion's Authentication Keyword

*December 2024*

When designing ConnectOnion's agent-to-agent authentication system, we faced a crucial decision: what should we call the parameter that controls how agents verify each other? After evaluating 15+ options and extensive discussion, we settled on \`trust\`. Here's why.

## The Challenge: Finding a Bidirectional Word

Our authentication system needed a keyword that works in two directions:
1. **As a service provider**: "Who can use my services?"
2. **As a service consumer**: "Which services do I trust?"

Most security terms only work in one direction. We needed something that naturally flows both ways.

## Options We Considered

### 1. \`auth\` / \`authentication\`
**Why not**: Too technical and implies traditional authentication (passwords, tokens). We're doing behavioral verification, not credential checking.

### 2. \`verify\` / \`validate\`
**Why not**: One-directional - you verify others, but saying "I'm verified" sounds like a credential system.

### 3. \`guard\` / \`guardian\`
**Why not**: Implies blocking/protection only. Doesn't capture the mutual relationship between agents.

### 4. \`policy\` / \`rules\`
**Why not**: Too formal and configuration-heavy. Doesn't match our natural language approach.

### 5. \`security\` / \`safe\`
**Why not**: Too broad and creates fear. Security implies threats; we want collaboration.

### 6. \`filter\` / \`allow\`
**Why not**: One-directional and negative. Focuses on exclusion rather than building relationships.

### 7. \`mode\` / \`env\`
**Why not**: Too generic. Could mean anything - doesn't clearly indicate authentication purpose.

### 8. \`strict\` / \`open\` / \`tested\`
**Why not**: These became our trust *levels*, but the parameter itself needed a clearer name.

### 9. \`require\` / \`expect\`
**Why not**: Works for incoming but awkward for outgoing ("I require others" vs "I'm required"?).

### 10. \`proof\` / \`prove\`
**Why not**: Implies formal verification. We do behavioral testing, not mathematical proofs.

## Why "Trust" Won

### 1. Naturally Bidirectional
\`\`\`python
# Both directions feel natural
agent = Agent(name="my_service", trust="strict")  # I trust strict agents
service = need("translator", trust="tested")      # I need tested services
\`\`\`

The word "trust" flows both ways without awkwardness.

### 2. Human-Friendly
Developers immediately understand trust. It's how we think about relationships:
- "I trust this service"
- "This service trusts me"
- "We need to build trust"

### 3. Progressive, Not Binary
Trust isn't yes/no - it grows through interaction:
\`\`\`python
trust="open"    # Trust everyone (dev mode)
trust="tested"  # Test first, then trust
trust="strict"  # Only trusted partners
\`\`\`

### 4. Matches Real Behavior
We're not checking passwords or certificates. We're testing behavior:
- Can you translate "Hello" to "Hola"?
- Do you respond within 500ms?
- Have we worked together successfully before?

This is trust-building, not authentication.

### 5. Enables Natural Language Config
\`\`\`python
trust = """
I trust agents that:
- Pass my capability tests
- Respond quickly
- Have good track record
"""
\`\`\`

"Trust policy" sounds natural. "Authentication policy" sounds bureaucratic.

## The Unix Philosophy Connection

Following Unix principles, trust isn't a complex protocol - it's simple functions composed by prompts:

\`\`\`python
# Small, composable trust functions
def check_whitelist(agent_id): ...
def test_capability(agent, test): ...
def measure_response_time(agent): ...

# Composed into trust agents
trust_agent = Agent(
    name="my_guardian",
    tools=[check_whitelist, test_capability, measure_response_time]
)
\`\`\`

## Some Challenges with "Trust"

We acknowledge potential confusion:

1. **Overloaded Term**: "Trust" appears in many contexts (TLS, trust stores, web of trust)
2. **Seems Soft**: Some developers might prefer "harder" security terms
3. **Cultural Variations**: Trust has different connotations across cultures

But these are outweighed by its clarity and naturalness for our use case.

## The Final Design

\`\`\`python
# Three forms, one keyword
translator = need("translate", trust="strict")           # Simple level
translator = need("translate", trust="./trust.md")       # Natural language
translator = need("translate", trust=my_trust_agent)     # Custom agent

# Bidirectional by default
alice = Agent(name="alice", trust="tested")  # Alice tests her users
bob_needs = need("service", trust="strict")  # Bob only uses strict services
# Both must approve for connection!
\`\`\`

## Conclusion

\`trust\` won because it's the most honest description of what we're doing. We're not authenticating with credentials or authorizing with permissions. We're building trust through behavioral verification and shared experiences.

In ConnectOnion, agents don't authenticate - they trust. And that makes all the difference.

---

*This design decision exemplifies ConnectOnion's philosophy: make simple things simple, make complicated things possible. Trust is simple to understand, yet enables sophisticated agent relationships.*`

// Options data with reasons
const optionsData = [
  { name: 'auth', icon: Shield, rejected: true, reason: 'Too technical, implies credentials' },
  { name: 'verify', icon: CheckCircle, rejected: true, reason: 'One-directional only' },
  { name: 'guard', icon: Shield, rejected: true, reason: 'Implies blocking, not collaboration' },
  { name: 'policy', icon: Code, rejected: true, reason: 'Too formal and configuration-heavy' },
  { name: 'security', icon: Shield, rejected: true, reason: 'Creates fear, too broad' },
  { name: 'trust', icon: Users, rejected: false, reason: 'Naturally bidirectional & human-friendly' },
  { name: 'filter', icon: XCircle, rejected: true, reason: 'Negative, focuses on exclusion' },
  { name: 'mode', icon: Code, rejected: true, reason: 'Too generic, unclear purpose' },
  { name: 'strict', icon: Shield, rejected: true, reason: 'Became a trust level, not the parameter' },
  { name: 'require', icon: CheckCircle, rejected: true, reason: 'Awkward for bidirectional use' },
]

export default function TrustKeywordBlog() {
  const [hoveredOption, setHoveredOption] = useState<string | null>(null)

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Hero Section */}
      <div className="relative overflow-hidden bg-gradient-to-b from-purple-900/20 to-gray-950 border-b border-gray-800">
        <div className="absolute inset-0 bg-grid-white/[0.02] bg-[size:32px_32px]" />
        <div className="relative max-w-6xl mx-auto px-8 py-16">
          <Link href="/docs" className="inline-flex items-center gap-2 text-gray-400 hover:text-white mb-8 transition-colors">
            <ArrowLeft className="w-4 h-4" />
            Back to Documentation
          </Link>
          
          <div className="flex items-start justify-between gap-8">
            <div>
              <div className="text-sm text-purple-400 font-medium mb-3">Design Decision</div>
              <h1 className="text-4xl lg:text-5xl font-bold mb-4 bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
                Why We Chose "Trust"
              </h1>
              <p className="text-xl text-gray-300 max-w-3xl">
                The story behind ConnectOnion's authentication keyword decision
              </p>
            </div>
            <CopyMarkdownButton content={blogContent} className="flex-shrink-0" />
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-6xl mx-auto px-8 py-12">
        <div className="grid lg:grid-cols-3 gap-12">
          {/* Article Content */}
          <div className="lg:col-span-2 space-y-8">
            {/* The Challenge */}
            <section className="prose prose-invert max-w-none">
              <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-3">
                <MessageSquare className="w-6 h-6 text-purple-400" />
                The Challenge
              </h2>
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                <p className="text-gray-300 mb-4">
                  Our authentication system needed a keyword that works in two directions:
                </p>
                <div className="space-y-3">
                  <div className="flex items-start gap-3">
                    <div className="w-6 h-6 rounded-full bg-purple-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <span className="text-purple-400 text-sm">1</span>
                    </div>
                    <div>
                      <div className="font-semibold text-white">As a service provider</div>
                      <div className="text-gray-400 text-sm">"Who can use my services?"</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <div className="w-6 h-6 rounded-full bg-purple-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <span className="text-purple-400 text-sm">2</span>
                    </div>
                    <div>
                      <div className="font-semibold text-white">As a service consumer</div>
                      <div className="text-gray-400 text-sm">"Which services do I trust?"</div>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Options Grid */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <Lightbulb className="w-6 h-6 text-yellow-400" />
                Options We Evaluated
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {optionsData.map((option) => {
                  const Icon = option.icon
                  return (
                    <div
                      key={option.name}
                      onMouseEnter={() => setHoveredOption(option.name)}
                      onMouseLeave={() => setHoveredOption(null)}
                      className={`relative p-4 rounded-lg border transition-all cursor-pointer ${
                        option.rejected
                          ? 'bg-gray-900/50 border-gray-800 hover:border-red-900/50'
                          : 'bg-purple-900/20 border-purple-800 hover:border-purple-600'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Icon className={`w-4 h-4 ${option.rejected ? 'text-gray-500' : 'text-purple-400'}`} />
                        <span className={`font-mono text-sm ${option.rejected ? 'text-gray-400 line-through' : 'text-white'}`}>
                          {option.name}
                        </span>
                      </div>
                      {hoveredOption === option.name && (
                        <div className="absolute z-10 bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-xs text-gray-300 whitespace-nowrap">
                          {option.reason}
                          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-px w-2 h-2 bg-gray-800 border-r border-b border-gray-700 rotate-45" />
                        </div>
                      )}
                      {!option.rejected && (
                        <CheckCircle className="absolute top-2 right-2 w-4 h-4 text-green-400" />
                      )}
                    </div>
                  )
                })}
              </div>
            </section>

            {/* Why Trust Won */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <TrendingUp className="w-6 h-6 text-green-400" />
                Why "Trust" Won
              </h2>
              <div className="space-y-4">
                {[
                  { title: 'Naturally Bidirectional', desc: 'Works equally well for "I trust you" and "You trust me"' },
                  { title: 'Human-Friendly', desc: 'Developers immediately understand trust relationships' },
                  { title: 'Progressive, Not Binary', desc: 'Trust grows through successful interactions' },
                  { title: 'Matches Real Behavior', desc: 'We test behavior, not check credentials' },
                  { title: 'Natural Language Config', desc: 'Trust policies read like plain English' },
                ].map((item, i) => (
                  <div key={i} className="flex gap-4 p-4 bg-gray-900/50 border border-gray-800 rounded-lg hover:border-gray-700 transition-colors">
                    <div className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center flex-shrink-0">
                      <span className="text-green-400 text-sm font-bold">{i + 1}</span>
                    </div>
                    <div>
                      <div className="font-semibold text-white mb-1">{item.title}</div>
                      <div className="text-sm text-gray-400">{item.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* Code Example */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <Code className="w-6 h-6 text-blue-400" />
                The Final Design
              </h2>
              <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                <div className="bg-gray-800 px-4 py-2 border-b border-gray-700">
                  <span className="text-xs text-gray-400">Python</span>
                </div>
                <pre className="p-6 overflow-x-auto">
                  <code className="text-sm text-gray-300">{`# Three forms, one keyword
translator = need("translate", trust="strict")           # Simple level
translator = need("translate", trust="./trust.md")       # Natural language  
translator = need("translate", trust=my_trust_agent)     # Custom agent

# Bidirectional by default
alice = Agent(name="alice", trust="tested")  # Alice tests her users
bob_needs = need("service", trust="strict")  # Bob only uses strict services
# Both must approve for connection!`}</code>
                </pre>
              </div>
            </section>
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1 space-y-6">
            {/* Key Insights */}
            <div className="bg-gradient-to-br from-purple-900/20 to-pink-900/20 border border-purple-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Lightbulb className="w-5 h-5 text-yellow-400" />
                Key Insight
              </h3>
              <p className="text-sm text-gray-300 leading-relaxed">
                <span className="font-mono bg-purple-900/50 px-1.5 py-0.5 rounded">trust</span> won because 
                it's the most honest description of what we're doing. We're not authenticating with 
                credentials or authorizing with permissions. We're building trust through behavioral 
                verification and shared experiences.
              </p>
            </div>

            {/* Philosophy */}
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Unix Philosophy</h3>
              <p className="text-sm text-gray-400 mb-4">
                Trust isn't a complex protocol - it's simple functions composed by prompts:
              </p>
              <ul className="space-y-2 text-sm">
                <li className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-purple-400 mt-1.5 flex-shrink-0" />
                  <span className="text-gray-300">Small, composable functions</span>
                </li>
                <li className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-purple-400 mt-1.5 flex-shrink-0" />
                  <span className="text-gray-300">Natural language configuration</span>
                </li>
                <li className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-purple-400 mt-1.5 flex-shrink-0" />
                  <span className="text-gray-300">Behavior over credentials</span>
                </li>
              </ul>
            </div>

            {/* Related Docs */}
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Related Documentation</h3>
              <div className="space-y-3">
                <Link href="/trust" className="block text-sm text-purple-400 hover:text-purple-300 transition-colors">
                  → Trust Parameter Guide
                </Link>
                <Link href="/examples" className="block text-sm text-purple-400 hover:text-purple-300 transition-colors">
                  → Agent Examples
                </Link>
                <Link href="/quickstart" className="block text-sm text-purple-400 hover:text-purple-300 transition-colors">
                  → Quick Start
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer Quote */}
      <div className="max-w-6xl mx-auto px-8 py-12 border-t border-gray-800">
        <blockquote className="text-center">
          <p className="text-lg text-gray-300 italic mb-4">
            "In ConnectOnion, agents don't authenticate - they trust. And that makes all the difference."
          </p>
          <cite className="text-sm text-gray-500">— ConnectOnion Team</cite>
        </blockquote>
      </div>
    </div>
  )
}