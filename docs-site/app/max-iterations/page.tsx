'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ChevronLeft, Copy, Check, Zap, Settings, Brain, Gauge, Lightbulb } from 'lucide-react';

export default function MaxIterationsPage() {
  const [copiedSection, setCopiedSection] = useState<string | null>(null);

  const copyToClipboard = (text: string, section: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSection(section);
    setTimeout(() => setCopiedSection(null), 2000);
  };

  const examples = {
    basic: `from connectonion import Agent

# Default: 10 iterations (works for most tasks!)
agent = Agent("my_bot", tools=[search, calculate])

# That's it! Just use it:
result = agent.input("What's 2+2?")  # Uses 1 iteration
result = agent.input("Search for Python tutorials")  # Uses 1-2 iterations`,

    complex: `# Complex tasks need more iterations
research_agent = Agent(
    "researcher",
    tools=[search, analyze, summarize],
    max_iterations=25  # I need more attempts for complex research
)`,

    override: `# Normal agent
agent = Agent("helper", tools=[...])  # Default 10

# But this ONE task is complex:
result = agent.input(
    "Do something really complex",
    max_iterations=30  # Just for this task!
)`,

    calculator: `def calculate(expression: str) -> float:
    return eval(expression)  # Simple math

# Calculator rarely needs many attempts
calc_bot = Agent(
    "calculator",
    tools=[calculate],
    max_iterations=3  # Math is simple, 3 attempts is plenty
)

# This works fine with just 1 iteration:
result = calc_bot.input("What's 15 * 8?")
print(result)  # "The answer is 120"`,

    autoRetry: `def smart_input(agent, prompt, max_retries=3):
    """Automatically increases iterations if task fails."""
    limits = [10, 25, 50]  # Try these limits in order
    
    for limit in limits:
        result = agent.input(prompt, max_iterations=limit)
        if "Maximum iterations" not in result:
            return result  # Success!
    
    return "Task too complex even with 50 iterations"

# Use it:
agent = Agent("smart", tools=[...])
result = smart_input(agent, "Complex task")  # Auto-adjusts!`,

    selfAdjusting: `class SelfAdjustingAgent:
    """Agent that learns optimal iterations from history."""
    
    def __init__(self, name, tools):
        self.agent = Agent(name, tools, max_iterations=10)
        self.task_history = {}
    
    def input(self, prompt):
        # Start with learned limit or default
        task_type = self._classify_task(prompt)
        max_iter = self.task_history.get(task_type, 10)
        
        # Try with current limit
        result = self.agent.input(prompt, max_iterations=max_iter)
        
        # If failed, increase and retry
        while "Maximum iterations" in result and max_iter < 50:
            max_iter += 10
            print(f"Increasing to {max_iter} iterations...")
            result = self.agent.input(prompt, max_iterations=max_iter)
        
        # Remember what worked
        if "Maximum iterations" not in result:
            self.task_history[task_type] = max_iter
            print(f"Learned: {task_type} tasks need {max_iter} iterations")
        
        return result`
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div className="flex items-center">
              <Link href="/" className="flex items-center text-gray-400 hover:text-white mr-8">
                <ChevronLeft className="w-5 h-5 mr-1" />
                Back to Docs
              </Link>
              <h1 className="text-2xl font-bold text-white">max_iterations Guide</h1>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Hero Section */}
        <div className="bg-gradient-to-r from-violet-900/20 to-purple-900/20 border border-violet-500/30 rounded-2xl p-8 mb-12 text-white">
          <div className="max-w-3xl">
            <h2 className="text-3xl font-bold mb-4">Control Your Agent's Power</h2>
            <p className="text-xl mb-6">
              max_iterations determines how many tool calls your agent can make. 
              Master this to build efficient, reliable agents.
            </p>
            <div className="flex items-center space-x-4 text-sm">
              <span className="flex items-center">
                <Zap className="w-4 h-4 mr-1" />
                Default: 10 iterations
              </span>
              <span className="flex items-center">
                <Settings className="w-4 h-4 mr-1" />
                Fully customizable
              </span>
              <span className="flex items-center">
                <Brain className="w-4 h-4 mr-1" />
                Smart patterns included
              </span>
            </div>
          </div>
        </div>

        {/* What Are Iterations */}
        <section className="mb-12">
          <h2 className="text-2xl font-bold text-white mb-4">What Are Iterations?</h2>
          <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
            <p className="text-gray-300 mb-4">
              Think of iterations as "attempts" - how many times your agent can use tools to complete a task.
            </p>
            <div className="bg-gray-800 rounded-lg p-4 font-mono text-sm">
              <div className="text-gray-300">
                # Your agent tries to complete the task<br/>
                # Iteration 1: "I need to search for info" → calls search tool<br/>
                # Iteration 2: "Now I'll calculate something" → calls calculate tool<br/>
                # Iteration 3: "Let me save the result" → calls save tool<br/>
                # Done! Task completed in 3 iterations
              </div>
            </div>
          </div>
        </section>

        {/* Quick Start */}
        <section className="mb-12">
          <h2 className="text-2xl font-bold text-white mb-4">Quick Start - Super Simple</h2>

          <div className="grid md:grid-cols-3 gap-6">
            {/* Basic Usage */}
            <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-white mb-3">
                The Basics (90% of cases)
              </h3>
              <pre className="bg-gray-800 rounded p-3 text-sm overflow-x-auto mb-3">
                <code>{examples.basic}</code>
              </pre>
              <button
                onClick={() => copyToClipboard(examples.basic, 'basic')}
                className="flex items-center text-sm text-purple-400 hover:text-purple-300"
              >
                {copiedSection === 'basic' ? (
                  <Check className="w-4 h-4 mr-1" />
                ) : (
                  <Copy className="w-4 h-4 mr-1" />
                )}
                Copy code
              </button>
            </div>

            {/* Complex Tasks */}
            <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-white mb-3">
                When You Need More Power
              </h3>
              <pre className="bg-gray-800 rounded p-3 text-sm overflow-x-auto mb-3">
                <code>{examples.complex}</code>
              </pre>
              <button
                onClick={() => copyToClipboard(examples.complex, 'complex')}
                className="flex items-center text-sm text-purple-400 hover:text-purple-300"
              >
                {copiedSection === 'complex' ? (
                  <Check className="w-4 h-4 mr-1" />
                ) : (
                  <Copy className="w-4 h-4 mr-1" />
                )}
                Copy code
              </button>
            </div>

            {/* Override */}
            <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-white mb-3">
                Quick Override for One Task
              </h3>
              <pre className="bg-gray-800 rounded p-3 text-sm overflow-x-auto mb-3">
                <code>{examples.override}</code>
              </pre>
              <button
                onClick={() => copyToClipboard(examples.override, 'override')}
                className="flex items-center text-sm text-purple-400 hover:text-purple-300"
              >
                {copiedSection === 'override' ? (
                  <Check className="w-4 h-4 mr-1" />
                ) : (
                  <Copy className="w-4 h-4 mr-1" />
                )}
                Copy code
              </button>
            </div>
          </div>
        </section>

        {/* Real Examples */}
        <section className="mb-12">
          <h2 className="text-2xl font-bold text-white mb-4">Real Examples</h2>

          <div className="space-y-6">
            {/* Calculator Example */}
            <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-white mb-3">
                Simple Calculator Bot
              </h3>
              <p className="text-gray-300 mb-3">
                Calculator needs very few iterations - math is straightforward.
              </p>
              <pre className="bg-gray-800 rounded p-4 text-sm overflow-x-auto mb-3">
                <code>{examples.calculator}</code>
              </pre>
              <button
                onClick={() => copyToClipboard(examples.calculator, 'calculator')}
                className="flex items-center text-sm text-purple-400 hover:text-purple-300"
              >
                {copiedSection === 'calculator' ? (
                  <Check className="w-4 h-4 mr-1" />
                ) : (
                  <Copy className="w-4 h-4 mr-1" />
                )}
                Copy code
              </button>
            </div>

            {/* Error Message */}
            <div className="bg-rose-900/20 rounded-lg border border-rose-500/30 p-6">
              <h3 className="text-lg font-semibold text-white mb-3">
                What Happens When You Hit The Limit?
              </h3>
              <div className="bg-gray-900 rounded p-4 font-mono text-sm mb-3">
                <span className="text-red-400">
                  "Task incomplete: Maximum iterations (10) reached."
                </span>
              </div>
              <p className="text-gray-300">
                <strong>Solution:</strong> Simply increase max_iterations for that agent or specific task!
              </p>
            </div>
          </div>
        </section>

        {/* Cool Tricks */}
          <section className="mb-12">
            <h2 className="text-2xl font-bold text-white mb-4 flex items-center">
              <Lightbulb className="w-6 h-6 mr-2 text-purple-400" />
              Cool Tricks & Advanced Patterns
            </h2>

          <div className="grid md:grid-cols-2 gap-6">
            {/* Auto-Retry */}
            <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-white mb-3">
                Trick 1: Auto-Retry with Higher Limit
              </h3>
              <p className="text-gray-300 mb-3">
                Automatically increases iterations if task fails.
              </p>
              <pre className="bg-gray-800 rounded p-3 text-sm overflow-x-auto mb-3">
                <code>{examples.autoRetry}</code>
              </pre>
              <button
                onClick={() => copyToClipboard(examples.autoRetry, 'autoRetry')}
                className="flex items-center text-sm text-purple-400 hover:text-purple-300"
              >
                {copiedSection === 'autoRetry' ? (
                  <Check className="w-4 h-4 mr-1" />
                ) : (
                  <Copy className="w-4 h-4 mr-1" />
                )}
                Copy code
              </button>
            </div>

            {/* Self-Adjusting */}
            <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-white mb-3">
                Trick 2: Self-Adjusting Agent
              </h3>
              <p className="text-gray-300 mb-3">
                Agent that learns optimal iterations from history.
              </p>
              <pre className="bg-gray-800 rounded p-3 text-sm overflow-x-auto mb-3">
                <code>{examples.selfAdjusting}</code>
              </pre>
              <button
                onClick={() => copyToClipboard(examples.selfAdjusting, 'selfAdjusting')}
                className="flex items-center text-sm text-purple-400 hover:text-purple-300"
              >
                {copiedSection === 'selfAdjusting' ? (
                  <Check className="w-4 h-4 mr-1" />
                ) : (
                  <Copy className="w-4 h-4 mr-1" />
                )}
                Copy code
              </button>
            </div>
          </div>
        </section>

        {/* Quick Reference Table */}
          <section className="mb-12">
            <h2 className="text-2xl font-bold text-white mb-4 flex items-center">
              <Gauge className="w-6 h-6 mr-2 text-purple-400" />
              Quick Reference
            </h2>

          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="min-w-full divide-y divide-gray-700">
              <thead className="bg-gray-800">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    What You're Doing
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Iterations
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Example
                  </th>
                </tr>
              </thead>
              <tbody className="bg-gray-900 divide-y divide-gray-800">
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">
                    Simple Q&A
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    3-5
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    "What's the weather?"
                  </td>
                </tr>
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">
                    Calculations
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    5-10
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    "Calculate my taxes"
                  </td>
                </tr>
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">
                    Multi-step tasks
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    10-20
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    "Search and summarize"
                  </td>
                </tr>
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">
                    Complex workflows
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    20-40
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    "Analyze all data and generate report"
                  </td>
                </tr>
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">
                    Research projects
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    30-50
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                    "Research topic from multiple sources"
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* One Minute Summary */}
        <section className="mb-12">
          <div className="bg-gradient-to-r from-violet-900/20 to-purple-900/20 rounded-lg border border-violet-500/30 p-8">
            <h2 className="text-2xl font-bold text-white mb-4">
              ⏱️ The One-Minute Summary
            </h2>
            <ol className="space-y-2 text-gray-300">
              <li className="flex items-start">
                <span className="font-bold mr-2">1.</span>
                Most agents are fine with default <code className="bg-gray-900 px-2 py-1 rounded">max_iterations=10</code>
              </li>
              <li className="flex items-start">
                <span className="font-bold mr-2">2.</span>
                Simple bots can use 5, complex ones need 20-30
              </li>
              <li className="flex items-start">
                <span className="font-bold mr-2">3.</span>
                Override per-task when needed: <code className="bg-gray-900 px-2 py-1 rounded">agent.input(prompt, max_iterations=X)</code>
              </li>
              <li className="flex items-start">
                <span className="font-bold mr-2">4.</span>
                If you see "Maximum iterations reached", just increase the limit
              </li>
              <li className="flex items-start">
                <span className="font-bold mr-2">5.</span>
                Advanced: Build smart agents that adjust limits automatically
              </li>
            </ol>
            <p className="mt-6 text-lg font-semibold text-gray-200">
              That's it! You now know everything about iteration control. Start simple, adjust when needed! 🚀
            </p>
          </div>
        </section>

        {/* Navigation */}
        <div className="flex justify-between items-center pt-8 border-t border-gray-800">
          <Link href="/xray" className="text-purple-400 hover:text-purple-300 font-medium">
            ← Previous: Xray Debugging
          </Link>
          <Link href="/prompts" className="text-purple-400 hover:text-purple-300 font-medium">
            Next: System Prompts →
          </Link>
        </div>
      </main>
    </div>
  );
}