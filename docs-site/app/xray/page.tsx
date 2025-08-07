'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Bug, Eye, Play, Terminal, Clock, Zap, Copy, Check, ArrowRight, Search, Database, Code, Activity } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'
import Link from 'next/link'
// React Icons
import { FaPython, FaRobot, FaBug, FaEye, FaClock, FaCode, FaFileCode, FaNetworkWired, FaChartLine, FaBrain } from 'react-icons/fa'
import { BiBug, BiMessageDetail, BiHistory, BiRefresh, BiCodeBlock } from 'react-icons/bi'
import { MdOutlineTimeline, MdBugReport, MdOutlineSpeed, MdOutlineVisibility, MdOutlineDataObject } from 'react-icons/md'
import { RiFlowChart, RiNodeTree, RiBrainLine, RiSearchEyeLine } from 'react-icons/ri'
import { VscDebugAlt, VscOutput, VscSymbolMethod, VscWatch } from 'react-icons/vsc'
import { TbBraces, TbChartDots, TbStack, TbRoute } from 'react-icons/tb'

interface TraceStep {
  id: number
  function: string
  params: Record<string, any>
  result: string
  duration: number
  timestamp: number
}

export default function XrayPage() {
  const [activeDemo, setActiveDemo] = useState<'basic' | 'trace' | 'debug'>('basic')
  const [isRunning, setIsRunning] = useState(false)
  const [traceSteps, setTraceSteps] = useState<TraceStep[]>([])
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const runDemo = async (demoType: 'basic' | 'trace' | 'debug') => {
    setIsRunning(true)
    setActiveDemo(demoType)
    setTraceSteps([])

    // Simulate execution steps
    const steps: Omit<TraceStep, 'timestamp'>[] = demoType === 'trace' ? [
      { id: 1, function: 'search_database', params: { query: 'Python tutorials' }, result: 'Found 5 results for Python tutorials', duration: 89 },
      { id: 2, function: 'summarize_text', params: { text: 'Found 5 results...', max_words: 50 }, result: '5 Python tutorials found covering basics to advanced topics', duration: 234 }
    ] : [
      { id: 1, function: 'analyze_data', params: { text: 'sample data' }, result: 'Analysis complete', duration: 156 }
    ]

    for (const step of steps) {
      await new Promise(resolve => setTimeout(resolve, 800))
      setTraceSteps(prev => [...prev, { ...step, timestamp: Date.now() }])
    }

    setIsRunning(false)
  }

  const basicExample = `from connectonion.decorators import xray

@xray
def my_tool(text: str) -> str:
    """Process some text."""
    
    # Now you can see inside the agent's mind!
    print(xray.agent.name)    # "my_assistant"
    print(xray.task)          # "Process this document"
    print(xray.iteration)     # 1, 2, 3...
    
    return f"Processed: {text}"`

  const traceExample = `@xray
def analyze_data(text: str) -> str:
    """Analyze data and show execution trace."""
    
    # Show what happened so far
    xray.trace()
    
    return "Analysis complete"`

  const debugExample = `@xray
def analyze_sentiment(text: str) -> str:
    # 🎯 Set breakpoint on next line
    sentiment = "positive"  # When stopped here in debugger:
                           # >>> xray
                           # <XrayContext active>
                           #   agent: 'my_bot'
                           #   task: 'How do people feel about Python?'
    
    return sentiment`

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 text-white">
      {/* Hero Section */}
      <section className="relative overflow-hidden py-20">
        <div className="container mx-auto px-6">
          <div className="text-center max-w-4xl mx-auto">
            <div className="inline-flex items-center gap-3 bg-purple-900/20 border border-purple-500/30 rounded-full px-6 py-3 mb-8">
              <VscDebugAlt className="w-5 h-5 text-purple-400" />
              <span className="text-sm font-medium">Debug with @xray</span>
              <RiSearchEyeLine className="w-5 h-5 text-purple-300" />
            </div>
            
            <h1 className="text-4xl md:text-5xl font-bold mb-6 text-gray-100">
              <FaBrain className="inline mr-3 text-purple-400" />
              See what your AI agent is thinking
            </h1>
            
            <p className="text-xl text-gray-300 max-w-3xl mx-auto mb-12">
              Add one decorator and unlock debugging superpowers. No more black box AI.
            </p>
            
            {/* Visual Flow Diagram */}
            <div className="bg-gray-900 border border-gray-700 rounded-lg p-8 max-w-2xl mx-auto">
              <h3 className="text-lg font-semibold mb-6 flex items-center gap-2">
                <RiFlowChart className="text-blue-400" />
                How @xray works
              </h3>
              <div className="flex items-center justify-between text-sm">
                <div className="flex flex-col items-center gap-2">
                  <div className="w-12 h-12 bg-green-900/50 border border-green-500 rounded-lg flex items-center justify-center">
                    <FaPython className="text-green-400 w-6 h-6" />
                  </div>
                  <span className="text-gray-400">Your Function</span>
                </div>
                <ArrowRight className="text-gray-500" />
                <div className="flex flex-col items-center gap-2">
                  <div className="w-12 h-12 bg-purple-900/50 border border-purple-500 rounded-lg flex items-center justify-center">
                    <VscDebugAlt className="text-purple-400 w-6 h-6" />
                  </div>
                  <span className="text-gray-400">@xray decorator</span>
                </div>
                <ArrowRight className="text-gray-500" />
                <div className="flex flex-col items-center gap-2">
                  <div className="w-12 h-12 bg-blue-900/50 border border-blue-500 rounded-lg flex items-center justify-center">
                    <FaBrain className="text-blue-400 w-6 h-6" />
                  </div>
                  <span className="text-gray-400">Agent Context</span>
                </div>
                <ArrowRight className="text-gray-500" />
                <div className="flex flex-col items-center gap-2">
                  <div className="w-12 h-12 bg-yellow-900/50 border border-yellow-500 rounded-lg flex items-center justify-center">
                    <MdOutlineVisibility className="text-yellow-400 w-6 h-6" />
                  </div>
                  <span className="text-gray-400">Full Visibility</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Interactive Demo Section */}
      <section className="container mx-auto px-6 py-16">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-bold mb-8 flex items-center gap-3">
            <Activity className="w-8 h-8 text-purple-400" />
            Interactive Demo
          </h2>

          {/* Demo Tabs */}
          <div className="flex gap-4 mb-8">
            {[
              { id: 'basic', name: 'Basic Usage', icon: FaEye, color: 'text-green-400', bg: 'bg-green-900/20 border-green-500/30' },
              { id: 'trace', name: 'Execution Trace', icon: MdOutlineTimeline, color: 'text-blue-400', bg: 'bg-blue-900/20 border-blue-500/30' },
              { id: 'debug', name: 'IDE Debug', icon: VscDebugAlt, color: 'text-purple-400', bg: 'bg-purple-900/20 border-purple-500/30' }
            ].map(({ id, name, icon: Icon, color, bg }) => (
              <button
                key={id}
                onClick={() => setActiveDemo(id as any)}
                className={`px-6 py-3 rounded-lg font-medium flex items-center gap-3 border transition-all ${
                  activeDemo === id 
                    ? `${bg} border-opacity-100 text-white` 
                    : 'bg-gray-800 border-gray-600 hover:bg-gray-700 text-gray-300'
                }`}
              >
                <Icon className={`w-5 h-5 ${activeDemo === id ? color : 'text-gray-400'}`} />
                {name}
              </button>
            ))}
          </div>

          <div className="grid lg:grid-cols-2 gap-8">
            {/* Code Panel */}
            <div className="bg-gray-900 border border-gray-700 rounded-lg hover:border-gray-600 transition-colors">
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
                <div className="flex items-center gap-3">
                  <FaFileCode className="w-4 h-4 text-blue-400" />
                  <span className="text-sm text-gray-300 font-mono">
                    {activeDemo === 'basic' && 'basic_example.py'}
                    {activeDemo === 'trace' && 'trace_example.py'}
                    {activeDemo === 'debug' && 'debug_example.py'}
                  </span>
                  <div className="flex items-center gap-1 ml-2">
                    <FaPython className="w-3 h-3 text-yellow-400" />
                    <span className="text-xs text-gray-500">Python</span>
                  </div>
                </div>
                <button
                  onClick={() => copyToClipboard(
                    activeDemo === 'basic' ? basicExample :
                    activeDemo === 'trace' ? traceExample :
                    debugExample,
                    activeDemo
                  )}
                  className="text-gray-400 hover:text-white focus:text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-950 rounded p-1 transition-colors"
                  aria-label="Copy code"
                >
                  {copiedId === activeDemo ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4" aria-hidden="true" />
                  )}
                </button>
              </div>
              
              <div className="p-6 syntax-highlighter-wrapper">
                <SyntaxHighlighter 
                  language="python" 
                  style={vscDarkPlus}
                  customStyle={{
                    background: 'transparent',
                    padding: 0,
                    margin: 0,
                    fontSize: '0.875rem',
                    lineHeight: '1.5',
                    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Consolas, "Liberation Mono", Menlo, monospace'
                  }}
                  wrapLines={true}
                  wrapLongLines={true}
                >
                  {activeDemo === 'basic' ? basicExample :
                   activeDemo === 'trace' ? traceExample :
                   debugExample}
                </SyntaxHighlighter>
              </div>
              
              <div className="px-6 pb-6">
                <button
                  onClick={() => runDemo(activeDemo)}
                  disabled={isRunning}
                  className="w-full btn-primary text-white rounded-lg py-3 font-medium flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isRunning ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Running...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      Run Demo
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Output Panel */}
            <div className="bg-gray-900 border border-gray-700 rounded-lg">
              <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-700">
                <VscOutput className="w-4 h-4 text-green-400" />
                <span className="text-sm text-gray-300 font-mono">output</span>
                <div className="flex items-center gap-1 ml-2">
                  <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                  <span className="text-xs text-green-400">live</span>
                </div>
              </div>
              
              <div className="p-6 font-mono text-sm min-h-[400px] space-y-4">
                <AnimatePresence mode="wait">
                  {activeDemo === 'basic' && traceSteps.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="space-y-3"
                    >
                      <div className="flex items-center gap-2">
                        <FaRobot className="text-blue-400" />
                        <span className="text-green-400">Agent: my_assistant</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <BiMessageDetail className="text-yellow-400" />
                        <span className="text-green-400">Task: "Process this document"</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <BiRefresh className="text-purple-400" />
                        <span className="text-green-400">Iteration: 1</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <VscOutput className="text-cyan-400" />
                        <span className="text-purple-400">Processed: sample data</span>
                      </div>
                    </motion.div>
                  )}
                  
                  {activeDemo === 'trace' && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="space-y-3"
                    >
                      <div className="text-gray-200 font-bold">Task: "Find Python tutorials and summarize them"</div>
                      <div className="border-t border-gray-800 pt-3">
                        {traceSteps.map((step, index) => (
                          <motion.div
                            key={step.id}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: index * 0.3 }}
                            className="mb-4 space-y-1"
                          >
                            <div className="flex items-center gap-2">
                              <span className="text-purple-400">[{step.id}]</span>
                              <span className="text-gray-400">•</span>
                              <span className="text-green-400">{step.duration}ms</span>
                              <span className="text-blue-400">{step.function}({Object.entries(step.params).map(([k, v]) => `${k}="${v}"`).join(', ')})</span>
                            </div>
                            <div className="ml-8 text-gray-500">
                              IN  → {Object.entries(step.params).map(([k, v]) => `${k}: "${v}"`).join('\n      ')}
                            </div>
                            <div className="ml-8 text-gray-300">
                              OUT ← "{step.result}"
                            </div>
                          </motion.div>
                        ))}
                        
                        {traceSteps.length === 2 && (
                          <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.8 }}
                            className="border-t border-gray-800 pt-3 text-purple-400"
                          >
                            Total: {traceSteps.reduce((sum, step) => sum + step.duration, 0)}ms • {traceSteps.length} steps • 1 iteration
                          </motion.div>
                        )}
                      </div>
                    </motion.div>
                  )}
                  
                  {activeDemo === 'debug' && traceSteps.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="space-y-2"
                    >
                      <div className="text-red-400">🔴 Breakpoint hit at line 3</div>
                      <div className="text-gray-400">{'>>> xray'}</div>
                      <div className="text-green-400">{'<XrayContext active>'}</div>
                      <div className="text-blue-400 ml-2">agent: 'my_bot'</div>
                      <div className="text-blue-400 ml-2">task: 'How do people feel about Python?'</div>
                      <div className="text-gray-400">{'>>> xray.messages'}</div>
                      <div className="text-yellow-400">[{'{'}'role': 'user', 'content': 'How do people feel about Python?'{'}'}, ...]</div>
                    </motion.div>
                  )}
                  
                  {!isRunning && traceSteps.length === 0 && (
                    <div className="text-gray-500 italic">Click "Run Demo" to see xray in action...</div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* What You Can Access Section */}
      <section className="container mx-auto px-6 py-16">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-8 flex items-center gap-3">
            <MdOutlineDataObject className="w-8 h-8 text-purple-400" />
            What You Can Access
          </h2>
          
          {/* Visual API Map */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 mb-8">
            <div className="text-center mb-6">
              <h3 className="text-lg font-semibold flex items-center justify-center gap-2">
                <TbBraces className="text-blue-400" />
                xray context object
              </h3>
            </div>
            <div className="grid md:grid-cols-3 gap-4 text-sm">
              <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4 text-center">
                <FaRobot className="w-8 h-8 text-blue-400 mx-auto mb-2" />
                <div className="font-mono text-blue-300">xray.agent</div>
                <div className="text-gray-400 text-xs mt-1">Agent Instance</div>
              </div>
              <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-4 text-center">
                <BiMessageDetail className="w-8 h-8 text-green-400 mx-auto mb-2" />
                <div className="font-mono text-green-300">xray.task</div>
                <div className="text-gray-400 text-xs mt-1">User Request</div>
              </div>
              <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-4 text-center">
                <BiHistory className="w-8 h-8 text-purple-400 mx-auto mb-2" />
                <div className="font-mono text-purple-300">xray.messages</div>
                <div className="text-gray-400 text-xs mt-1">Chat History</div>
              </div>
            </div>
          </div>
          
          <div className="grid md:grid-cols-2 gap-6">
            {[
              { name: 'xray.agent', desc: 'The Agent instance calling this tool', icon: FaRobot, color: 'text-blue-400' },
              { name: 'xray.task', desc: 'Original request from user', icon: BiMessageDetail, color: 'text-green-400' },
              { name: 'xray.messages', desc: 'Full conversation history', icon: BiHistory, color: 'text-purple-400' },
              { name: 'xray.iteration', desc: 'Which round of tool calls (1-10)', icon: BiRefresh, color: 'text-yellow-400' },
              { name: 'xray.previous_tools', desc: 'Tools called before this one', icon: TbStack, color: 'text-cyan-400' },
              { name: 'xray.trace()', desc: 'Visual execution trace', icon: TbChartDots, color: 'text-pink-400' }
            ].map((item, i) => {
              const IconComponent = item.icon;
              return (
                <div
                  key={item.name}
                  className="bg-gray-900 border border-gray-700 rounded-lg p-6 hover:border-gray-600 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <div className={`p-2 rounded-lg bg-gray-800 ${item.color}`}>
                      <IconComponent className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className={`font-mono ${item.color} font-bold mb-2`}>{item.name}</h3>
                      <p className="text-gray-300">{item.desc}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Use Cases Section */}
      <section className="container mx-auto px-6 py-16">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-bold mb-8 flex items-center gap-3">
            <Zap className="w-8 h-8 text-purple-400" />
            Practical Use Cases
          </h2>
          
          <div className="grid lg:grid-cols-3 gap-8">
            {[
              {
                title: 'Understand Context',
                description: 'See why a tool was called and what led to it',
                code: `@xray
def emergency_shutdown():
    print(f"Shutdown: {xray.task}")
    print(f"After: {xray.previous_tools}")
    
    if xray.iteration == 1:
        return "Try restarting first"
    
    return "System shutdown complete"`
              },
              {
                title: 'Adaptive Behavior',
                description: 'Change tool behavior based on execution context',
                code: `@xray
def fetch_data(source: str) -> str:
    # Use cache on repeated calls
    if "fetch_data" in xray.previous_tools:
        return "Using cached data"
    
    # Fresh fetch on first call
    return f"Fresh data from {source}"`
              },
              {
                title: 'Debug Complex Flows',
                description: 'Get full visibility into multi-step agent processes',
                code: `@xray
def process_order(order_id: str) -> str:
    if xray.agent:
        print(f"Agent: {xray.agent.name}")
        print(f"Request: {xray.task}")
        print(f"Messages: {len(xray.messages)}")
    
    return f"Order {order_id} processed"`
              }
            ].map((useCase, i) => (
              <motion.div
                key={useCase.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                className="glass-subtle rounded-lg overflow-hidden card-hover"
              >
                <div className="p-6 border-b border-gray-800/50">
                  <h3 className="font-bold text-xl mb-2">{useCase.title}</h3>
                  <p className="text-gray-300">{useCase.description}</p>
                </div>
                <div className="syntax-highlighter-wrapper">
                  <SyntaxHighlighter 
                    language="python" 
                    style={vscDarkPlus}
                    customStyle={{
                      background: 'transparent',
                      padding: '1.5rem',
                      margin: 0,
                      fontSize: '0.8rem',
                      lineHeight: '1.4'
                    }}
                    wrapLines={true}
                  >
                    {useCase.code}
                  </SyntaxHighlighter>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Tips Section */}
      <section className="container mx-auto px-6 py-16">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-8">Pro Tips</h2>
          
          <div className="space-y-4">
            {[
              { icon: '🚀', tip: 'Development Only', detail: 'Remove @xray in production for best performance' },
              { icon: '🔍', tip: 'Combine with IDE', detail: 'Set breakpoints for interactive debugging' },
              { icon: '📊', tip: 'Use trace()', detail: 'Call xray.trace() after runs to see full flow' },
              { icon: '🛡️', tip: 'Check context', detail: 'Always verify xray.agent exists before using' }
            ].map((tip, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                whileInView={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
                className="flex items-start gap-4 glass-subtle rounded-lg p-4"
              >
                <span className="text-2xl">{tip.icon}</span>
                <div>
                  <h4 className="font-bold text-purple-400">{tip.tip}</h4>
                  <p className="text-gray-300">{tip.detail}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Next Steps */}
      <section className="container mx-auto px-6 py-16 pb-24">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="max-w-4xl mx-auto text-center"
        >
          <h2 className="text-3xl font-bold mb-8">Ready to debug like a pro?</h2>
          
          <div className="flex flex-wrap justify-center gap-4">
            {['Getting Started', 'Examples', 'API Reference'].map((item) => (
              <motion.button
                key={item}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="glass-subtle hover:glass rounded-lg px-6 py-3 flex items-center gap-2 transition-all duration-300"
              >
                {item}
                <ArrowRight className="w-4 h-4" />
              </motion.button>
            ))}
          </div>
        </motion.div>
      </section>
    </div>
  )
}