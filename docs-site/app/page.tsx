'use client'

import { useState } from 'react'
import { Copy, Check, Terminal, Play, ArrowRight, BookOpen, Code, Zap, Clock, Users, Activity, CheckCircle, AlertCircle, Github } from 'lucide-react'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

export default function HomePage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [terminalOutput, setTerminalOutput] = useState<string[]>([])
  const [currentStep, setCurrentStep] = useState(1)
  const [activeExample, setActiveExample] = useState<'basic' | 'real' | 'production'>('basic')

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

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

  return (
    <main className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Docs Header */}
      <header className="mb-16">
        <div className="text-center max-w-4xl mx-auto">
          <h1 className="text-4xl md:text-6xl font-bold text-white mb-6">ConnectOnion</h1>
          <p className="text-xl md:text-2xl text-gray-300 mb-8 max-w-3xl mx-auto">
            The simplest way to build AI agents with Python functions
          </p>
          
          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-12">
            <Link 
              href="/quickstart"
              className="px-8 py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold rounded-lg transition-all duration-300 shadow-lg hover:shadow-xl flex items-center gap-2"
            >
              <Play className="w-5 h-5" />
              Get Started (5 min)
            </Link>
            
            <a
              href="https://github.com/connectonion/connectonion"
              target="_blank"
              rel="noopener noreferrer"
              className="px-8 py-4 bg-gray-800 hover:bg-gray-700 text-white font-semibold rounded-lg transition-colors border border-gray-600 flex items-center gap-2"
            >
              <Github className="w-5 h-5" />
              View on GitHub
            </a>
          </div>
          
          {/* Quick Feature Highlights */}
          <div className="grid md:grid-cols-3 gap-6 text-center">
            <div className="p-4 bg-gray-900/50 rounded-lg border border-gray-700">
              <div className="text-2xl mb-2">⚡</div>
              <div className="text-white font-semibold">2 Lines of Code</div>
              <div className="text-gray-400 text-sm">Turn any Python function into an AI tool</div>
            </div>
            <div className="p-4 bg-gray-900/50 rounded-lg border border-gray-700">
              <div className="text-2xl mb-2">🔍</div>
              <div className="text-white font-semibold">Built-in Debugging</div>
              <div className="text-gray-400 text-sm">@xray decorator shows agent thinking</div>
            </div>
            <div className="p-4 bg-gray-900/50 rounded-lg border border-gray-700">
              <div className="text-2xl mb-2">📊</div>
              <div className="text-white font-semibold">Auto Tracking</div>
              <div className="text-gray-400 text-sm">Automatic behavior recording and history</div>
            </div>
          </div>
        </div>
      </header>
        
      {/* Simple Installation */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Installation</h2>
        
        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden mb-8">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-2 border-b border-gray-700">
            <span className="text-sm text-gray-400 font-mono">Terminal</span>
            <button
              onClick={() => copyToClipboard('pip install connectonion==0.0.1', 'install-cmd')}
              className="text-gray-400 hover:text-white transition-colors p-1"
            >
              {copiedId === 'install-cmd' ? (
                <Check className="w-4 h-4 text-green-400" />
              ) : (
                <Copy className="w-4 h-4" />
              )}
            </button>
          </div>
          <div className="bg-black p-4 font-mono text-sm">
            <span className="text-green-400">$</span> <span className="text-white">pip install connectonion==0.0.1</span>
          </div>
        </div>
      </section>
      
      {/* Simple Example */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Simple Example</h2>
        
        <div className="mb-6 p-6 bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-500/30 rounded-xl">
          <div className="text-lg text-blue-100 text-center">
            <strong className="text-white">That's it!</strong> Agents need just: <strong className="text-blue-300">name</strong> + <strong className="text-purple-300">tools</strong> (your existing Python functions). Everything else is optional.
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden mb-8">
          <div className="flex items-center justify-between bg-gray-800 border-b border-gray-700 px-4 py-3">
            <span className="text-sm text-gray-400 font-mono">simple_example.py</span>
            <button
              onClick={() => copyToClipboard(`from connectonion import Agent\n\ndef get_weather(city: str) -> str:\n    """Get current weather for a city."""\n    return f"Weather in {city}: sunny, 72°F"\n\n# Create agent\nagent = Agent("assistant", tools=[get_weather])\n\n# Use the agent\nresponse = agent.run("What's the weather in NYC?")\nprint(response)  # Output: "Weather in NYC: sunny, 72°F"`, 'simple-example')}
              className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
            >
              {copiedId === 'simple-example' ? (
                <Check className="w-4 h-4 text-green-400" />
              ) : (
                <Copy className="w-4 h-4" />
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
                lineHeight: '1.5'
              }}
            >
{`from connectonion import Agent

def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"Weather in {city}: sunny, 72°F"

# Create agent
agent = Agent("assistant", tools=[get_weather])

# Use the agent
response = agent.run("What's the weather in NYC?")
print(response)  # Output: "Weather in NYC: sunny, 72°F"`}
            </SyntaxHighlighter>
          </div>
        </div>
      </section>



      {/* Next Steps */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Next Steps</h2>
        
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Link href="/prompts" className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-blue-500/50 transition-colors">
            <h3 className="font-semibold text-white mb-2">📝 System Prompts</h3>
            <p className="text-sm text-gray-400">Craft perfect agent personalities</p>
          </Link>
          
          <Link href="/xray" className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-purple-500/50 transition-colors">
            <h3 className="font-semibold text-white mb-2">🔍 Debugging</h3>
            <p className="text-sm text-gray-400">Debug with @xray decorator</p>
          </Link>
          
          <a href="https://github.com/connectonion/connectonion" className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-green-500/50 transition-colors">
            <h3 className="font-semibold text-white mb-2">🐙 GitHub</h3>
            <p className="text-sm text-gray-400">Source code and issues</p>
          </a>
          
          <a href="https://pypi.org/project/connectonion/" className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-orange-500/50 transition-colors">
            <h3 className="font-semibold text-white mb-2">📦 PyPI</h3>
            <p className="text-sm text-gray-400">Package releases</p>
          </a>
        </div>
      </section>

    </main>
  )
}