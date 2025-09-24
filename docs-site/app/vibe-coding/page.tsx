'use client'

import { useState } from 'react'
import { FileCode2, Copy, Check, Sparkles, ArrowRight, Zap, BookOpen, Mouse, Rocket, Code, Terminal, Download, ChevronRight, Target } from 'lucide-react'
import { FaBullseye, FaRocket, FaEnvelope, FaLightbulb, FaGift } from 'react-icons/fa'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'
import { ContentNavigation } from '../../components/ContentNavigation'

export default function VibeCodingPage() {
  const [copiedCode, setCopiedCode] = useState<string | null>(null)
  
  // Add CSS for gradient animation
  const gradientStyle = `
    @keyframes gradient {
      0% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
      100% { background-position: 0% 50%; }
    }
    .animate-gradient {
      background-size: 200% 200%;
      animation: gradient 3s ease infinite;
    }
  `

  const handleCopyCode = (code: string, id: string) => {
    navigator.clipboard.writeText(code)
    setCopiedCode(id)
    setTimeout(() => setCopiedCode(null), 2000)
  }

  const CodeBlock = ({ code, language = 'python', id }: { code: string; language?: string; id: string }) => (
    <div className="relative group">
      <button
        onClick={() => handleCopyCode(code, id)}
        className="absolute right-2 top-2 p-2 bg-gray-700 hover:bg-gray-600 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity z-10"
        aria-label="Copy code"
      >
        {copiedCode === id ? (
          <Check className="w-4 h-4 text-green-400" />
        ) : (
          <Copy className="w-4 h-4 text-gray-300" />
        )}
      </button>
      <SyntaxHighlighter 
        language={language} 
        style={monokai}
        customStyle={{
          borderRadius: '0.5rem',
          padding: '1.25rem',
          margin: 0,
          fontSize: '0.875rem',
          lineHeight: '1.5',
          overflowX: 'auto'
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <style jsx>{gradientStyle}</style>
      <div className="max-w-5xl mx-auto px-6 md:px-8 py-12">
        {/* Header */}
        <div className="mb-16">
          <div className="flex items-center gap-4 mb-6">
            <div className="p-4 bg-gradient-to-br from-purple-500/20 via-pink-500/10 to-purple-500/20 rounded-2xl border border-purple-500/30 shadow-lg shadow-purple-500/10">
              <FileCode2 className="w-10 h-10 text-purple-400" />
            </div>
            <div>
              <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-purple-400 via-pink-400 to-purple-400 bg-clip-text text-transparent animate-gradient">
                Vibe Coding Guide
              </h1>
              <p className="text-gray-400 mt-2 text-lg">Build AI Agents in 60 Seconds with Cursor</p>
            </div>
          </div>
          <div className="flex gap-3">
            <CopyMarkdownButton />
            <a 
              href="https://cursor.sh" 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors border border-gray-700"
            >
              <Download className="w-4 h-4" />
              <span className="text-sm">Get Cursor</span>
            </a>
          </div>
        </div>

        {/* Hero Section */}
        <section className="mb-20">
          <div className="bg-gradient-to-br from-purple-500/10 via-transparent to-pink-500/10 rounded-2xl p-8 border border-purple-500/20 mb-12">
            <div className="text-center mb-8">
              <div className="inline-flex items-center gap-2 px-4 py-2 bg-purple-500/10 rounded-full border border-purple-500/30 mb-6">
                <Sparkles className="w-4 h-4 text-purple-400" />
                <span className="text-sm font-medium text-purple-300">No Coding Experience Required</span>
              </div>
              <h2 className="text-3xl md:text-4xl font-bold mb-4">
                From Idea to Working Agent in <span className="text-purple-400">3 Steps</span>
              </h2>
              <p className="text-xl text-gray-400 max-w-2xl mx-auto">
                Just drag our docs into Cursor AI and describe what you want. The AI handles everything else.
              </p>
            </div>
            
            <div className="grid md:grid-cols-3 gap-4 max-w-3xl mx-auto">
              <div className="flex items-center gap-3 bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                <div className="bg-purple-500/20 p-2 rounded-lg">
                  <Mouse className="w-5 h-5 text-purple-400" />
                </div>
                <div>
                  <p className="font-semibold">1. Drag</p>
                  <p className="text-sm text-gray-400">Our docs file</p>
                </div>
              </div>
              <div className="flex items-center gap-3 bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                <div className="bg-pink-500/20 p-2 rounded-lg">
                  <Code className="w-5 h-5 text-pink-400" />
                </div>
                <div>
                  <p className="font-semibold">2. Describe</p>
                  <p className="text-sm text-gray-400">Your agent idea</p>
                </div>
              </div>
              <div className="flex items-center gap-3 bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                <div className="bg-green-500/20 p-2 rounded-lg">
                  <Rocket className="w-5 h-5 text-green-400" />
                </div>
                <div>
                  <p className="font-semibold">3. Run</p>
                  <p className="text-sm text-gray-400">Your new agent</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Quick Start */}
        <section className="mb-20">
          <div className="flex items-center gap-3 mb-8">
            <Zap className="w-6 h-6 text-yellow-400" />
            <h2 className="text-3xl font-bold">Getting Started</h2>
            <span className="text-sm text-gray-500 bg-gray-800 px-3 py-1 rounded-full">2 Simple Methods</span>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <div className="group bg-gradient-to-br from-purple-500/5 to-transparent rounded-xl p-6 border border-purple-500/20 hover:border-purple-500/40 transition-all">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-purple-500/20 rounded-lg group-hover:bg-purple-500/30 transition-colors">
                    <Mouse className="w-5 h-5 text-purple-400" />
                  </div>
                  <h3 className="text-lg font-semibold">Method 1: Local Files</h3>
                </div>
                <span className="text-xs text-purple-400 bg-purple-500/10 px-2 py-1 rounded">Recommended</span>
              </div>
              <ol className="space-y-3">
                <li className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-purple-500/20 text-purple-400 rounded-full flex items-center justify-center text-xs font-bold">1</span>
                  <div>
                    <p className="font-medium">Run Setup</p>
                    <code className="text-xs bg-gray-800 px-2 py-1 rounded mt-1 inline-block">co init</code>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-purple-500/20 text-purple-400 rounded-full flex items-center justify-center text-xs font-bold">2</span>
                  <div>
                    <p className="font-medium">Open Cursor AI</p>
                    <p className="text-xs text-gray-500 mt-1">In your project folder</p>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-purple-500/20 text-purple-400 rounded-full flex items-center justify-center text-xs font-bold">3</span>
                  <div>
                    <p className="font-medium">Drag File to Chat</p>
                    <code className="text-xs bg-gray-800 px-2 py-1 rounded mt-1 inline-block break-all">.co/docs/co-vibecoding-*.md</code>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-purple-500/20 text-purple-400 rounded-full flex items-center justify-center text-xs font-bold">4</span>
                  <div>
                    <p className="font-medium">Ask Cursor</p>
                    <p className="text-xs text-gray-400 mt-1">"Create an agent for..."</p>
                  </div>
                </li>
              </ol>
            </div>

            <div className="group bg-gradient-to-br from-pink-500/5 to-transparent rounded-xl p-6 border border-gray-700 hover:border-pink-500/40 transition-all">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-pink-500/20 rounded-lg group-hover:bg-pink-500/30 transition-colors">
                    <Copy className="w-5 h-5 text-pink-400" />
                  </div>
                  <h3 className="text-lg font-semibold">Method 2: Copy from Web</h3>
                </div>
                <span className="text-xs text-gray-400 bg-gray-800 px-2 py-1 rounded">Quick</span>
              </div>
              <ol className="space-y-3">
                <li className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-pink-500/20 text-pink-400 rounded-full flex items-center justify-center text-xs font-bold">1</span>
                  <div>
                    <p className="font-medium">Visit Docs</p>
                    <a href="https://docs.connectonion.com" className="text-xs text-pink-400 hover:text-pink-300 mt-1 inline-block">docs.connectonion.com</a>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-pink-500/20 text-pink-400 rounded-full flex items-center justify-center text-xs font-bold">2</span>
                  <div>
                    <p className="font-medium">Click Purple Button</p>
                    <p className="text-xs text-gray-500 mt-1">"Copy All Docs"</p>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-pink-500/20 text-pink-400 rounded-full flex items-center justify-center text-xs font-bold">3</span>
                  <div>
                    <p className="font-medium">Open Cursor Chat</p>
                    <p className="text-xs text-gray-500 mt-1">CMD+L or CTRL+L</p>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-pink-500/20 text-pink-400 rounded-full flex items-center justify-center text-xs font-bold">4</span>
                  <div>
                    <p className="font-medium">Paste & Ask</p>
                    <p className="text-xs text-gray-400 mt-1">Describe your agent</p>
                  </div>
                </li>
              </ol>
            </div>
          </div>
        </section>

        {/* Live Demo */}
        <section className="mb-20">
          <div className="flex items-center gap-3 mb-8">
            <Target className="w-6 h-6 text-green-400" />
            <h2 className="text-3xl font-bold">Live Example</h2>
            <span className="text-sm text-green-400 bg-green-500/10 px-3 py-1 rounded-full border border-green-500/30">See it in action</span>
          </div>
          
          <div className="mb-8">
            <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg p-6 border border-purple-500/20">
              <p className="text-sm text-gray-400 mb-2">You ask Cursor:</p>
              <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 flex items-center gap-2">
                <ChevronRight className="w-5 h-5 text-purple-400" />
                <p className="text-lg font-mono text-purple-300">"Using ConnectOnion docs, create a calculator agent"</p>
              </div>
            </div>
          </div>

          <div className="mb-8">
            <p className="text-sm text-gray-400 mb-4">Cursor automatically generates:</p>
            <CodeBlock 
              code={`from connectonion import Agent

def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

# Create agent
calculator = Agent(
    "calculator",
    tools=[add, multiply],
    instructions="You are a helpful calculator"
)

# Use it
result = calculator.input("What is 5 plus 3?")
print(result)  # Output: "5 plus 3 equals 8"`}
              id="example-code"
            />
          </div>

          <div className="bg-gradient-to-br from-green-500/5 to-transparent rounded-lg p-6 border border-green-500/20">
            <div className="flex items-center gap-3 mb-4">
              <Sparkles className="w-5 h-5 text-green-400" />
              <h3 className="text-lg font-semibold text-green-300 flex items-center gap-2">
                <Sparkles className="w-5 h-5" />
                <span>The Magic Happens</span>
              </h3>
            </div>
            <p className="text-gray-400 mb-4">Your agent automatically:</p>
            <div className="grid md:grid-cols-3 gap-4">
              <div className="bg-gray-900/50 rounded-lg p-3 border border-gray-800">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-green-400">✅</span>
                  <span className="font-medium text-sm">Understands Context</span>
                </div>
                <p className="text-xs text-gray-500">"plus" → <code className="bg-gray-800 px-1 rounded">add()</code></p>
              </div>
              <div className="bg-gray-900/50 rounded-lg p-3 border border-gray-800">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-green-400">✅</span>
                  <span className="font-medium text-sm">Picks Right Tool</span>
                </div>
                <p className="text-xs text-gray-500">Automatically selects functions</p>
              </div>
              <div className="bg-gray-900/50 rounded-lg p-3 border border-gray-800">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-green-400">✅</span>
                  <span className="font-medium text-sm">Natural Responses</span>
                </div>
                <p className="text-xs text-gray-500">Speaks human, not code</p>
              </div>
            </div>
          </div>
        </section>

        {/* Prompt Examples */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-8">Prompt Templates</h2>
          <p className="text-gray-400 mb-8">Copy and customize these prompts for Cursor:</p>

          <div className="space-y-4">
            <div className="group bg-gradient-to-r from-purple-500/5 to-transparent rounded-xl p-6 border border-gray-700 hover:border-purple-500/30 transition-all">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-lg font-semibold mb-1 flex items-center gap-2">
                    <FaBullseye className="text-gray-400" />
                    <span>Basic Agent</span>
                  </h3>
                  <p className="text-sm text-gray-500">Perfect for getting started</p>
                </div>
                <button 
                  onClick={() => handleCopyCode('"Using ConnectOnion docs, create a calculator agent"', 'prompt-basic')}
                  className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                >
                  {copiedCode === 'prompt-basic' ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4 text-gray-400" />
                  )}
                </button>
              </div>
              <div className="bg-gray-900 rounded-lg p-3 border border-gray-800">
                <code className="text-sm text-purple-300">
                  "Using ConnectOnion docs, create a calculator agent"
                </code>
              </div>
            </div>

            <div className="group bg-gradient-to-r from-pink-500/5 to-transparent rounded-xl p-6 border border-gray-700 hover:border-pink-500/30 transition-all">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-lg font-semibold mb-1 flex items-center gap-2">
                    <FaRocket className="text-gray-400" />
                    <span>Web Scraper</span>
                  </h3>
                  <p className="text-sm text-gray-500">Extract data from websites</p>
                </div>
                <button 
                  onClick={() => handleCopyCode('"Using ConnectOnion docs, create an agent that can scrape product prices from e-commerce sites"', 'prompt-scraper')}
                  className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                >
                  {copiedCode === 'prompt-scraper' ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4 text-gray-400" />
                  )}
                </button>
              </div>
              <div className="bg-gray-900 rounded-lg p-3 border border-gray-800">
                <code className="text-sm text-pink-300">
                  "Using ConnectOnion docs, create an agent that can scrape product prices from e-commerce sites"
                </code>
              </div>
            </div>

            <div className="group bg-gradient-to-r from-green-500/5 to-transparent rounded-xl p-6 border border-gray-700 hover:border-green-500/30 transition-all">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-lg font-semibold mb-1 flex items-center gap-2">
                    <FaEnvelope className="text-gray-400" />
                    <span>Email Assistant</span>
                  </h3>
                  <p className="text-sm text-gray-500">Send automated emails</p>
                </div>
                <button 
                  onClick={() => handleCopyCode('"Using ConnectOnion docs, create an agent that sends email notifications when certain conditions are met"', 'prompt-email')}
                  className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                >
                  {copiedCode === 'prompt-email' ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4 text-gray-400" />
                  )}
                </button>
              </div>
              <div className="bg-gray-900 rounded-lg p-3 border border-gray-800">
                <code className="text-sm text-green-300">
                  "Using ConnectOnion docs, create an agent that sends email notifications when certain conditions are met"
                </code>
              </div>
            </div>

            <div className="group bg-gradient-to-r from-blue-500/5 to-transparent rounded-xl p-6 border border-gray-700 hover:border-blue-500/30 transition-all">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-lg font-semibold mb-1 flex items-center gap-2">
                    <FaLightbulb className="text-gray-400" />
                    <span>Custom Idea</span>
                  </h3>
                  <p className="text-sm text-gray-500">Describe your own agent</p>
                </div>
              </div>
              <div className="bg-gray-900 rounded-lg p-3 border border-gray-800">
                <code className="text-sm text-blue-300">
                  "Using ConnectOnion docs, create an agent that [describe what you want your agent to do]"
                </code>
              </div>
            </div>
          </div>
        </section>

        {/* Why It Works */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-8">Why This Works So Well</h2>

          <div className="grid md:grid-cols-2 gap-6">
            <div className="bg-gradient-to-br from-purple-500/10 to-transparent border border-purple-500/20 rounded-xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-purple-500/20 rounded-lg">
                  <BookOpen className="w-5 h-5 text-purple-400" />
                </div>
                <h3 className="text-lg font-semibold">Complete Context</h3>
              </div>
              <p className="text-sm text-gray-400 mb-4">Our docs contain everything Cursor needs:</p>
              <ul className="space-y-2">
                <li className="flex items-start gap-2">
                  <ChevronRight className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
                  <span className="text-sm">Full API documentation</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
                  <span className="text-sm">Working examples</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
                  <span className="text-sm">Best practices</span>
                </li>
              </ul>
            </div>

            <div className="bg-gradient-to-br from-pink-500/10 to-transparent border border-pink-500/20 rounded-xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-pink-500/20 rounded-lg">
                  <Zap className="w-5 h-5 text-pink-400" />
                </div>
                <h3 className="text-lg font-semibold">AI Understanding</h3>
              </div>
              <p className="text-sm text-gray-400 mb-4">Cursor's AI can:</p>
              <ul className="space-y-2">
                <li className="flex items-start gap-2">
                  <ChevronRight className="w-4 h-4 text-pink-400 mt-0.5 flex-shrink-0" />
                  <span className="text-sm">Generate complete code</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="w-4 h-4 text-pink-400 mt-0.5 flex-shrink-0" />
                  <span className="text-sm">Handle complex logic</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="w-4 h-4 text-pink-400 mt-0.5 flex-shrink-0" />
                  <span className="text-sm">Fix errors automatically</span>
                </li>
              </ul>
            </div>
          </div>
        </section>

        {/* Step by Step Guide */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-8">Step-by-Step Setup</h2>

          <div className="space-y-4">
            <div className="group bg-gray-900/50 border border-gray-700 hover:border-purple-500/30 rounded-xl p-6 transition-all">
              <div className="flex items-start gap-4">
                <span className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-purple-500/20 to-pink-500/20 text-purple-400 rounded-xl flex items-center justify-center font-bold">1</span>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-semibold text-lg">Install ConnectOnion</p>
                    <Terminal className="w-5 h-5 text-gray-500" />
                  </div>
                  <div className="bg-gray-800 rounded-lg p-3 font-mono text-sm">
                    <span className="text-gray-500 select-none">$ </span>
                    <span className="text-green-400">pip install connectonion</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">Takes about 10 seconds</p>
                </div>
              </div>
            </div>

            <div className="group bg-gray-900/50 border border-gray-700 hover:border-purple-500/30 rounded-xl p-6 transition-all">
              <div className="flex items-start gap-4">
                <span className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-purple-500/20 to-pink-500/20 text-purple-400 rounded-xl flex items-center justify-center font-bold">2</span>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-semibold text-lg">Initialize Project</p>
                    <Rocket className="w-5 h-5 text-gray-500" />
                  </div>
                  <div className="bg-gray-800 rounded-lg p-3 font-mono text-sm">
                    <span className="text-gray-500 select-none">$ </span>
                    <span className="text-green-400">co init</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">Creates .co/docs/ folder with all documentation</p>
                </div>
              </div>
            </div>

            <div className="group bg-gray-900/50 border border-gray-700 hover:border-purple-500/30 rounded-xl p-6 transition-all">
              <div className="flex items-start gap-4">
                <span className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-purple-500/20 to-pink-500/20 text-purple-400 rounded-xl flex items-center justify-center font-bold">3</span>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-semibold text-lg">Open Cursor AI</p>
                    <Code className="w-5 h-5 text-gray-500" />
                  </div>
                  <p className="text-sm text-gray-400">Open Cursor in your project folder</p>
                  <p className="text-xs text-gray-500 mt-2">Don't have Cursor? <a href="https://cursor.sh" className="text-purple-400 hover:text-purple-300">Download free</a></p>
                </div>
              </div>
            </div>

            <div className="group bg-gray-900/50 border border-gray-700 hover:border-purple-500/30 rounded-xl p-6 transition-all">
              <div className="flex items-start gap-4">
                <span className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-purple-500/20 to-pink-500/20 text-purple-400 rounded-xl flex items-center justify-center font-bold">4</span>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-semibold text-lg">Drag Documentation</p>
                    <Mouse className="w-5 h-5 text-gray-500" />
                  </div>
                  <p className="text-sm text-gray-400">Drag <code className="bg-gray-800 px-2 py-1 rounded text-xs">.co/docs/co-vibecoding-*.md</code> into Cursor chat</p>
                  <p className="text-xs text-gray-500 mt-2">This gives Cursor all the context it needs</p>
                </div>
              </div>
            </div>

            <div className="group bg-gray-900/50 border border-gray-700 hover:border-purple-500/30 rounded-xl p-6 transition-all">
              <div className="flex items-start gap-4">
                <span className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-purple-500/20 to-pink-500/20 text-purple-400 rounded-xl flex items-center justify-center font-bold">5</span>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-semibold text-lg">Describe Your Agent</p>
                    <Sparkles className="w-5 h-5 text-gray-500" />
                  </div>
                  <p className="text-sm text-gray-400">Tell Cursor what kind of agent you want to create</p>
                  <div className="bg-gray-800 rounded-lg p-3 mt-2">
                    <p className="text-xs text-purple-300">"Create an agent that..."</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="group bg-gray-900/50 border border-gray-700 hover:border-green-500/30 rounded-xl p-6 transition-all">
              <div className="flex items-start gap-4">
                <span className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-green-500/20 to-green-600/20 text-green-400 rounded-xl flex items-center justify-center font-bold">6</span>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-semibold text-lg">Run Your Agent!</p>
                    <Rocket className="w-5 h-5 text-green-400" />
                  </div>
                  <div className="bg-gray-800 rounded-lg p-3 font-mono text-sm">
                    <span className="text-gray-500 select-none">$ </span>
                    <span className="text-green-400">python agent.py</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-2 flex items-center gap-1">
                    <FaGift className="text-gray-400" />
                    <span>Congratulations! Your agent is live!</span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>


        {/* Final CTA */}
        <div className="mb-20">
          <div className="relative bg-gradient-to-br from-purple-500/10 via-pink-500/10 to-purple-500/10 rounded-2xl p-12 border border-purple-500/20 text-center overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-r from-purple-500/5 via-transparent to-pink-500/5 animate-pulse" />
            <Sparkles className="w-16 h-16 text-purple-400 mx-auto mb-6 relative" />
            <h2 className="text-3xl md:text-4xl font-bold mb-4 bg-gradient-to-r from-purple-400 via-pink-400 to-purple-400 bg-clip-text text-transparent relative">
              Ready to Build Your First Agent?
            </h2>
            <p className="text-xl text-gray-300 mb-8 relative max-w-2xl mx-auto">
              Join thousands of developers creating AI agents without writing complex code.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center relative">
              <button 
                onClick={() => handleCopyCode('pip install connectonion', 'install-cmd')}
                className="group flex items-center gap-3 px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 rounded-xl font-semibold transition-all transform hover:scale-105"
              >
                <Terminal className="w-5 h-5" />
                <span>Get Started Now</span>
                <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </button>
              <a 
                href="https://cursor.sh"
                target="_blank"
                rel="noopener noreferrer" 
                className="group flex items-center gap-3 px-6 py-3 bg-gray-800 hover:bg-gray-700 rounded-xl font-semibold transition-all border border-gray-700"
              >
                <Download className="w-5 h-5" />
                <span>Download Cursor</span>
                <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </a>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <ContentNavigation />
      </div>
    </div>
  )
}