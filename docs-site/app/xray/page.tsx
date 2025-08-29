'use client'

import { motion } from 'framer-motion'
import { Zap, ArrowRight, Activity } from 'lucide-react'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'
import CodeWithResult from '../../components/CodeWithResult'
import Link from 'next/link'
// React Icons
import { FaPython, FaRobot, FaBug, FaEye, FaClock, FaCode, FaFileCode, FaNetworkWired, FaChartLine, FaBrain } from 'react-icons/fa'
import { BiBug, BiMessageDetail, BiHistory, BiRefresh, BiCodeBlock } from 'react-icons/bi'
import { MdOutlineTimeline, MdBugReport, MdOutlineSpeed, MdOutlineVisibility, MdOutlineDataObject } from 'react-icons/md'
import { RiFlowChart, RiNodeTree, RiBrainLine, RiSearchEyeLine } from 'react-icons/ri'
import { VscDebugAlt, VscOutput, VscSymbolMethod, VscWatch } from 'react-icons/vsc'
import { TbBraces, TbChartDots, TbStack, TbRoute } from 'react-icons/tb'

export default function XrayPage() {

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

      {/* Examples Section */}
      <section className="container mx-auto px-6 py-16">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-bold mb-8 flex items-center gap-3">
            <Activity className="w-8 h-8 text-purple-400" />
            Examples
          </h2>

          <div className="space-y-12">
            {/* Basic Usage */}
            <div>
              <h3 className="text-2xl font-bold mb-4 flex items-center gap-3">
                <FaEye className="w-6 h-6 text-green-400" />
                Basic Usage
              </h3>
              <p className="text-gray-300 mb-6">
                Add the @xray decorator to see inside the agent's mind. Access agent name, task, and iteration count.
              </p>
              <CodeWithResult 
                code={`from connectonion.decorators import xray

@xray
def my_tool(text: str) -> str:
    """Process some text."""
    
    # Now you can see inside the agent's mind!
    print(xray.agent.name)    # "my_assistant"
    print(xray.task)          # "Process this document"
    print(xray.iteration)     # 1, 2, 3...
    
    return f"Processed: {text}"`}
                result={`my_assistant
Process this document
1

Processed: sample data`}
                language="python"
              />
            </div>

            {/* Execution Trace */}
            <div>
              <h3 className="text-2xl font-bold mb-4 flex items-center gap-3">
                <MdOutlineTimeline className="w-6 h-6 text-blue-400" />
                Execution Trace
              </h3>
              <p className="text-gray-300 mb-6">
                Call xray.trace() to see the complete execution flow of your agent. Perfect for understanding multi-step processes.
              </p>
              <CodeWithResult 
                code={`@xray
def analyze_data(text: str) -> str:
    """Analyze data and show execution trace."""
    
    # Show what happened so far
    xray.trace()
    
    return "Analysis complete"`}
                result={`Task: "Find Python tutorials and summarize them"

[1] • 89ms • search_database(query="Python tutorials")
    IN  → query: "Python tutorials"
    OUT ← "Found 5 results for Python tutorials"

[2] • 234ms • summarize_text(text="Found 5 results...", max_words=50)
    IN  → text: "Found 5 results..."
          max_words: 50
    OUT ← "5 Python tutorials found covering basics to advanced topics"

Total: 323ms • 2 steps • 1 iteration

Analysis complete`}
                language="python"
              />
            </div>

            {/* IDE Debug */}
            <div>
              <h3 className="text-2xl font-bold mb-4 flex items-center gap-3">
                <VscDebugAlt className="w-6 h-6 text-purple-400" />
                IDE Debug
              </h3>
              <p className="text-gray-300 mb-6">
                Set breakpoints in your IDE and inspect the xray context. Access the full agent state including messages and previous tool calls.
              </p>
              <CodeWithResult 
                code={`@xray
def analyze_sentiment(text: str) -> str:
    # 🎯 Set breakpoint on next line
    sentiment = "positive"  # When stopped here in debugger:
                           # >>> xray
                           # <XrayContext active>
                           #   agent: 'my_bot'
                           #   task: 'How do people feel about Python?'
    
    return sentiment`}
                result={`🔴 Breakpoint hit at line 3

>>> xray
<XrayContext active>
  agent: 'my_bot'
  task: 'How do people feel about Python?'

>>> xray.messages
[{'role': 'user', 'content': 'How do people feel about Python?'}, ...]

>>> xray.previous_tools
['search_web', 'analyze_results']

positive`}
                language="python"
              />
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
          
          <div className="space-y-8">
            {/* Understand Context */}
            <div>
              <h3 className="font-bold text-xl mb-2">Understand Context</h3>
              <p className="text-gray-300 mb-4">See why a tool was called and what led to it</p>
              <CodeWithResult 
                code={`@xray
def emergency_shutdown():
    print(f"Shutdown: {xray.task}")
    print(f"After: {xray.previous_tools}")
    
    if xray.iteration == 1:
        return "Try restarting first"
    
    return "System shutdown complete"`}
                result={`Shutdown: Server is not responding, please help
After: ['check_server_status', 'restart_service']

System shutdown complete`}
              />
            </div>

            {/* Adaptive Behavior */}
            <div>
              <h3 className="font-bold text-xl mb-2">Adaptive Behavior</h3>
              <p className="text-gray-300 mb-4">Change tool behavior based on execution context</p>
              <CodeWithResult 
                code={`@xray
def fetch_data(source: str) -> str:
    # Use cache on repeated calls
    if "fetch_data" in xray.previous_tools:
        return "Using cached data"
    
    # Fresh fetch on first call
    return f"Fresh data from {source}"`}
                result={`# First call:
Fresh data from database

# Second call (same agent session):
Using cached data`}
              />
            </div>

            {/* Debug Complex Flows */}
            <div>
              <h3 className="font-bold text-xl mb-2">Debug Complex Flows</h3>
              <p className="text-gray-300 mb-4">Get full visibility into multi-step agent processes</p>
              <CodeWithResult 
                code={`@xray
def process_order(order_id: str) -> str:
    if xray.agent:
        print(f"Agent: {xray.agent.name}")
        print(f"Request: {xray.task}")
        print(f"Messages: {len(xray.messages)}")
    
    return f"Order {order_id} processed"`}
                result={`Agent: sales_assistant
Request: Process order ABC123 for customer
Messages: 5

Order ABC123 processed`}
              />
            </div>
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