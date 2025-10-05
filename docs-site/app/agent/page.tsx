/*
  @date: 2025-10-05
  @description: Agent Documentation Page

  This page documents the Agent class - the core orchestrator of ConnectOnion.
  Structure: Simple example → Full API overview → Detailed sections

  Design follows CLAUDE.md principles:
  - Start with success (60 second example)
  - Full API overview after quick start
  - Progressive disclosure (simple → advanced)
  - Code-first, explanation second
  - Real examples with real output
*/

'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ContentNavigation } from '../../components/ContentNavigation'
import { Copy, Check, Users, Rocket, ArrowRight, Zap, Code, Settings, RefreshCw, Play } from 'lucide-react'
import CodeWithResult from '../../components/CodeWithResult'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'
import { CommandBlock } from '../../components/CommandBlock'

export default function AgentDocsPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const pageContent = `# Agent

The heart of ConnectOnion. Give it tools, and it figures out the rest.

## Quick Start (60 Seconds)

\`\`\`python
from connectonion import Agent

# Define what your agent can do
def calculate(expression: str) -> str:
    """Do math calculations."""
    return str(eval(expression))

# Create agent
agent = Agent("math_bot", tools=[calculate])

# Use it
result = agent.input("What is 42 * 17?")
\`\`\`

**Output:**
\`\`\`
To calculate 42 * 17, I'll use the calculator tool.
The result is 714.
\`\`\`

**That's it.** Your first AI agent in 5 lines.

## What Agent Can Do - Full API Overview

After that simple example, here's **everything** an Agent can do:

### Creating an Agent

\`\`\`python
Agent(
    name="my_bot",                        # Required: agent identifier
    tools=[func1, func2],                 # Optional: functions agent can call
    system_prompt="You are helpful",      # Optional: personality/behavior
    model="o4-mini",                      # Optional: LLM model (OpenAI/Claude/Gemini)
    max_iterations=10,                    # Optional: how many tool calls allowed
    api_key="sk-...",                     # Optional: override environment variable
    llm=custom_llm,                       # Optional: bring your own LLM instance
    trust="tested",                       # Optional: security verification
    log=True                              # Optional: logging configuration
)
\`\`\`

### Using Your Agent

\`\`\`python
# Give it a task
result = agent.input("Do something")

# Override iterations for complex tasks
result = agent.input("Complex task", max_iterations=20)

# Execute a tool directly (for testing)
result = agent.execute_tool("tool_name", {"arg": "value"})
\`\`\`

### Managing Tools

\`\`\`python
# Add tools after creation
agent.add_tool(new_function)

# Remove tools
agent.remove_tool("function_name")

# See what tools are available
tools = agent.list_tools()
\`\`\`

### Conversations & State

\`\`\`python
# Multi-turn conversations work automatically
agent.input("What is 10 + 5?")       # Turn 1: "15"
agent.input("Multiply that by 2")    # Turn 2: "30" (remembers context)

# Start fresh
agent.reset_conversation()

# Access internal state (advanced)
session = agent.current_session      # Messages, trace, turn count
\`\`\`

### Attributes You Can Access

\`\`\`python
agent.name                  # str: Agent identifier
agent.tools                 # List[Callable]: All available tools
agent.tool_map              # Dict[str, Callable]: Fast tool lookup
agent.system_prompt         # str: Agent's personality
agent.max_iterations        # int: Default iteration limit
agent.current_session       # dict | None: Runtime state
\`\`\`

**That's the complete API.** Now let's dive into each feature.
`

  return (
    <div className="min-h-screen bg-black text-gray-100">
      <div className="max-w-4xl mx-auto px-6 py-12">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-gray-400 mb-8">
          <Link href="/" className="hover:text-purple-400 transition-colors">
            Docs
          </Link>
          <ArrowRight className="w-4 h-4" />
          <span className="text-white">Agent</span>
        </div>

        {/* Header */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-gradient-to-br from-purple-600/20 to-blue-600/20 rounded-xl border border-purple-500/30">
              <Users className="w-8 h-8 text-purple-400" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-white mb-2">Agent</h1>
              <p className="text-lg text-gray-400">
                The heart of ConnectOnion. Give it tools, and it figures out the rest.
              </p>
            </div>
          </div>
          <CopyMarkdownButton content={pageContent} filename="agent.md" />
        </div>

        {/* Quick Start Section */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
            <Rocket className="w-6 h-6 text-purple-400" />
            Quick Start (60 Seconds)
          </h2>

          <CodeWithResult
            code={`from connectonion import Agent

# Define what your agent can do
def calculate(expression: str) -> str:
    """Do math calculations."""
    return str(eval(expression))

# Create agent
agent = Agent("math_bot", tools=[calculate])

# Use it
result = agent.input("What is 42 * 17?")`}
            result={`To calculate 42 * 17, I'll use the calculator tool.
The result is 714.`}
            language="python"
          />

          <div className="mt-4 p-4 bg-green-900/20 border border-green-500/30 rounded-lg">
            <p className="text-green-300 font-semibold">
              That's it. Your first AI agent in 5 lines.
            </p>
          </div>
        </section>

        {/* Full API Overview */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
            <Code className="w-6 h-6 text-purple-400" />
            What Agent Can Do - Full API Overview
          </h2>

          <p className="text-gray-300 mb-6">
            After that simple example, here's <span className="text-purple-400 font-semibold">everything</span> an Agent can do:
          </p>

          {/* Creating an Agent */}
          <div className="mb-8">
            <h3 className="text-xl font-semibold text-white mb-4">Creating an Agent</h3>
            <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
              <pre className="text-sm overflow-x-auto">
                <code className="text-gray-300">{`Agent(
    name="my_bot",                        # Required: agent identifier
    tools=[func1, func2],                 # Optional: functions agent can call
    system_prompt="You are helpful",      # Optional: personality/behavior
    model="o4-mini",                      # Optional: LLM model
    max_iterations=10,                    # Optional: iteration limit
    api_key="sk-...",                     # Optional: override env var
    llm=custom_llm,                       # Optional: custom LLM instance
    trust="tested",                       # Optional: security verification
    log=True                              # Optional: logging config
)`}</code>
              </pre>
            </div>
          </div>

          {/* Using Your Agent */}
          <div className="mb-8">
            <h3 className="text-xl font-semibold text-white mb-4">Using Your Agent</h3>
            <div className="grid grid-cols-1 gap-4">
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <pre className="text-sm"><code className="text-gray-300">{`# Give it a task
result = agent.input("Do something")

# Override iterations for complex tasks
result = agent.input("Complex task", max_iterations=20)

# Execute a tool directly (for testing)
result = agent.execute_tool("tool_name", {"arg": "value"})`}</code></pre>
              </div>
            </div>
          </div>

          {/* Managing Tools */}
          <div className="mb-8">
            <h3 className="text-xl font-semibold text-white mb-4">Managing Tools</h3>
            <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
              <pre className="text-sm"><code className="text-gray-300">{`agent.add_tool(new_function)    # Add tools after creation
agent.remove_tool("name")       # Remove tools
agent.list_tools()              # See available tools`}</code></pre>
            </div>
          </div>

          {/* Conversations */}
          <div className="mb-8">
            <h3 className="text-xl font-semibold text-white mb-4">Conversations & State</h3>
            <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
              <pre className="text-sm"><code className="text-gray-300">{`agent.input("What is 10 + 5?")     # Turn 1: "15"
agent.input("Multiply that by 2")  # Turn 2: "30" (remembers!)

agent.reset_conversation()         # Start fresh
session = agent.current_session    # Access internal state`}</code></pre>
            </div>
          </div>

          {/* Attributes */}
          <div className="mb-8">
            <h3 className="text-xl font-semibold text-white mb-4">Attributes You Can Access</h3>
            <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
              <pre className="text-sm"><code className="text-gray-300">{`agent.name                # str: Agent identifier
agent.tools               # List[Callable]: All tools
agent.tool_map            # Dict: Fast tool lookup
agent.system_prompt       # str: Personality
agent.max_iterations      # int: Iteration limit
agent.current_session     # dict | None: Runtime state`}</code></pre>
            </div>
          </div>

          <div className="mt-6 p-4 bg-purple-900/20 border border-purple-500/30 rounded-lg">
            <p className="text-purple-300 font-semibold mb-2">
              That's the complete API.
            </p>
            <p className="text-gray-400 text-sm">
              Now let's dive into each feature below. Jump to any section that interests you!
            </p>
          </div>
        </section>

        {/* Table of Contents */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6">Table of Contents</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              { title: 'Creating Agents', href: '#creating-agents' },
              { title: 'Using Your Agent', href: '#using-your-agent' },
              { title: 'Managing Tools', href: '#managing-tools' },
              { title: 'Conversations & Multi-Turn', href: '#conversations' },
              { title: 'Iteration Control', href: '#iteration-control' },
              { title: 'Models & LLMs', href: '#models' },
              { title: 'Logging & Debugging', href: '#logging' },
              { title: 'Trust & Security', href: '#trust' },
              { title: 'Common Patterns', href: '#patterns' },
              { title: 'Testing', href: '#testing' },
              { title: 'Architecture', href: '#architecture' }
            ].map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="flex items-center gap-2 p-3 bg-gray-900 hover:bg-gray-800 rounded-lg border border-gray-800 hover:border-purple-500/50 transition-all group"
              >
                <ArrowRight className="w-4 h-4 text-gray-500 group-hover:text-purple-400 transition-colors" />
                <span className="text-gray-300 group-hover:text-white transition-colors">
                  {item.title}
                </span>
              </a>
            ))}
          </div>
        </section>

        {/* Learn More Section */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6">Learn More</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Link
              href="/tools"
              className="p-6 bg-gradient-to-br from-blue-900/20 to-purple-900/20 rounded-lg border border-blue-500/30 hover:border-blue-500/60 transition-all group"
            >
              <Code className="w-8 h-8 text-blue-400 mb-3" />
              <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-blue-300 transition-colors">
                Tools
              </h3>
              <p className="text-sm text-gray-400">
                Learn how to create powerful tools for your agents
              </p>
            </Link>

            <Link
              href="/max-iterations"
              className="p-6 bg-gradient-to-br from-purple-900/20 to-pink-900/20 rounded-lg border border-purple-500/30 hover:border-purple-500/60 transition-all group"
            >
              <RefreshCw className="w-8 h-8 text-purple-400 mb-3" />
              <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-purple-300 transition-colors">
                max_iterations
              </h3>
              <p className="text-sm text-gray-400">
                Control how many tool calls your agent can make
              </p>
            </Link>

            <Link
              href="/prompts"
              className="p-6 bg-gradient-to-br from-green-900/20 to-teal-900/20 rounded-lg border border-green-500/30 hover:border-green-500/60 transition-all group"
            >
              <Settings className="w-8 h-8 text-green-400 mb-3" />
              <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-green-300 transition-colors">
                System Prompts
              </h3>
              <p className="text-sm text-gray-400">
                Give your agent a personality and behavior
              </p>
            </Link>

            <Link
              href="/xray"
              className="p-6 bg-gradient-to-br from-yellow-900/20 to-orange-900/20 rounded-lg border border-yellow-500/30 hover:border-yellow-500/60 transition-all group"
            >
              <Zap className="w-8 h-8 text-yellow-400 mb-3" />
              <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-yellow-300 transition-colors">
                Debug with @xray
              </h3>
              <p className="text-sm text-gray-400">
                See what your agent is thinking during execution
              </p>
            </Link>
          </div>
        </section>

        {/* Philosophy */}
        <section className="mb-16">
          <div className="p-8 bg-gradient-to-br from-purple-900/10 to-blue-900/10 rounded-xl border border-purple-500/20">
            <h2 className="text-2xl font-bold text-white mb-4">Philosophy</h2>
            <p className="text-xl text-purple-300 font-semibold mb-6">
              "Keep simple things simple, make complicated things possible"
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-3">Simple Case</h3>
                <div className="bg-black/50 rounded-lg p-4 border border-gray-800">
                  <pre className="text-sm"><code className="text-gray-300">{`agent = Agent("bot", tools=[search])
agent.input("Find Python docs")`}</code></pre>
                </div>
              </div>

              <div>
                <h3 className="text-lg font-semibold text-white mb-3">Complex Case</h3>
                <div className="bg-black/50 rounded-lg p-4 border border-gray-800">
                  <pre className="text-sm"><code className="text-gray-300">{`trust_agent = Agent("verifier", ...)

agent = Agent(
    name="production",
    llm=custom_llm,
    tools=[deploy, rollback],
    system_prompt=Path("ops.md"),
    max_iterations=30,
    trust=trust_agent,
    log="/var/log/production.log"
)`}</code></pre>
                </div>
              </div>
            </div>

            <p className="text-gray-400 mt-6 text-center">
              <span className="font-semibold text-white">Both are valid.</span> Start simple, add complexity only when needed.
            </p>
          </div>
        </section>

        {/* Bottom Note */}
        <div className="text-center py-8 border-t border-gray-800">
          <p className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-blue-400 mb-2">
            ConnectOnion: AI Agent = Prompt + Function
          </p>
          <p className="text-gray-400">
            That's it. That's the framework. Now go build something useful.
          </p>
        </div>

        {/* Navigation */}
        <div className="mt-12">
          <ContentNavigation />
        </div>
      </div>
    </div>
  )
}
