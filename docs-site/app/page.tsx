'use client'

import { useState } from 'react'
import { Terminal, Play, ArrowRight, BookOpen, Code, Zap, Clock, Users, Activity, CheckCircle, AlertCircle, Github, Copy, Check, Sparkles, Rocket, FileCode, Package, GitBranch, MessageCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
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
    <main className="">
      {/* Hero Section - Mobile optimized */}
      <section className="min-h-[85vh] md:min-h-screen flex items-center justify-center px-4 md:px-6 py-6 md:py-12 relative overflow-hidden">
        {/* Bright gradient background for emotional relief */}
        <div className="absolute inset-0 bg-gradient-to-b from-purple-900/10 via-blue-900/5 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-tr from-purple-600/10 via-transparent to-blue-600/10" />
        
        {/* Single subtle glow effect */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-purple-500/10 rounded-full blur-3xl" />
        
        <div className="max-w-4xl mx-auto text-center relative z-10">
          {/* Subtle pain point intro - larger on mobile */}
          <p className="text-base md:text-base text-gray-400 mb-3">
            AI agents shouldn't need <span className="text-red-400">500 lines of boilerplate</span>
          </p>
          
          {/* Version badge - moved inline and smaller */}
          <span className="inline-block px-2 py-0.5 text-xs font-mono bg-purple-500/10 text-purple-400 rounded-full border border-purple-500/20 mb-3">
            v0.0.1b6 BETA
          </span>
          
          {/* Main Title - smaller on mobile */}
          <h1 className="text-4xl sm:text-5xl md:text-7xl font-bold text-white mb-2">
            ConnectOnion
          </h1>
          
          {/* Combined tagline and benefit - better mobile sizing */}
          <p className="text-lg sm:text-xl md:text-3xl text-gray-300 mb-2">
            The <span className="font-bold bg-gradient-to-r from-purple-300 via-purple-400 to-blue-400 bg-clip-text text-transparent">simplest</span> AI agent framework
          </p>
          <p className="text-base md:text-xl text-gray-300 mb-4 md:mb-6">
            Ship in <span className="text-white font-semibold">5 minutes</span>, not 5 days
          </p>
          
          {/* Install command - smaller on mobile */}
          <div className="mb-4 md:mb-5 max-w-md mx-auto">
            <div className="bg-black/60 backdrop-blur border border-gray-700 rounded-lg p-0.5 hover:border-purple-500/50 transition-all">
              <CommandBlock commands={['pip install connectonion']} />
            </div>
          </div>
          
          {/* CTAs - mobile optimized with full width primary */}
          <div className="flex flex-col gap-3 w-full max-w-sm mx-auto md:max-w-none md:flex-row md:justify-center md:items-center">
            <a 
              href="#vibe-coding" 
              className="relative group w-full md:w-auto"
            >
              <div className="absolute inset-0 bg-purple-600 rounded-lg blur-xl group-hover:bg-purple-500 transition-all opacity-50" />
              <div className="relative px-6 py-3 md:py-2.5 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-500 hover:to-purple-600 text-white font-medium rounded-lg transition-all flex items-center justify-center gap-2 shadow-lg">
                <Copy className="w-4 h-4" />
                Vibe Coding Now
              </div>
            </a>
            <div className="flex gap-4 justify-center">
              <a 
                href="https://github.com/wu-changxing/connectonion" 
                className="px-4 py-2.5 text-gray-400 hover:text-white transition-colors flex items-center gap-1.5"
              >
                <Github className="w-4 h-4" />
                <span className="hidden sm:inline">GitHub</span>
              </a>
              <a 
                href="https://discord.gg/4xfD9k8AUF" 
                className="px-4 py-2.5 text-gray-400 hover:text-white transition-colors flex items-center gap-1.5"
              >
                <MessageCircle className="w-4 h-4" />
                <span className="hidden sm:inline">Discord</span>
              </a>
            </div>
          </div>
        </div>
      </section>
      
      {/* Section 2: The Equation - Show don't tell */}

      <section className="py-16 md:py-20 px-6">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-8 md:mb-12">
            <h2 className="text-2xl md:text-4xl font-bold text-white mb-2 md:mb-3">How It Works</h2>
            <p className="text-base md:text-lg text-gray-400">It's just this simple:</p>
          </div>
          
          {/* Responsive Equation */}
          <div className="bg-gray-800/50 rounded-xl p-6 md:p-8 border border-gray-700">
            {/* Text equation - responsive */}
            <div className="text-center mb-6 md:mb-8">
              <code className="text-lg md:text-2xl font-mono text-white block">
                <span className="block md:inline">Agent =</span>
                <span className="block md:inline md:ml-2">Markdown + Functions</span>
              </code>
            </div>
            
            {/* Mobile: Vertical flow */}
            <div className="md:hidden space-y-4">
              <div className="flex items-center justify-between bg-gray-900/30 rounded-lg p-4">
                <div className="flex items-center gap-3">
                  <div className="text-2xl">📝</div>
                  <div>
                    <div className="font-semibold text-white">Markdown</div>
                    <div className="text-xs text-gray-500">your prompt</div>
                  </div>
                </div>
              </div>
              
              <div className="text-center text-lg text-gray-600">+</div>
              
              <div className="flex items-center justify-between bg-gray-900/30 rounded-lg p-4">
                <div className="flex items-center gap-3">
                  <div className="text-2xl">🔧</div>
                  <div>
                    <div className="font-semibold text-white">Functions</div>
                    <div className="text-xs text-gray-500">your tools</div>
                  </div>
                </div>
              </div>
              
              <div className="text-center text-lg text-gray-600">=</div>
              
              <div className="bg-purple-900/20 rounded-lg p-4 border border-purple-500/30">
                <div className="flex items-center justify-center gap-3">
                  <div className="text-2xl">🤖</div>
                  <div>
                    <div className="font-semibold text-white">Agent</div>
                    <div className="text-xs text-purple-400">AI assistant</div>
                  </div>
                </div>
              </div>
            </div>
            
            {/* Desktop: Horizontal flow */}
            <div className="hidden md:grid grid-cols-5 gap-2 items-center">
              <div className="text-center">
                <div className="text-4xl mb-2">📝</div>
                <div className="font-semibold text-white">Markdown</div>
                <div className="text-xs text-gray-500">prompt</div>
              </div>
              
              <div className="text-center text-2xl text-gray-600">+</div>
              
              <div className="text-center">
                <div className="text-4xl mb-2">🔧</div>
                <div className="font-semibold text-white">Functions</div>
                <div className="text-xs text-gray-500">tools</div>
              </div>
              
              <div className="text-center text-2xl text-gray-600">=</div>
              
              <div className="text-center p-4 bg-purple-900/20 rounded-lg border border-purple-500/30">
                <div className="text-4xl mb-2">🤖</div>
                <div className="font-semibold text-white">Agent</div>
                <div className="text-xs text-purple-400">AI</div>
              </div>
            </div>
          </div>
        </div>
      </section>
      
      {/* Section 3: Code Example - Cleaner */}
      <section className="py-20 px-6 bg-gray-900/20">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-8">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-3">Complete Example</h2>
            <p className="text-lg text-gray-400">This is all the code you need:</p>
          </div>
          
          <CodeWithResult 
            code={`from connectonion import Agent

# 1. Write your prompt
prompt = "You are a helpful assistant"

# 2. Define your function  
def calculate(expression: str) -> str:
    return str(eval(expression))

# 3. Create agent
agent = Agent(prompt, tools=[calculate])

# That's it! Use it:
result = agent.input("What's 42 * 17?")
print(result)  # "42 * 17 equals 714"`}
            result={`42 * 17 equals 714`}
          />
        </div>
      </section>

      {/* Section 4: See the Difference - Comparison */}
      <section className="py-16 md:py-20 px-6 bg-gray-900/20">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-8 md:mb-12">
            <h2 className="text-2xl md:text-4xl font-bold text-white mb-2 md:mb-3">See the Difference</h2>
            <p className="text-base md:text-lg text-gray-400">Same AI agent, different approach</p>
          </div>
          
          {/* Comparison Grid */}
          <div className="grid md:grid-cols-2 gap-6 md:gap-8">
            {/* Other Frameworks */}
            <div className="order-2 md:order-1">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-gray-400">Other Frameworks</h3>
                <span className="text-sm text-red-400 font-mono">~50 lines</span>
              </div>
              <div className="bg-gray-900/50 rounded-lg border border-gray-700 overflow-hidden">
                <div className="p-4 overflow-x-auto">
                  <SyntaxHighlighter 
                    language="python" 
                    style={monokai}
                    customStyle={{
                      background: 'transparent',
                      padding: 0,
                      margin: 0,
                      fontSize: '0.75rem',
                      lineHeight: '1.5'
                    }}
                    showLineNumbers={true}
                  >
{`from langchain.agents import Tool, AgentExecutor
from langchain.agents import create_react_agent
from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage
import json

# Define the calculation tool
def calculate_tool(expression: str) -> str:
    try:
        result = eval(expression)
        return json.dumps({"result": result})
    except Exception as e:
        return json.dumps({"error": str(e)})

# Create tool wrapper
tools = [
    Tool(
        name="Calculator",
        func=calculate_tool,
        description="Useful for mathematical calculations"
    )
]

# Setup prompt template
template = """You are a helpful assistant.

{history}
Human: {input}
{agent_scratchpad}
"""

prompt = PromptTemplate(
    input_variables=["history", "input", "agent_scratchpad"],
    template=template
)

# Initialize LLM
llm = OpenAI(temperature=0)

# Setup memory
memory = ConversationBufferMemory(
    memory_key="history",
    return_messages=True
)

# Create agent
agent = create_react_agent(
    llm=llm,
    tools=tools,
    prompt=prompt
)

# Create executor
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    verbose=True,
    handle_parsing_errors=True
)

# Finally use it
result = agent_executor.invoke({"input": "What's 42 * 17?"})
print(result["output"])`}
                  </SyntaxHighlighter>
                </div>
              </div>
            </div>
            
            {/* ConnectOnion */}
            <div className="order-1 md:order-2">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-green-400">ConnectOnion</h3>
                <span className="text-sm text-green-400 font-mono">8 lines ✨</span>
              </div>
              <div className="bg-gray-900/50 rounded-lg border border-green-500/30 overflow-hidden">
                <div className="p-4 overflow-x-auto">
                  <SyntaxHighlighter 
                    language="python" 
                    style={monokai}
                    customStyle={{
                      background: 'transparent',
                      padding: 0,
                      margin: 0,
                      fontSize: '0.875rem',
                      lineHeight: '1.7'
                    }}
                    showLineNumbers={true}
                  >
{`from connectonion import Agent

def calculate(expression: str) -> str:
    return str(eval(expression))

agent = Agent("You are a helpful assistant", 
              tools=[calculate])

result = agent.input("What's 42 * 17?")
print(result)`}
                  </SyntaxHighlighter>
                </div>
              </div>
            </div>
          </div>
          
          {/* Big Callout */}
          <div className="mt-8 md:mt-12 text-center">
            <div className="inline-block bg-gradient-to-r from-green-500/10 to-purple-500/10 rounded-lg px-6 py-4 border border-green-500/20">
              <p className="text-2xl md:text-3xl font-bold text-white mb-1">
                Same result, <span className="text-green-400">85% less code</span>
              </p>
              <p className="text-sm md:text-base text-gray-400">
                No boilerplate. No complexity. Just agents.
              </p>
            </div>
          </div>
        </div>
      </section>
      
      {/* Section 5: Vibe Coding - Stunning Design */}
      <section id="vibe-coding" className="py-20 px-6 relative overflow-hidden">
        {/* Background gradient effect */}
        <div className="absolute inset-0 bg-gradient-to-br from-purple-900/20 via-transparent to-blue-900/20" />
        
        <div className="max-w-5xl mx-auto relative">
          {/* Header with better typography */}
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 mb-6">
              <div className="h-px w-12 bg-gradient-to-r from-transparent to-purple-500" />
              <span className="text-purple-400 text-sm font-mono uppercase tracking-wider">AI-Powered Development</span>
              <div className="h-px w-12 bg-gradient-to-l from-transparent to-purple-500" />
            </div>
            
            <h2 className="text-4xl md:text-6xl font-black text-white mb-4">
              Vibe Coding Now
            </h2>
            <p className="text-xl text-gray-300 mb-8 max-w-2xl mx-auto">
              Copy our docs once. Your AI assistant writes perfect ConnectOnion code forever.
            </p>
            
            {/* AI Tools Grid - More Visual */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-3xl mx-auto mb-12">
              <div className="group relative">
                <div className="absolute inset-0 bg-purple-600/20 rounded-xl blur-xl group-hover:bg-purple-600/30 transition-all" />
                <div className="relative bg-gray-900/60 backdrop-blur border border-purple-500/30 rounded-xl p-4 hover:border-purple-500/50 transition-all">
                  <div className="text-2xl mb-2">🤖</div>
                  <div className="text-sm font-semibold text-purple-300">Claude Code</div>
                </div>
              </div>
              
              <div className="group relative">
                <div className="absolute inset-0 bg-blue-600/20 rounded-xl blur-xl group-hover:bg-blue-600/30 transition-all" />
                <div className="relative bg-gray-900/60 backdrop-blur border border-blue-500/30 rounded-xl p-4 hover:border-blue-500/50 transition-all">
                  <div className="text-2xl mb-2">💻</div>
                  <div className="text-sm font-semibold text-blue-300">Cursor</div>
                </div>
              </div>
              
              <div className="group relative">
                <div className="absolute inset-0 bg-green-600/20 rounded-xl blur-xl group-hover:bg-green-600/30 transition-all" />
                <div className="relative bg-gray-900/60 backdrop-blur border border-green-500/30 rounded-xl p-4 hover:border-green-500/50 transition-all">
                  <div className="text-2xl mb-2">🚀</div>
                  <div className="text-sm font-semibold text-green-300">GitHub Copilot</div>
                </div>
              </div>
              
              <div className="group relative">
                <div className="absolute inset-0 bg-orange-600/20 rounded-xl blur-xl group-hover:bg-orange-600/30 transition-all" />
                <div className="relative bg-gray-900/60 backdrop-blur border border-orange-500/30 rounded-xl p-4 hover:border-orange-500/50 transition-all">
                  <div className="text-2xl mb-2">💬</div>
                  <div className="text-sm font-semibold text-orange-300">ChatGPT</div>
                </div>
              </div>
            </div>
          </div>
          
          {/* The Big CTA - Maximum Impact */}
          <div className="text-center mb-16">
            <div className="relative inline-block">
              {/* Glow effect */}
              <div className="absolute inset-0 bg-purple-600/50 blur-2xl" />
              
              {/* Button */}
              <button
                onClick={copyAllDocs}
                className="relative px-12 py-5 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white font-bold text-xl rounded-xl shadow-2xl transition-all transform hover:scale-105 inline-flex items-center gap-3"
              >
                {copyAllStatus === 'done' ? (
                  <>
                    <Check className="w-6 h-6 animate-bounce" />
                    <span>Documentation Copied!</span>
                    <Sparkles className="w-6 h-6 animate-pulse" />
                  </>
                ) : (
                  <>
                    <Copy className="w-6 h-6" />
                    <span>Copy All Documentation</span>
                    <ArrowRight className="w-6 h-6" />
                  </>
                )}
              </button>
            </div>
            
            <p className="text-sm text-gray-400 mt-4 font-mono">
              One click • Full context • Start immediately
            </p>
          </div>
          
          {/* Process Steps - Clean and Simple */}
          <div className="grid md:grid-cols-3 gap-8 max-w-4xl mx-auto">
            <div className="text-center group">
              <div className="w-16 h-16 bg-gradient-to-br from-purple-600/20 to-purple-600/10 rounded-2xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <span className="text-2xl font-bold text-purple-400">1</span>
              </div>
              <h3 className="font-bold text-white mb-2">Copy Documentation</h3>
              <p className="text-sm text-gray-400">Click the button above</p>
            </div>
            
            <div className="text-center group">
              <div className="w-16 h-16 bg-gradient-to-br from-blue-600/20 to-blue-600/10 rounded-2xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <span className="text-2xl font-bold text-blue-400">2</span>
              </div>
              <h3 className="font-bold text-white mb-2">Paste to Your AI</h3>
              <p className="text-sm text-gray-400">Any AI coding assistant</p>
            </div>
            
            <div className="text-center group">
              <div className="w-16 h-16 bg-gradient-to-br from-green-600/20 to-green-600/10 rounded-2xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <span className="text-2xl font-bold text-green-400">3</span>
              </div>
              <h3 className="font-bold text-white mb-2">Start Building</h3>
              <p className="text-sm text-gray-400">AI writes perfect code</p>
            </div>
          </div>
          
          {/* Bottom tagline */}
          <div className="text-center mt-12">
            <p className="text-gray-500 text-sm">
              Direct access to the authors on Discord • Shape the framework with us
            </p>
          </div>
        </div>
      </section>

      {/* Section 5: Start Simple, Ship Production-Ready */}
      <section className="py-20 px-6 bg-gray-900/20">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-3">Start Simple, Ship Production-Ready</h2>
          <p className="text-lg text-gray-400">Zero setup complexity, full production capabilities</p>
        </div>

        {/* Key features in clean grid */}
        <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto mb-12">
          <div className="p-5 bg-gray-800/30 rounded-lg border border-gray-700">
            <div className="text-2xl mb-2">🎯</div>
            <h3 className="font-semibold text-white mb-1">Zero Setup</h3>
            <p className="text-sm text-gray-400">Functions become tools instantly</p>
          </div>
          
          <div className="p-5 bg-gray-800/30 rounded-lg border border-gray-700">
            <div className="text-2xl mb-2">🔍</div>
            <h3 className="font-semibold text-white mb-1">Debug Mode</h3>
            <p className="text-sm text-gray-400">@xray shows everything</p>
          </div>
          
          <div className="p-5 bg-gray-800/30 rounded-lg border border-gray-700">
            <div className="text-2xl mb-2">📊</div>
            <h3 className="font-semibold text-white mb-1">Auto History</h3>
            <p className="text-sm text-gray-400">Every interaction saved</p>
          </div>
        </div>

        {/* Detailed production features */}
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

      <section className="py-20 px-6 bg-gray-900/20">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-white mb-8">Join the Community</h2>
          
          <div className="grid md:grid-cols-2 gap-6 max-w-2xl mx-auto">
            <a 
              href="https://discord.gg/4xfD9k8AUF"
              target="_blank"
              rel="noopener noreferrer"
              className="p-6 bg-gray-800/30 rounded-lg border border-gray-700 hover:border-purple-500/50 transition-colors"
            >
              <MessageCircle className="w-10 h-10 text-purple-400 mb-3 mx-auto" />
              <h3 className="font-semibold text-white mb-1">Discord</h3>
              <p className="text-sm text-gray-400">Get help & share ideas</p>
            </a>
            
            <a 
              href="https://github.com/wu-changxing/connectonion"
              target="_blank"
              rel="noopener noreferrer"
              className="p-6 bg-gray-800/30 rounded-lg border border-gray-700 hover:border-blue-500/50 transition-colors"
            >
              <Github className="w-10 h-10 text-blue-400 mb-3 mx-auto" />
              <h3 className="font-semibold text-white mb-1">GitHub</h3>
              <p className="text-sm text-gray-400">Star & contribute</p>
            </a>
          </div>
        </div>
      </section>

      {/* Section 7: Final CTA - Simplified */}
      <section className="py-16 md:py-20 px-6">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-2xl md:text-3xl font-bold text-white mb-3 md:mb-4">Ready to Start?</h2>
          <p className="text-base md:text-lg text-gray-400 mb-6 md:mb-8">
            Build your first agent today
          </p>
          
          <CommandBlock commands={['pip install connectonion']} />
          
          <div className="mt-4 md:mt-6">
            <Link 
              href="/quickstart"
              className="text-sm text-gray-500 hover:text-white transition-colors"
            >
              View Documentation →
            </Link>
          </div>
        </div>
      </section>
    </main>
  )
}