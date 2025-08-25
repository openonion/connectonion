'use client'

import { useState } from 'react'
import { Terminal, Play, ArrowRight, BookOpen, Code, Zap, Clock, Users, Activity, CheckCircle, AlertCircle, Github, Copy, Check } from 'lucide-react'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { WaitlistSignup } from '../components/WaitlistSignup'
import { copyAllDocsToClipboard } from '../utils/copyAllDocs'
import { CommandBlock } from '../components/CommandBlock'

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
    <main className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Docs Header */}
      <header className="mb-16">
        <div className="text-center max-w-4xl mx-auto">
          <div className="flex items-center justify-center gap-3 mb-4">
            <h1 className="text-4xl md:text-6xl font-bold text-white">ConnectOnion</h1>
          <span className="sr-only">Connect Onion AI Framework</span>
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 bg-purple-600/20 text-purple-400 text-sm font-semibold rounded-full border border-purple-500/30">
                v0.0.1b6
              </span>
              <span className="px-2 py-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white text-xs font-bold rounded-full">BETA</span>
            </div>
          </div>
          <p className="text-xl md:text-2xl text-gray-300 mb-4 max-w-3xl mx-auto">
            The simplest way to build AI agents with Python functions
          </p>
          <p className="text-lg text-gray-400 mb-8 max-w-2xl mx-auto">
            Connect Onion framework - Transform any Python function into a powerful AI tool. No complexity, just results.
          </p>
          
          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-6">
            <Link 
              href="/quickstart"
              className="px-8 py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold rounded-lg transition-all duration-300 shadow-lg hover:shadow-xl flex items-center gap-2"
            >
              <Play className="w-5 h-5" />
              Get Started (5 min)
            </Link>
            
            <a
              href="https://github.com/wu-changxing/connectonion"
              target="_blank"
              rel="noopener noreferrer"
              className="px-8 py-4 bg-gray-800 hover:bg-gray-700 text-white font-semibold rounded-lg transition-colors border border-gray-600 flex items-center gap-2"
            >
              <Github className="w-5 h-5" />
              View on GitHub
            </a>
            
            <a
              href="https://discord.gg/4xfD9k8AUF"
              target="_blank"
              rel="noopener noreferrer"
              className="px-8 py-4 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg transition-colors border border-indigo-500 flex items-center gap-2"
            >
              💬 Join Discord
            </a>
            
            <button
              onClick={copyAllDocs}
              className="px-8 py-4 bg-gradient-to-r from-emerald-600 to-blue-600 hover:from-emerald-700 hover:to-blue-700 text-white font-semibold rounded-lg transition-all duration-300 flex items-center gap-2"
            >
              {copyAllStatus === 'copying' ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Copy All Docs
                </>
              ) : copyAllStatus === 'done' ? (
                <>
                  <Check className="w-5 h-5 text-green-300" />
                  Copied All Docs
                </>
              ) : (
                <>
                  <Copy className="w-5 h-5" />
                  Copy All Docs
                </>
              )}
            </button>
          </div>
          
          {/* Helper Caption */}
          <div className="text-center mb-12">
            <p className="text-sm text-gray-400">
              Need help from AI? Copy all docs and paste into any AI assistant for comprehensive support.
            </p>
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
        
        <div className="mb-8">
          <CommandBlock 
            commands={['pip install connectonion']}
          />
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
              onClick={() => copyToClipboard(`from connectonion import Agent\n\ndef get_weather(city: str) -> str:\n    """Get current weather for a city."""\n    return f"Weather in {city}: sunny, 72°F"\n\n# Create agent\nagent = Agent("assistant", tools=[get_weather])\n\n# Use the agent\nresponse = agent.input("What's the weather in NYC?")\nprint(response)  # Output: "Weather in NYC: sunny, 72°F"`, 'simple-example')}
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
response = agent.input("What's the weather in NYC?")
print(response)  # Output: "Weather in NYC: sunny, 72°F"`}
            </SyntaxHighlighter>
          </div>
        </div>
      </section>

      {/* Best Agent Framework Comparison - SEO Section */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Why ConnectOnion is the Best Agent Framework</h2>
        
        <div className="bg-gradient-to-r from-green-900/20 to-emerald-900/20 border border-green-500/30 rounded-lg p-8 mb-8">
          <h3 className="text-2xl font-semibold text-white mb-4">🏆 Best Agent Framework Comparison</h3>
          
          <div className="overflow-x-auto">
            <table className="min-w-full text-left">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="py-3 px-4 text-gray-300">Feature</th>
                  <th className="py-3 px-4 text-green-400">ConnectOnion</th>
                  <th className="py-3 px-4 text-gray-400">LangChain</th>
                  <th className="py-3 px-4 text-gray-400">AutoGen</th>
                  <th className="py-3 px-4 text-gray-400">CrewAI</th>
                </tr>
              </thead>
              <tbody className="text-sm">
                <tr className="border-b border-gray-800">
                  <td className="py-3 px-4 text-gray-300">Setup Time</td>
                  <td className="py-3 px-4 text-green-300">✅ 60 seconds</td>
                  <td className="py-3 px-4 text-gray-400">30+ minutes</td>
                  <td className="py-3 px-4 text-gray-400">20+ minutes</td>
                  <td className="py-3 px-4 text-gray-400">15+ minutes</td>
                </tr>
                <tr className="border-b border-gray-800">
                  <td className="py-3 px-4 text-gray-300">Learning Curve</td>
                  <td className="py-3 px-4 text-green-300">✅ Just functions</td>
                  <td className="py-3 px-4 text-gray-400">Complex chains</td>
                  <td className="py-3 px-4 text-gray-400">Agent classes</td>
                  <td className="py-3 px-4 text-gray-400">Role system</td>
                </tr>
                <tr className="border-b border-gray-800">
                  <td className="py-3 px-4 text-gray-300">Code Required</td>
                  <td className="py-3 px-4 text-green-300">✅ 5 lines</td>
                  <td className="py-3 px-4 text-gray-400">50+ lines</td>
                  <td className="py-3 px-4 text-gray-400">30+ lines</td>
                  <td className="py-3 px-4 text-gray-400">40+ lines</td>
                </tr>
                <tr className="border-b border-gray-800">
                  <td className="py-3 px-4 text-gray-300">Type Safety</td>
                  <td className="py-3 px-4 text-green-300">✅ Built-in</td>
                  <td className="py-3 px-4 text-gray-400">Optional</td>
                  <td className="py-3 px-4 text-gray-400">Partial</td>
                  <td className="py-3 px-4 text-gray-400">Limited</td>
                </tr>
                <tr className="border-b border-gray-800">
                  <td className="py-3 px-4 text-gray-300">Debugging</td>
                  <td className="py-3 px-4 text-green-300">✅ @xray decorator</td>
                  <td className="py-3 px-4 text-gray-400">Verbose logging</td>
                  <td className="py-3 px-4 text-gray-400">Print statements</td>
                  <td className="py-3 px-4 text-gray-400">Basic logging</td>
                </tr>
                <tr>
                  <td className="py-3 px-4 text-gray-300">Production Ready</td>
                  <td className="py-3 px-4 text-green-300">✅ Yes</td>
                  <td className="py-3 px-4 text-gray-400">Yes (complex)</td>
                  <td className="py-3 px-4 text-gray-400">Beta</td>
                  <td className="py-3 px-4 text-gray-400">Yes</td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <p className="text-gray-300 mt-6 text-lg">
            <strong className="text-white">Verdict:</strong> ConnectOnion is the <strong className="text-green-400">best agent framework</strong> for 
            developers who value simplicity, speed, and maintainability. While other frameworks add layers of abstraction, 
            ConnectOnion proves that the best agent framework is the one that gets out of your way.
          </p>
        </div>
      </section>

      {/* Why Connect Onion? - SEO Section */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Why Choose Connect Onion Framework?</h2>
        
        <div className="prose prose-invert max-w-none mb-8">
          <p className="text-gray-300 text-lg leading-relaxed">
            <strong>ConnectOnion (Connect Onion)</strong> revolutionizes AI agent development by eliminating unnecessary complexity. 
            While other frameworks require complex class hierarchies and boilerplate code, Connect Onion lets you 
            build powerful AI agents using simple Python functions you already know how to write.
          </p>
          
          <div className="grid md:grid-cols-2 gap-8 mt-8">
            <div>
              <h3 className="text-xl font-semibold text-white mb-4">🧅 The Connect Onion Philosophy</h3>
              <p className="text-gray-300">
                Like peeling an onion, Connect Onion reveals layers of functionality without overwhelming complexity. 
                Start simple with basic functions, then progressively add capabilities as needed. ConnectOnion makes 
                connecting AI to your code as natural as calling a function.
              </p>
            </div>
            
            <div>
              <h3 className="text-xl font-semibold text-white mb-4">⚡ Connect Onion vs Traditional Frameworks</h3>
              <ul className="space-y-2 text-gray-300">
                <li className="flex items-start gap-2">
                  <span className="text-green-400">✓</span>
                  <span>No complex class inheritance - just functions</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-green-400">✓</span>
                  <span>Connect Onion auto-discovers tool schemas from type hints</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-green-400">✓</span>
                  <span>Built-in behavior tracking and debugging</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-green-400">✓</span>
                  <span>5-minute setup vs hours of configuration</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
        
        <div className="bg-gradient-to-r from-purple-900/20 to-pink-900/20 border border-purple-500/30 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-3">🚀 Get Started with Connect Onion in Seconds</h3>
          <p className="text-gray-300 mb-4">
            ConnectOnion is designed for developers who want to connect AI capabilities to their applications 
            without learning a new framework. If you can write a Python function, you can build an AI agent with Connect Onion.
          </p>
          <div className="flex gap-4">
            <code className="bg-black/30 px-3 py-1 rounded text-purple-300">pip install connectonion</code>
            <span className="text-gray-400">→</span>
            <span className="text-green-300">Start building in 60 seconds</span>
          </div>
        </div>
      </section>

      {/* Advanced Configuration */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Advanced Configuration</h2>
        
        <p className="text-gray-300 mb-6">
          ConnectOnion agents support multiple configuration options for different use cases:
        </p>

        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden mb-8">
          <div className="flex items-center justify-between bg-gray-800 border-b border-gray-700 px-4 py-3">
            <span className="text-sm text-gray-400 font-mono">advanced_config.py</span>
            <button
              onClick={() => copyToClipboard(`from connectonion import Agent

# Full configuration example
agent = Agent(
    name="advanced_assistant",
    model="gpt-5-mini",           # Model selection (default)
    api_key="sk-...",              # Optional API key
    system_prompt="Be concise",    # Custom personality
    tools=[calculate, search],    # Multiple tools
)

# Available Models:
# - gpt-5-nano: Fastest, most cost-effective
# - gpt-5-mini: Balanced performance (default)
# - gpt-5: Most capable, highest quality

# API Key Options:
# 1. Environment variable (recommended):
#    export OPENAI_API_KEY="sk-..."
# 2. Pass directly:
#    agent = Agent(api_key="sk-...")

# System Prompt Options:
# 1. Inline string:
#    system_prompt="You are helpful"
# 2. File path:
#    system_prompt="prompts/agent.md"
# 3. None (uses default):
#    system_prompt=None`, 'advanced-config')}
              className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
            >
              {copiedId === 'advanced-config' ? (
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

# Full configuration example
agent = Agent(
    name="advanced_assistant",
    model="gpt-5-mini",           # Model selection (default)
    api_key="sk-...",              # Optional API key
    system_prompt="Be concise",    # Custom personality
    tools=[calculate, search],    # Multiple tools
)

# Available Models:
# - gpt-5-nano: Fastest, most cost-effective
# - gpt-5-mini: Balanced performance (default)
# - gpt-5: Most capable, highest quality

# API Key Options:
# 1. Environment variable (recommended):
#    export OPENAI_API_KEY="sk-..."
# 2. Pass directly:
#    agent = Agent(api_key="sk-...")

# System Prompt Options:
# 1. Inline string:
#    system_prompt="You are helpful"
# 2. File path:
#    system_prompt="prompts/agent.md"
# 3. None (uses default):
#    system_prompt=None`}
            </SyntaxHighlighter>
          </div>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
            <h3 className="font-semibold text-white mb-2 flex items-center gap-2">
              <span className="text-2xl">🚀</span> Model Selection
            </h3>
            <p className="text-sm text-gray-400 mb-3">Choose based on your needs:</p>
            <ul className="text-sm space-y-1">
              <li className="text-green-300"><code>gpt-5-nano</code>: Fast responses</li>
              <li className="text-blue-300"><code>gpt-5-mini</code>: Balanced (default)</li>
              <li className="text-purple-300"><code>gpt-5</code>: Best quality</li>
            </ul>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
            <h3 className="font-semibold text-white mb-2 flex items-center gap-2">
              <span className="text-2xl">🔑</span> API Key Setup
            </h3>
            <p className="text-sm text-gray-400 mb-3">Two ways to configure:</p>
            <ul className="text-sm space-y-1">
              <li className="text-gray-300">• Environment variable</li>
              <li className="text-gray-300">• Direct parameter</li>
              <li className="text-gray-300">• Custom LLM provider</li>
            </ul>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
            <h3 className="font-semibold text-white mb-2 flex items-center gap-2">
              <span className="text-2xl">💬</span> System Prompts
            </h3>
            <p className="text-sm text-gray-400 mb-3">Define agent personality:</p>
            <ul className="text-sm space-y-1">
              <li className="text-gray-300">• Inline strings</li>
              <li className="text-gray-300">• External files (.md, .txt)</li>
              <li className="text-gray-300">• Dynamic loading</li>
            </ul>
          </div>
        </div>
      </section>

      {/* Waitlist Signup */}
      <section className="mb-16">
        <WaitlistSignup />
      </section>

      {/* FAQ Section for SEO */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Frequently Asked Questions about ConnectOnion</h2>
        
        <div className="space-y-6">
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-3">What is ConnectOnion (Connect Onion)?</h3>
            <p className="text-gray-300">
              ConnectOnion, also known as Connect Onion, is a Python framework that makes building AI agents incredibly simple. 
              Instead of complex class hierarchies, Connect Onion lets you create powerful AI agents using regular Python functions. 
              It's designed for developers who want to connect AI capabilities to their applications without learning a new framework.
            </p>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-3">Why is ConnectOnion the best agent framework?</h3>
            <p className="text-gray-300">
              ConnectOnion is considered the best agent framework because it eliminates complexity while maintaining power. 
              Unlike LangChain's complex chains or AutoGen's class hierarchies, ConnectOnion works with simple Python functions. 
              It's the best agent framework for developers who want to build production-ready AI agents in minutes, not hours.
            </p>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-3">How does Connect Onion compare to other agent frameworks?</h3>
            <p className="text-gray-300">
              Connect Onion stands out as the best agent framework by offering: 60-second setup vs 30+ minutes for competitors, 
              5 lines of code vs 50+ for LangChain, built-in debugging with @xray decorator, and automatic type safety. 
              ConnectOnion proves that the best agent framework is the simplest one that still gets the job done.
            </p>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-3">Can I use ConnectOnion with OpenAI's GPT models?</h3>
            <p className="text-gray-300">
              Yes! ConnectOnion (Connect Onion) is built to work seamlessly with OpenAI's GPT models including GPT-4, GPT-4 Turbo, 
              and GPT-3.5. Simply provide your OpenAI API key, and Connect Onion handles all the integration details. The framework 
              also supports custom LLM providers if you need to use other models.
            </p>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-3">How quickly can I build an agent with Connect Onion?</h3>
            <p className="text-gray-300">
              You can have a working AI agent in under 60 seconds with ConnectOnion. Install with <code className="bg-black/30 px-2 py-1 rounded">pip install connectonion</code>, 
              write a simple Python function, and create an agent with one line of code. Connect Onion's simplicity means you spend 
              time building features, not fighting with framework complexity.
            </p>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-3">Is ConnectOnion suitable for production use?</h3>
            <p className="text-gray-300">
              Absolutely! Connect Onion includes production-ready features like automatic behavior tracking, comprehensive error handling, 
              configurable iteration limits, and the @xray debugging decorator. Many developers use ConnectOnion in production for 
              customer support bots, data analysis agents, and automation workflows.
            </p>
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
          
          <a href="https://github.com/wu-changxing/connectonion" className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-green-500/50 transition-colors">
            <h3 className="font-semibold text-white mb-2">🐙 GitHub</h3>
            <p className="text-sm text-gray-400">Source code and issues</p>
          </a>
          
          <a href="https://pypi.org/project/connectonion/" className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-orange-500/50 transition-colors">
            <h3 className="font-semibold text-white mb-2">📦 PyPI</h3>
            <p className="text-sm text-gray-400">Package releases</p>
          </a>
          
          <a href="https://discord.gg/4xfD9k8AUF" className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-indigo-500/50 transition-colors">
            <h3 className="font-semibold text-white mb-2">💬 Discord</h3>
            <p className="text-sm text-gray-400">Join our community</p>
          </a>
        </div>
      </section>

    </main>
  )
}