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
    <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12 lg:py-16">
      {/* DESIGN FIX: Simplified Hero with Clear Hierarchy */}
      <header className="mb-24 text-center">
        <div className="max-w-4xl mx-auto">
          {/* DESIGN FIX: Single focal point - Title and Version */}
          <div className="mb-8">
            <div className="flex items-center justify-center gap-2 mb-4">
              <span className="px-3 py-1 bg-purple-500/10 text-purple-400 text-xs font-medium rounded-full border border-purple-500/20">
                v0.0.1b6
              </span>
              <span className="px-2 py-0.5 bg-purple-500 text-white text-xs font-bold rounded">
                BETA
              </span>
            </div>
            <h1 className="text-5xl md:text-7xl font-bold text-white mb-6">
              ConnectOnion
            </h1>
          </div>
          
          {/* DESIGN FIX: Clear hierarchy - Philosophy as H2 */}
          <h2 className="text-2xl md:text-3xl font-medium text-gray-200 mb-4 leading-relaxed">
            Keep simple things simple,<br />
            make complicated things possible
          </h2>
          
          {/* DESIGN FIX: Supporting text smaller and muted */}
          <p className="text-lg text-gray-400 mb-12">
            The simplest way to build AI agents with Python functions
          </p>
          
          {/* DESIGN FIX: Single hero message - consistent color scheme */}
          <div className="bg-gradient-to-br from-purple-500/10 to-blue-500/10 rounded-2xl p-8 mb-12 border border-purple-500/20">
            <div className="flex items-center justify-center gap-3 mb-2">
              <Sparkles className="w-8 h-8 text-purple-400" />
              <h3 className="text-3xl md:text-4xl font-bold text-white">
                2 Lines = AI Agent
              </h3>
              <Sparkles className="w-8 h-8 text-purple-400" />
            </div>
            <p className="text-lg text-gray-300">
              Turn any Python function into an AI-powered tool instantly
            </p>
          </div>
          
          {/* DESIGN FIX: Simplified CTA - Primary and Secondary only */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Link 
              href="/quickstart"
              className="px-8 py-3 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg shadow-lg hover:shadow-xl transition-all flex items-center gap-2"
            >
              <Rocket className="w-5 h-5" />
              Get Started
            </Link>
            
            <button
              onClick={copyAllDocs}
              className="px-8 py-3 bg-gray-800 hover:bg-gray-700 text-white font-medium rounded-lg border border-gray-700 transition-all flex items-center gap-2"
            >
              {copyAllStatus === 'done' ? (
                <>
                  <Check className="w-5 h-5 text-green-400" />
                  <span>Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-5 h-5" />
                  <span>Copy All Docs</span>
                </>
              )}
            </button>
            
            <a
              href="https://github.com/wu-changxing/connectonion"
              target="_blank"
              rel="noopener noreferrer"
              className="px-8 py-3 text-gray-400 hover:text-white font-medium transition-all flex items-center gap-2"
            >
              <Github className="w-5 h-5" />
              GitHub
            </a>
          </div>
        </div>
      </header>

      {/* DESIGN FIX: Clear content sections with consistent spacing */}
      
      {/* The Simplest Example */}
      <section className="mb-32">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-white mb-3">This is All You Need</h2>
          <p className="text-gray-400">No boilerplate. No complexity. Just functions.</p>
        </div>
        
        <div className="max-w-4xl mx-auto">
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
          />
        </div>
        
        {/* DESIGN FIX: Subtle install hint */}
        <div className="text-center mt-8">
          <code className="text-sm text-gray-500 bg-gray-900 px-3 py-1 rounded">
            pip install connectonion
          </code>
        </div>
      </section>

      {/* DESIGN FIX: Consistent three-column feature grid */}
      <section className="mb-32">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-white mb-3">
            Simple but Production Ready
          </h2>
          <p className="text-gray-400">Everything you need for real-world applications</p>
        </div>
        
        <div className="grid md:grid-cols-3 gap-8">
          {/* DESIGN FIX: Consistent card design with subtle borders */}
          <div className="bg-gray-900/50 rounded-xl p-8 border border-gray-800 hover:border-gray-700 transition-all">
            <div className="text-5xl mb-4">🎯</div>
            <h3 className="text-xl font-bold text-white mb-2">Functions = Tools</h3>
            <p className="text-gray-400 text-sm mb-4">
              Your existing Python functions become AI tools automatically.
            </p>
            <span className="text-xs text-purple-400 font-medium">ZERO SETUP</span>
          </div>
          
          <div className="bg-gray-900/50 rounded-xl p-8 border border-gray-800 hover:border-gray-700 transition-all">
            <div className="text-5xl mb-4">🔍</div>
            <h3 className="text-xl font-bold text-white mb-2">Debug Everything</h3>
            <p className="text-gray-400 text-sm mb-4">
              @xray decorator shows exactly what your agent is thinking.
            </p>
            <span className="text-xs text-blue-400 font-medium">BUILT-IN</span>
          </div>
          
          <div className="bg-gray-900/50 rounded-xl p-8 border border-gray-800 hover:border-gray-700 transition-all">
            <div className="text-5xl mb-4">📊</div>
            <h3 className="text-xl font-bold text-white mb-2">Auto History</h3>
            <p className="text-gray-400 text-sm mb-4">
              Every interaction saved automatically for analysis.
            </p>
            <span className="text-xs text-green-400 font-medium">AUDIT READY</span>
          </div>
        </div>
      </section>

      {/* DESIGN FIX: Simplified Production Features */}
      <section className="mb-32">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-white mb-3">Production Features</h2>
          <p className="text-gray-400">Enterprise capabilities without enterprise complexity</p>
        </div>

        {/* DESIGN FIX: Two-column layout for features */}
        <div className="grid md:grid-cols-2 gap-8 max-w-5xl mx-auto">
          {/* CLI Tools */}
          <div className="bg-gray-900/50 rounded-xl p-6 border border-gray-800">
            <div className="flex items-center gap-3 mb-4">
              <Terminal className="w-5 h-5 text-purple-400" />
              <h3 className="text-lg font-bold text-white">Professional CLI</h3>
            </div>
            <div className="bg-black/50 rounded-lg p-4 mb-4 font-mono text-sm">
              <span className="text-green-400">$ co init</span>
              <div className="text-gray-500 mt-1">✓ Project ready in 5 seconds</div>
            </div>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center gap-2 text-gray-300">
                <CheckCircle className="w-4 h-4 text-green-400" />
                Project templates
              </li>
              <li className="flex items-center gap-2 text-gray-300">
                <CheckCircle className="w-4 h-4 text-green-400" />
                Environment management
              </li>
              <li className="flex items-center gap-2 text-gray-300">
                <CheckCircle className="w-4 h-4 text-green-400" />
                Best practices built-in
              </li>
            </ul>
          </div>

          {/* Debugging */}
          <div className="bg-gray-900/50 rounded-xl p-6 border border-gray-800">
            <div className="flex items-center gap-3 mb-4">
              <Zap className="w-5 h-5 text-purple-400" />
              <h3 className="text-lg font-bold text-white">@xray Debugging</h3>
            </div>
            <div className="bg-black/50 rounded-lg p-4 mb-4 font-mono text-sm">
              <span className="text-purple-400">@xray</span>
              <div className="text-blue-400">def process(data):</div>
              <div className="text-gray-500 mt-1">🔍 See everything</div>
            </div>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center gap-2 text-gray-300">
                <CheckCircle className="w-4 h-4 text-green-400" />
                Real-time insights
              </li>
              <li className="flex items-center gap-2 text-gray-300">
                <CheckCircle className="w-4 h-4 text-green-400" />
                Iteration tracking
              </li>
              <li className="flex items-center gap-2 text-gray-300">
                <CheckCircle className="w-4 h-4 text-green-400" />
                Performance metrics
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* DESIGN FIX: Progressive Complexity - Cleaner */}
      <section className="mb-32">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-white mb-3">Start Simple, Grow Powerful</h2>
          <p className="text-gray-400">ConnectOnion scales with your needs</p>
        </div>
        
        <div className="space-y-6 max-w-4xl mx-auto">
          {/* Level indicators with consistent styling */}
          <div className="bg-gray-900/30 rounded-xl p-6 border border-gray-800">
            <div className="flex items-center gap-3 mb-4">
              <span className="px-3 py-1 bg-green-500/20 text-green-400 text-xs font-bold rounded-full">
                BASIC
              </span>
              <span className="text-gray-500 text-sm">30 seconds</span>
            </div>
            <p className="text-gray-300 mb-4">Single function, single purpose</p>
            <code className="text-sm text-gray-400">
              Agent("calculator", tools=[calculate])
            </code>
          </div>
          
          <div className="bg-gray-900/30 rounded-xl p-6 border border-gray-800">
            <div className="flex items-center gap-3 mb-4">
              <span className="px-3 py-1 bg-blue-500/20 text-blue-400 text-xs font-bold rounded-full">
                ADVANCED
              </span>
              <span className="text-gray-500 text-sm">2 minutes</span>
            </div>
            <p className="text-gray-300 mb-4">Multiple tools working together</p>
            <code className="text-sm text-gray-400">
              Agent("researcher", tools=[search, analyze, summarize])
            </code>
          </div>
          
          <div className="bg-gray-900/30 rounded-xl p-6 border border-gray-800">
            <div className="flex items-center gap-3 mb-4">
              <span className="px-3 py-1 bg-purple-500/20 text-purple-400 text-xs font-bold rounded-full">
                PRODUCTION
              </span>
              <span className="text-gray-500 text-sm">Ready to deploy</span>
            </div>
            <p className="text-gray-300 mb-4">Full features with debugging and monitoring</p>
            <code className="text-sm text-gray-400">
              Agent("analyst", tools=[...], system_prompt="...", max_iterations=10)
            </code>
          </div>
        </div>
      </section>

      {/* DESIGN FIX: Clear Philosophy Statement */}
      <section className="mb-32">
        <div className="bg-gradient-to-br from-purple-900/10 to-blue-900/10 rounded-2xl p-12 border border-purple-500/20 text-center">
          <h2 className="text-3xl font-bold text-white mb-6">Our Philosophy</h2>
          <p className="text-2xl text-gray-200 mb-8 font-light italic">
            "Keep simple things simple, make complicated things possible"
          </p>
          
          <div className="grid grid-cols-3 gap-8 max-w-2xl mx-auto">
            <div>
              <div className="text-4xl font-bold text-purple-400">2</div>
              <div className="text-sm text-gray-400 mt-1">Lines to start</div>
            </div>
            <div>
              <div className="text-4xl font-bold text-blue-400">∞</div>
              <div className="text-sm text-gray-400 mt-1">Possibilities</div>
            </div>
            <div>
              <div className="text-4xl font-bold text-green-400">0</div>
              <div className="text-sm text-gray-400 mt-1">Boilerplate</div>
            </div>
          </div>
        </div>
      </section>

      {/* DESIGN FIX: Simplified comparison */}
      <section className="mb-32">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-white mb-3">Why Developers Choose ConnectOnion</h2>
          <p className="text-gray-400">Compare the code, not the marketing</p>
        </div>
        
        <div className="max-w-4xl mx-auto">
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <h3 className="text-lg font-semibold text-gray-500 mb-4">Other Frameworks</h3>
              <ul className="space-y-3 text-sm">
                <li className="flex items-start gap-2 text-gray-400">
                  <span className="text-red-400 mt-0.5">✗</span>
                  50+ lines of boilerplate
                </li>
                <li className="flex items-start gap-2 text-gray-400">
                  <span className="text-red-400 mt-0.5">✗</span>
                  Complex class hierarchies
                </li>
                <li className="flex items-start gap-2 text-gray-400">
                  <span className="text-red-400 mt-0.5">✗</span>
                  30+ minutes to first agent
                </li>
              </ul>
            </div>
            
            <div>
              <h3 className="text-lg font-semibold text-white mb-4">ConnectOnion</h3>
              <ul className="space-y-3 text-sm">
                <li className="flex items-start gap-2 text-gray-300">
                  <span className="text-green-400 mt-0.5">✓</span>
                  2 lines to create an agent
                </li>
                <li className="flex items-start gap-2 text-gray-300">
                  <span className="text-green-400 mt-0.5">✓</span>
                  Use existing Python functions
                </li>
                <li className="flex items-start gap-2 text-gray-300">
                  <span className="text-green-400 mt-0.5">✓</span>
                  60 seconds to working agent
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* DESIGN FIX: Single clear CTA */}
      <section className="mb-32">
        <div className="bg-gray-900/50 rounded-2xl p-12 text-center border border-gray-800">
          <h2 className="text-3xl font-bold text-white mb-4">Ready to Build?</h2>
          <p className="text-xl text-gray-300 mb-8">
            Join thousands of developers building AI agents the simple way
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Link 
              href="/quickstart"
              className="px-10 py-4 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg shadow-lg hover:shadow-xl transition-all flex items-center gap-2"
            >
              <Play className="w-6 h-6" />
              Start Building Now
            </Link>
            
            <Link 
              href="/tools"
              className="px-10 py-4 text-gray-400 hover:text-white font-medium transition-all flex items-center gap-2"
            >
              View Examples →
            </Link>
          </div>
        </div>
      </section>

      {/* Waitlist */}
      <section className="mb-20">
        <WaitlistSignup />
      </section>

      {/* DESIGN FIX: Clean footer */}
      <footer className="border-t border-gray-800 pt-12">
        <div className="flex flex-wrap gap-x-8 gap-y-2 justify-center mb-8 text-sm">
          <Link href="/quickstart" className="text-gray-400 hover:text-white transition-colors">
            Quick Start
          </Link>
          <Link href="/tools" className="text-gray-400 hover:text-white transition-colors">
            Tools
          </Link>
          <Link href="/prompts" className="text-gray-400 hover:text-white transition-colors">
            Prompts
          </Link>
          <Link href="/xray" className="text-gray-400 hover:text-white transition-colors">
            Debugging
          </Link>
          <Link href="/cli" className="text-gray-400 hover:text-white transition-colors">
            CLI
          </Link>
          <a href="https://github.com/wu-changxing/connectonion" className="text-gray-400 hover:text-white transition-colors">
            GitHub
          </a>
          <a href="https://discord.gg/4xfD9k8AUF" className="text-gray-400 hover:text-white transition-colors">
            Discord
          </a>
        </div>
        
        <div className="text-center text-sm text-gray-500">
          <p>ConnectOnion - Keep simple things simple, make complicated things possible</p>
          <p className="mt-2">© 2024 ConnectOnion</p>
        </div>
      </footer>
    </main>
  )
}