'use client'

import React, { useState } from 'react'
import { Copy, Check, User, ArrowRight, ArrowLeft, Download, Play, Terminal, Lightbulb, Zap } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'

const agentCode = `from connectonion import Agent

def greet(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}! Nice to meet you!"

# Create the simplest agent
agent = Agent(
    name="greeter",
    tools=[greet]
)

# Use it
response = agent.run("Say hello to Alice")
print(response)`

const expectedOutput = `Hello, Alice! Nice to meet you!`

const installationCode = `pip install connectonion`

const fullExampleCode = `# hello_world_agent.py
import os
from connectonion import Agent

# Set your OpenAI API key
os.environ['OPENAI_API_KEY'] = 'your-api-key-here'

def greet(name: str) -> str:
    """Say hello to someone by name."""
    return f"Hello, {name}! Nice to meet you!"

def say_goodbye(name: str) -> str:
    """Say goodbye to someone by name."""
    return f"Goodbye, {name}! It was great talking with you!"

# Create your first agent
agent = Agent(
    name="greeter",
    tools=[greet, say_goodbye]
)

if __name__ == "__main__":
    # Test the agent
    print("=== Hello World Agent ===")
    
    # Simple greeting
    response1 = agent.run("Say hello to Alice")
    print(f"Response 1: {response1}")
    
    # Say goodbye  
    response2 = agent.run("Say goodbye to Bob")
    print(f"Response 2: {response2}")
    
    # Interactive conversation
    response3 = agent.run("Greet John and then say goodbye to him")
    print(f"Response 3: {response3}")`

export default function HelloWorldAgentPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Hello World Agent - ConnectOnion Tutorial

Learn how to build your first AI agent with ConnectOnion in just a few lines of code.

## What You'll Learn

- How to create your first ConnectOnion agent
- How to define simple tool functions
- How to run and interact with agents
- Basic agent-to-tool communication patterns

## Installation

\`\`\`bash
${installationCode}
\`\`\`

## Complete Example

\`\`\`python
${fullExampleCode}
\`\`\`

## Key Concepts

1. **Tool Functions**: Regular Python functions become agent tools automatically
2. **Agent Creation**: Simple \`Agent()\` constructor with name and tools
3. **Agent Execution**: Use \`.run()\` method with natural language instructions
4. **Function Calling**: Agent automatically determines which tools to use

This is your first step into building intelligent agents with ConnectOnion!`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/examples" className="hover:text-white transition-colors">Agent Building</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">Hello World Agent</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-green-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">1</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <User className="w-8 h-8 text-green-400" />
                <h1 className="text-4xl font-bold text-white">Hello World Agent</h1>
                <span className="px-3 py-1 bg-green-900/50 text-green-300 rounded-full text-sm font-medium">
                  Beginner
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Build your first AI agent in 5 minutes. Learn the fundamentals of agent creation and tool integration.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="hello-world-agent.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-green-900/20 border border-green-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-green-400" />
          What You'll Learn
        </h2>
        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-green-600 rounded-lg flex items-center justify-center">
              <User className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Agent Creation</h3>
            <p className="text-green-200 text-sm">How to create your first ConnectOnion agent</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-green-600 rounded-lg flex items-center justify-center">
              <Zap className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Tool Functions</h3>
            <p className="text-green-200 text-sm">Turn regular Python functions into AI tools</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-green-600 rounded-lg flex items-center justify-center">
              <Play className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Execution</h3>
            <p className="text-green-200 text-sm">Run agents with natural language commands</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-green-600 rounded-lg flex items-center justify-center">
              <Terminal className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Communication</h3>
            <p className="text-green-200 text-sm">Understand agent-to-tool patterns</p>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-12">
        {/* Code Examples */}
        <div className="space-y-8">
          {/* Installation */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">1. Installation</h3>
              <button
                onClick={() => copyToClipboard(installationCode, 'install')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'install' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6">
              <SyntaxHighlighter 
                language="bash" 
                style={vscDarkPlus}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
              >
                {installationCode}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Basic Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">2. Basic Agent</h3>
              <button
                onClick={() => copyToClipboard(agentCode, 'basic')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'basic' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6">
              <SyntaxHighlighter 
                language="python" 
                style={vscDarkPlus}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {agentCode}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Complete Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">3. Complete Example</h3>
              <button
                onClick={() => copyToClipboard(fullExampleCode, 'complete')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'complete' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6">
              <SyntaxHighlighter 
                language="python" 
                style={vscDarkPlus}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {fullExampleCode}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="space-y-8">
          {/* Output */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
              <Terminal className="w-5 h-5 text-green-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm">
                <pre className="text-green-200 whitespace-pre-wrap">
                  {`=== Hello World Agent ===

Response 1: Hello, Alice! Nice to meet you!

Response 2: Goodbye, Bob! It was great talking with you!

Response 3: Hello, John! Nice to meet you! Goodbye, John! It was great talking with you!`}
                </pre>
              </div>
            </div>
          </div>

          {/* How It Works */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">How It Works</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-green-400 mb-2">🔧 Tool Definition</h4>
                <p className="text-gray-300">Regular Python functions with docstrings become AI tools automatically.</p>
              </div>
              <div>
                <h4 className="font-semibold text-green-400 mb-2">🤖 Agent Creation</h4>
                <p className="text-gray-300">Pass your functions to Agent() constructor - ConnectOnion handles the rest.</p>
              </div>
              <div>
                <h4 className="font-semibold text-green-400 mb-2">💬 Natural Language</h4>
                <p className="text-gray-300">Agent understands instructions and chooses the right tools automatically.</p>
              </div>
            </div>
          </div>

          {/* Next Steps */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Try It Yourself</h3>
            <div className="space-y-3 text-sm">
              <div className="p-3 bg-green-900/20 border border-green-500/30 rounded">
                <p className="text-green-300 font-medium mb-1">💡 Experiment Ideas</p>
                <ul className="text-green-200 space-y-1">
                  <li>• Add more greeting functions in different languages</li>
                  <li>• Create tools that take multiple parameters</li>
                  <li>• Try complex multi-step instructions</li>
                </ul>
              </div>
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(fullExampleCode)}`}
                download="hello_world_agent.py"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-green-600 hover:bg-green-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Complete Example
              </a>
            </div>
          </div>

          {/* Requirements */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Requirements</h3>
            <div className="space-y-2 text-sm text-gray-300">
              <p>• Python 3.8+</p>
              <p>• ConnectOnion v0.0.1</p>
              <p>• OpenAI API key</p>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <Link 
          href="/examples" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          All Examples
        </Link>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/examples/calculator" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            2. Basic Calculator
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}