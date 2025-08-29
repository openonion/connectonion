'use client'

import { useState } from 'react'
import { Terminal, Play, ArrowRight, BookOpen, Code, Zap, Clock, Users, Activity, CheckCircle, AlertCircle, Github, Copy, Check, Sparkles, Rocket, FileCode, Package, GitBranch } from 'lucide-react'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { WaitlistSignup } from '../components/WaitlistSignup'
import { copyAllDocsToClipboard } from '../utils/copyAllDocs'
import { CommandBlock } from '../components/CommandBlock'
import CodeWithResult from '../components/CodeWithResult'

export default function HomePage() {
  const [isRunning, setIsRunning] = useState(false)
  const [terminalOutput, setTerminalOutput] = useState<string[]>([])
  const [currentStep, setCurrentStep] = useState(1)
  const [activeExample, setActiveExample] = useState<'basic' | 'real' | 'production'>('basic')
  const [copyAllStatus, setCopyAllStatus] = useState<'idle' | 'copying' | 'done'>('idle')
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const runQuickstart = async () => {
    setIsRunning(true)
    setTerminalOutput([])
    
    const steps = [
      '$ pip install connectonion',
      'Collecting connectonion...',
      'Successfully installed connectonion-0.2.0',
      '$ python quickstart.py',
      'Agent: "assistant" initialized with 1 tool',
      'User: "What is 42 * 17?"',
      'Tool: calculate("42 * 17") → "714"',
      'Agent: "The result is 714."',
      '✓ Complete in 0.23s'
    ]
    
    for (let i = 0; i < steps.length; i++) {
      await new Promise(resolve => setTimeout(resolve, i < 3 ? 800 : 600))
      setTerminalOutput(prev => [...prev, steps[i]])
    }
    
    setIsRunning(false)
  }

  const copyAllDocs = async () => {
    try {
      setCopyAllStatus('copying')
      const ok = await copyAllDocsToClipboard()
      setCopyAllStatus(ok ? 'done' : 'idle')
      setTimeout(() => setCopyAllStatus('idle'), 2000)
    } catch {
      setCopyAllStatus('idle')
    }
  }

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  return (
    <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-12 pt-12">
      {/* Hero Section - Refined */}
      <header className="mb-20">
        <div className="text-center max-w-5xl mx-auto">
          {/* Title with Version Badge */}
          <div className="flex items-center justify-center gap-3 mb-8">
            <h1 className="text-5xl md:text-7xl font-bold text-white">ConnectOnion</h1>
            <div className="flex flex-col gap-1">
              <span className="px-3 py-1 bg-purple-600/20 text-purple-400 text-sm font-semibold rounded-full border border-purple-500/30">
                v0.0.1b6
              </span>
              <span className="px-2 py-0.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white text-xs font-bold rounded-full text-center">
                BETA
              </span>
            </div>
          </div>
          
          {/* Main Tagline - Larger and Clearer */}
          <h2 className="text-3xl md:text-4xl font-semibold text-white mb-4">
            Keep simple things simple, make complicated things possible
          </h2>
          
          {/* Sub-tagline */}
          <p className="text-xl text-gray-300 mb-12 max-w-3xl mx-auto">
            The simplest way to build AI agents with Python functions
          </p>
          
          {/* Hero Value Proposition - Enhanced */}
          <div className="bg-gradient-to-r from-blue-600 via-purple-600 to-pink-600 rounded-3xl p-10 mb-12 max-w-4xl mx-auto shadow-2xl">
            <div className="flex items-center justify-center gap-4 mb-4">
              <Sparkles className="w-10 h-10 text-white animate-pulse" />
              <h3 className="text-4xl md:text-5xl font-bold text-white">2 Lines = AI Agent</h3>
              <Sparkles className="w-10 h-10 text-white animate-pulse" />
            </div>
            <p className="text-2xl text-white/90">
              Turn any Python function into an AI-powered tool instantly
            </p>
          </div>
          
          {/* Primary CTA Buttons - Better Layout */}
          <div className="flex flex-col md:flex-row gap-4 justify-center items-center mb-8">
            <Link 
              href="/quickstart"
              className="group btn-primary px-10 py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 shadow-xl hover:shadow-2xl flex items-center gap-3 text-lg font-semibold transition-all transform hover:scale-105"
            >
              <Rocket className="w-6 h-6 group-hover:rotate-12 transition-transform" />
              Get Started (2 min)
            </Link>
            
            <button
              onClick={copyAllDocs}
              className="group btn-primary px-10 py-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 shadow-xl hover:shadow-2xl flex items-center gap-3 text-lg font-semibold transition-all transform hover:scale-105"
            >
              {copyAllStatus === 'copying' ? (
                <>
                  <div className="w-6 h-6 border-3 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Copying Docs...</span>
                </>
              ) : copyAllStatus === 'done' ? (
                <>
                  <Check className="w-6 h-6 text-green-200" />
                  <span>Docs Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-6 h-6 group-hover:scale-110 transition-transform" />
                  <span>Copy All Docs</span>
                </>
              )}
            </button>
          </div>

          {/* Secondary CTA Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <a
              href="https://github.com/wu-changxing/connectonion"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary px-8 py-3 flex items-center gap-2 hover:scale-105 transition-transform"
            >
              <Github className="w-5 h-5" />
              Star on GitHub
            </a>
            
            <a
              href="https://discord.gg/4xfD9k8AUF"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary px-8 py-3 flex items-center gap-2 hover:scale-105 transition-transform"
            >
              💬 Join Discord Community
            </a>
          </div>
          
          {/* Helper Text */}
          <p className="text-sm text-gray-400 mt-6">
            Need AI help? Copy all docs and paste into ChatGPT, Claude, or any AI assistant
          </p>
        </div>
      </header>

      {/* The Simplest Example - Enhanced Presentation */}
      <section className="mb-24">
        <div className="text-center mb-10">
          <h2 className="text-4xl font-bold text-white mb-4">This is All You Need</h2>
          <p className="text-lg text-gray-300">Seriously. That's it. No boilerplate, no complex setup.</p>
        </div>
        
        <div className="max-w-5xl mx-auto">
          <CodeWithResult 
            code={`from connectonion import Agent

# Any function becomes an AI tool
def greet(name: str) -> str:
    """Greet someone warmly."""
    return f"Hello {name}! Welcome to ConnectOnion! 🎉"

# Create agent with your function
agent = Agent("assistant", tools=[greet])

# Use it
response = agent.input("Say hi to the world")
print(response)`}
            result={`Hello world! Welcome to ConnectOnion! 🎉`}
            className="shadow-2xl"
          />
        </div>
        
        <div className="text-center mt-10">
          <div className="inline-flex items-center gap-4 bg-gray-800/50 px-6 py-3 rounded-full border border-gray-700">
            <Package className="w-5 h-5 text-blue-400" />
            <span className="text-gray-300">Install:</span>
            <code className="bg-black/30 px-3 py-1 rounded text-blue-300 font-mono">pip install connectonion</code>
          </div>
        </div>
      </section>

      {/* Core Features - Enhanced Visual Design */}
      <section className="mb-24">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-bold text-white mb-4">
            Simple but <span className="text-gradient bg-gradient-to-r from-green-400 to-emerald-400 bg-clip-text text-transparent">Production Ready</span>
          </h2>
          <p className="text-lg text-gray-300">Everything you need for real-world applications</p>
        </div>
        
        <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          <div className="group hover:scale-105 transition-transform">
            <div className="bg-gradient-to-br from-blue-600/20 via-blue-600/10 to-transparent rounded-3xl p-10 border border-blue-500/30 hover:border-blue-400/50 transition-all h-full">
              <div className="text-6xl mb-6 group-hover:scale-110 transition-transform">🎯</div>
              <h3 className="text-2xl font-bold text-white mb-3">Functions = Tools</h3>
              <p className="text-gray-300">
                Your existing Python functions become AI tools automatically. No wrappers, no decorators needed.
              </p>
              <div className="mt-4 pt-4 border-t border-blue-500/20">
                <span className="text-xs text-blue-400 font-semibold">PRODUCTION READY</span>
              </div>
            </div>
          </div>
          
          <div className="group hover:scale-105 transition-transform">
            <div className="bg-gradient-to-br from-purple-600/20 via-purple-600/10 to-transparent rounded-3xl p-10 border border-purple-500/30 hover:border-purple-400/50 transition-all h-full">
              <div className="text-6xl mb-6 group-hover:scale-110 transition-transform">🔍</div>
              <h3 className="text-2xl font-bold text-white mb-3">See Everything</h3>
              <p className="text-gray-300">
                @xray decorator shows what your agent is thinking. Debug with complete transparency.
              </p>
              <div className="mt-4 pt-4 border-t border-purple-500/20">
                <span className="text-xs text-purple-400 font-semibold">BUILT-IN DEBUGGING</span>
              </div>
            </div>
          </div>
          
          <div className="group hover:scale-105 transition-transform">
            <div className="bg-gradient-to-br from-green-600/20 via-green-600/10 to-transparent rounded-3xl p-10 border border-green-500/30 hover:border-green-400/50 transition-all h-full">
              <div className="text-6xl mb-6 group-hover:scale-110 transition-transform">📊</div>
              <h3 className="text-2xl font-bold text-white mb-3">Auto History</h3>
              <p className="text-gray-300">
                Every interaction is automatically saved. Analyze, replay, and learn from agent behavior.
              </p>
              <div className="mt-4 pt-4 border-t border-green-500/20">
                <span className="text-xs text-green-400 font-semibold">AUDIT TRAIL</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Production Features Showcase - NEW SECTION */}
      <section className="mb-24">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-bold text-white mb-4">Production Features Built-In</h2>
          <p className="text-lg text-gray-300">Enterprise-grade capabilities without the complexity</p>
        </div>

        {/* CLI Feature Display */}
        <div className="mb-12 max-w-5xl mx-auto">
          <div className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-8 border border-gray-700">
            <div className="flex items-center gap-3 mb-6">
              <Terminal className="w-6 h-6 text-blue-400" />
              <h3 className="text-2xl font-bold text-white">Professional CLI</h3>
              <span className="px-3 py-1 bg-green-600/20 text-green-400 text-xs font-bold rounded-full border border-green-500/30">
                READY TO USE
              </span>
            </div>
            
            <div className="grid md:grid-cols-2 gap-6">
              <div className="bg-black/40 rounded-lg p-4 font-mono text-sm">
                <div className="text-gray-400 mb-2"># Initialize project with templates</div>
                <div className="text-green-400">$ co init --template meta-agent</div>
                <div className="text-gray-500 mt-2">
                  ✓ Created agent.py<br/>
                  ✓ Created prompt.md<br/>
                  ✓ Created .env.example<br/>
                  ✓ Ready to build!
                </div>
              </div>
              
              <div className="space-y-3">
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 text-green-400 mt-0.5" />
                  <div>
                    <p className="text-white font-semibold">Project Templates</p>
                    <p className="text-gray-400 text-sm">Meta-agent, Playwright, Custom templates</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 text-green-400 mt-0.5" />
                  <div>
                    <p className="text-white font-semibold">Environment Management</p>
                    <p className="text-gray-400 text-sm">Automatic .env setup and validation</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 text-green-400 mt-0.5" />
                  <div>
                    <p className="text-white font-semibold">Best Practices</p>
                    <p className="text-gray-400 text-sm">Gitignore, folder structure, config files</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Debugging Feature Display */}
        <div className="mb-12 max-w-5xl mx-auto">
          <div className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-8 border border-gray-700">
            <div className="flex items-center gap-3 mb-6">
              <Zap className="w-6 h-6 text-purple-400" />
              <h3 className="text-2xl font-bold text-white">@xray Debugging</h3>
              <span className="px-3 py-1 bg-purple-600/20 text-purple-400 text-xs font-bold rounded-full border border-purple-500/30">
                ZERO CONFIG
              </span>
            </div>
            
            <div className="grid md:grid-cols-2 gap-6">
              <div className="bg-black/40 rounded-lg p-4 font-mono text-sm">
                <div className="text-gray-400 mb-2"># Add one decorator</div>
                <div className="text-purple-400">@xray</div>
                <div className="text-blue-400">def process_data(data):</div>
                <div className="text-gray-300 ml-4">return analyze(data)</div>
                <div className="text-gray-500 mt-3">
                  🔍 Agent: assistant<br/>
                  🔍 Task: Process user data<br/>
                  🔍 Iteration: 1<br/>
                  🔍 Result: Success
                </div>
              </div>
              
              <div className="space-y-3">
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 text-purple-400 mt-0.5" />
                  <div>
                    <p className="text-white font-semibold">Real-time Insights</p>
                    <p className="text-gray-400 text-sm">See what your agent is thinking</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 text-purple-400 mt-0.5" />
                  <div>
                    <p className="text-white font-semibold">Iteration Tracking</p>
                    <p className="text-gray-400 text-sm">Monitor tool calls and decisions</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 text-purple-400 mt-0.5" />
                  <div>
                    <p className="text-white font-semibold">Performance Metrics</p>
                    <p className="text-gray-400 text-sm">Execution time and resource usage</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Error Handling & Recovery */}
        <div className="max-w-5xl mx-auto">
          <div className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-8 border border-gray-700">
            <div className="flex items-center gap-3 mb-6">
              <Activity className="w-6 h-6 text-orange-400" />
              <h3 className="text-2xl font-bold text-white">Automatic Recovery</h3>
              <span className="px-3 py-1 bg-orange-600/20 text-orange-400 text-xs font-bold rounded-full border border-orange-500/30">
                SELF-HEALING
              </span>
            </div>
            
            <div className="grid md:grid-cols-3 gap-4">
              <div className="bg-black/40 rounded-lg p-4">
                <div className="text-orange-400 font-bold mb-2">Retry Logic</div>
                <p className="text-gray-300 text-sm">Automatic retries with exponential backoff</p>
              </div>
              <div className="bg-black/40 rounded-lg p-4">
                <div className="text-orange-400 font-bold mb-2">Error Context</div>
                <p className="text-gray-300 text-sm">Rich error messages with actionable fixes</p>
              </div>
              <div className="bg-black/40 rounded-lg p-4">
                <div className="text-orange-400 font-bold mb-2">Graceful Degradation</div>
                <p className="text-gray-300 text-sm">Fallback strategies when tools fail</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Progressive Examples - Better Visual Hierarchy */}
      <section className="mb-24">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-bold text-white mb-4">Start Simple, Grow Powerful</h2>
          <p className="text-lg text-gray-300">ConnectOnion scales with your needs</p>
        </div>
        
        <div className="space-y-8 max-w-5xl mx-auto">
          {/* Level 1: Basic */}
          <div className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-8 border border-gray-700 hover:border-gray-600 transition-all">
            <div className="flex items-center gap-4 mb-6">
              <span className="px-4 py-2 bg-gradient-to-r from-green-600/30 to-green-500/30 text-green-300 font-bold rounded-full border border-green-500/50">
                Level 1: Basic
              </span>
              <span className="text-gray-400 flex items-center gap-2">
                <Clock className="w-4 h-4" />
                30 seconds to build
              </span>
            </div>
            
            <CodeWithResult 
              code={`from connectonion import Agent

def calculate(expression: str) -> str:
    """Evaluate a math expression."""
    return str(eval(expression))

agent = Agent("calculator", tools=[calculate])
response = agent.input("What's 15% of 240?")
print(response)`}
              result={`Let me calculate 15% of 240 for you.

15% of 240 = 0.15 × 240 = 36

The answer is 36.`}
              className="text-sm"
            />
          </div>
          
          {/* Level 2: Multiple Tools */}
          <div className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-8 border border-gray-700 hover:border-gray-600 transition-all">
            <div className="flex items-center gap-4 mb-6">
              <span className="px-4 py-2 bg-gradient-to-r from-blue-600/30 to-blue-500/30 text-blue-300 font-bold rounded-full border border-blue-500/50">
                Level 2: Multiple Tools
              </span>
              <span className="text-gray-400 flex items-center gap-2">
                <Zap className="w-4 h-4" />
                Agent orchestrates automatically
              </span>
            </div>
            
            <CodeWithResult 
              code={`from connectonion import Agent

def search(query: str) -> str:
    """Search for information."""
    # Simulated search
    return f"Python was created by Guido van Rossum in 1991"

def summarize(text: str, length: str = "short") -> str:
    """Summarize text."""
    if length == "short":
        return "Python: Created 1991 by Guido van Rossum"
    return text

agent = Agent("researcher", tools=[search, summarize])
response = agent.input("Who created Python? Give me a brief summary")
print(response)`}
              result={`I'll search for information about Python's creator and provide you with a brief summary.

Python was created by Guido van Rossum in 1991. 

Brief summary: Python: Created 1991 by Guido van Rossum`}
              className="text-sm"
            />
          </div>
          
          {/* Level 3: Production */}
          <div className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-8 border border-gray-700 hover:border-gray-600 transition-all">
            <div className="flex items-center gap-4 mb-6">
              <span className="px-4 py-2 bg-gradient-to-r from-purple-600/30 to-purple-500/30 text-purple-300 font-bold rounded-full border border-purple-500/50">
                Level 3: Production Ready
              </span>
              <span className="text-gray-400 flex items-center gap-2">
                <Code className="w-4 h-4" />
                With debugging and custom prompts
              </span>
            </div>
            
            <CodeWithResult 
              code={`from connectonion import Agent
from connectonion.decorators import xray

@xray  # See what your agent is thinking
def analyze_data(data: list[int]) -> dict:
    """Analyze numerical data."""
    return {
        "mean": sum(data) / len(data),
        "max": max(data),
        "min": min(data)
    }

agent = Agent(
    name="analyst",
    tools=[analyze_data],
    system_prompt="You are a helpful data analyst. Be concise.",
    max_iterations=10  # Control complexity
)

response = agent.input("Analyze these sales: [100, 150, 120, 180, 90]")
print(response)`}
              result={`I'll analyze the sales data for you.

Based on the analysis of your sales data [100, 150, 120, 180, 90]:
- Average sales: 128
- Highest sale: 180
- Lowest sale: 90

The sales show moderate variation with a 90-point range between min and max values.`}
              className="text-sm"
            />
          </div>
        </div>
      </section>

      {/* Philosophy Section - Enhanced */}
      <section className="mb-24">
        <div className="bg-gradient-to-br from-purple-900/20 via-blue-900/20 to-pink-900/20 rounded-3xl p-16 border border-purple-500/30 max-w-5xl mx-auto text-center shadow-2xl">
          <h2 className="text-4xl font-bold text-white mb-8">Our Philosophy</h2>
          <p className="text-3xl text-white mb-12 font-medium">
            "Keep simple things simple, make complicated things possible"
          </p>
          
          <div className="grid md:grid-cols-3 gap-10">
            <div className="bg-black/20 rounded-2xl p-6 border border-white/10">
              <div className="text-5xl font-bold text-blue-400 mb-3">2</div>
              <div className="text-lg text-gray-300">Lines to start</div>
            </div>
            <div className="bg-black/20 rounded-2xl p-6 border border-white/10">
              <div className="text-5xl font-bold text-green-400 mb-3">∞</div>
              <div className="text-lg text-gray-300">Possibilities</div>
            </div>
            <div className="bg-black/20 rounded-2xl p-6 border border-white/10">
              <div className="text-5xl font-bold text-purple-400 mb-3">0</div>
              <div className="text-lg text-gray-300">Boilerplate</div>
            </div>
          </div>
        </div>
      </section>

      {/* When You Need More - Better Icons */}
      <section className="mb-24">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-bold text-white mb-4">When You Need More</h2>
          <p className="text-lg text-gray-300">Advanced features that stay out of your way until you need them</p>
        </div>
        
        <div className="grid md:grid-cols-2 gap-6 max-w-5xl mx-auto">
          <div className="bg-gray-900/60 border border-gray-700 rounded-2xl p-8 hover:border-gray-600 transition-all">
            <div className="flex items-start gap-4 mb-4">
              <div className="p-3 bg-blue-600/20 rounded-xl">
                <FileCode className="w-6 h-6 text-blue-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-xl font-semibold text-white mb-2">Meta-Agent Template</h3>
                <p className="text-gray-400 text-sm mb-4">
                  Generate complete agents, tools, and tests automatically with our development assistant.
                </p>
                <CommandBlock commands={['co init  # Creates a full dev environment']} />
              </div>
            </div>
          </div>
          
          <div className="bg-gray-900/60 border border-gray-700 rounded-2xl p-8 hover:border-gray-600 transition-all">
            <div className="flex items-start gap-4 mb-4">
              <div className="p-3 bg-purple-600/20 rounded-xl">
                <Zap className="w-6 h-6 text-purple-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-xl font-semibold text-white mb-2">Custom System Prompts</h3>
                <p className="text-gray-400 text-sm mb-4">
                  Define agent personalities with inline strings or external files.
                </p>
                <code className="block bg-black/30 px-4 py-3 rounded-lg text-sm text-gray-300 font-mono">
                  system_prompt="prompts/expert.md"
                </code>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-900/60 border border-gray-700 rounded-2xl p-8 hover:border-gray-600 transition-all">
            <div className="flex items-start gap-4 mb-4">
              <div className="p-3 bg-green-600/20 rounded-xl">
                <Activity className="w-6 h-6 text-green-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-xl font-semibold text-white mb-2">Iteration Control</h3>
                <p className="text-gray-400 text-sm mb-4">
                  Prevent infinite loops and control agent complexity.
                </p>
                <code className="block bg-black/30 px-4 py-3 rounded-lg text-sm text-gray-300 font-mono">
                  max_iterations=10
                </code>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-900/60 border border-gray-700 rounded-2xl p-8 hover:border-gray-600 transition-all">
            <div className="flex items-start gap-4 mb-4">
              <div className="p-3 bg-orange-600/20 rounded-xl">
                <Terminal className="w-6 h-6 text-orange-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-xl font-semibold text-white mb-2">Custom LLM Providers</h3>
                <p className="text-gray-400 text-sm mb-4">
                  Use OpenAI, Anthropic, or any LLM provider you prefer.
                </p>
                <code className="block bg-black/30 px-4 py-3 rounded-lg text-sm text-gray-300 font-mono">
                  llm=CustomLLM()
                </code>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Quick Comparison - Enhanced */}
      <section className="mb-24">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-bold text-white mb-4">Why Developers Choose ConnectOnion</h2>
          <p className="text-lg text-gray-300">Compare the code, not the marketing</p>
        </div>
        
        <div className="bg-gradient-to-r from-green-900/30 to-emerald-900/30 border border-green-500/30 rounded-3xl p-10 max-w-5xl mx-auto shadow-2xl">
          <div className="grid md:grid-cols-2 gap-10">
            <div>
              <h3 className="text-xl font-semibold text-gray-400 mb-6 flex items-center gap-2">
                <span className="text-red-500">⚠️</span> Other Frameworks
              </h3>
              <ul className="space-y-4 text-gray-400">
                <li className="flex items-start gap-3">
                  <span className="text-red-400 mt-1">✗</span>
                  <span>50+ lines of boilerplate code</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-red-400 mt-1">✗</span>
                  <span>Complex class hierarchies to learn</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-red-400 mt-1">✗</span>
                  <span>Verbose configuration files</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-red-400 mt-1">✗</span>
                  <span>30+ minutes to first working agent</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-red-400 mt-1">✗</span>
                  <span>Debugging requires extensive logging</span>
                </li>
              </ul>
            </div>
            
            <div>
              <h3 className="text-xl font-semibold text-green-400 mb-6 flex items-center gap-2">
                <span className="text-green-400">✨</span> ConnectOnion
              </h3>
              <ul className="space-y-4 text-white">
                <li className="flex items-start gap-3">
                  <span className="text-green-400 mt-1">✓</span>
                  <span>2 lines to create an agent</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-green-400 mt-1">✓</span>
                  <span>Use your existing Python functions</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-green-400 mt-1">✓</span>
                  <span>Zero configuration required</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-green-400 mt-1">✓</span>
                  <span>60 seconds to first working agent</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-green-400 mt-1">✓</span>
                  <span>@xray decorator shows agent thinking</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Getting Started - Enhanced CTA */}
      <section className="mb-24">
        <div className="bg-gradient-to-br from-purple-900/40 via-pink-900/40 to-blue-900/40 border border-purple-500/30 rounded-3xl p-16 text-center max-w-5xl mx-auto shadow-2xl">
          <h2 className="text-4xl font-bold text-white mb-6">Ready to Build?</h2>
          <p className="text-2xl text-gray-200 mb-10">
            Join thousands of developers building AI agents the simple way
          </p>
          
          <div className="flex flex-col sm:flex-row gap-6 justify-center items-center">
            <Link 
              href="/quickstart"
              className="group btn-primary px-12 py-5 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 shadow-xl hover:shadow-2xl flex items-center gap-3 text-xl font-bold transition-all transform hover:scale-105"
            >
              <Play className="w-8 h-8 group-hover:rotate-12 transition-transform" />
              Start Building Now
            </Link>
            
            <Link 
              href="/tools"
              className="group btn-secondary px-12 py-5 flex items-center gap-3 text-xl hover:scale-105 transition-transform"
            >
              <Code className="w-8 h-8 group-hover:rotate-3 transition-transform" />
              Explore Examples
            </Link>
          </div>
          
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-6 text-gray-300">
            <div className="flex items-center gap-2">
              <Package className="w-5 h-5 text-blue-400" />
              <code className="bg-black/30 px-3 py-1 rounded font-mono">pip install connectonion</code>
            </div>
            <span className="hidden sm:block">•</span>
            <a href="https://github.com/wu-changxing/connectonion" className="flex items-center gap-2 hover:text-white transition-colors">
              <Github className="w-5 h-5" />
              GitHub
            </a>
            <span className="hidden sm:block">•</span>
            <a href="https://discord.gg/4xfD9k8AUF" className="flex items-center gap-2 hover:text-white transition-colors">
              💬 Discord
            </a>
          </div>
        </div>
      </section>

      {/* Waitlist */}
      <section className="mb-20">
        <WaitlistSignup />
      </section>

      {/* Footer Links - Enhanced */}
      <footer className="border-t border-gray-800 pt-12">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-6 mb-12">
          <Link href="/quickstart" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors group">
            <Rocket className="w-4 h-4 group-hover:rotate-12 transition-transform" />
            Quick Start
          </Link>
          <Link href="/tools" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors group">
            <Code className="w-4 h-4 group-hover:scale-110 transition-transform" />
            Build Tools
          </Link>
          <Link href="/prompts" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors group">
            <FileCode className="w-4 h-4 group-hover:rotate-3 transition-transform" />
            System Prompts
          </Link>
          <Link href="/xray" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors group">
            <Zap className="w-4 h-4 group-hover:scale-110 transition-transform" />
            Debugging
          </Link>
          <Link href="/llm_do" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors group">
            <GitBranch className="w-4 h-4 group-hover:rotate-12 transition-transform" />
            LLM Do Pattern
          </Link>
        </div>
        
        <div className="text-center">
          <p className="text-lg text-gray-400 font-medium">
            ConnectOnion - Keep simple things simple, make complicated things possible
          </p>
          <p className="text-sm text-gray-500 mt-2">
            © 2024 ConnectOnion. Built with ❤️ for developers who value simplicity.
          </p>
        </div>
      </footer>
    </main>
  )
}