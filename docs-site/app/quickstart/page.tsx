'use client'

import { useState } from 'react'
import { Play, Terminal, ArrowRight, Zap, FileText, Clock, Code, Wrench, Copy, Check } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'
import { CommandBlock } from '../../components/CommandBlock'

export default function QuickStartPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)
  
  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# ConnectOnion Quick Start Guide

Get up and running with ConnectOnion in under 2 minutes.

## 1. Install ConnectOnion

\`\`\`bash
pip install connectonion
\`\`\`

## 2. Create Your First Meta-Agent

\`\`\`bash
# Create a new directory for your agent
mkdir meta-agent
cd meta-agent

# Initialize the meta-agent (default)
co init
\`\`\`

This creates a ConnectOnion development assistant with powerful capabilities:
- \`agent.py\` - Meta-agent with documentation expertise and development tools
- \`prompt.md\` - System prompt for your agent
- \`.env.example\` - Template for API keys
- \`.co/docs/\` - Embedded ConnectOnion documentation for offline reference

## 3. Set Up Your API Key

\`\`\`bash
cp .env.example .env
\`\`\`

Edit \`.env\` and add your OpenAI API key:
\`\`\`
OPENAI_API_KEY=sk-your-actual-api-key-here
\`\`\`

## 4. Run Your Agent

\`\`\`bash
python agent.py
\`\`\`

Your meta-agent comes with powerful built-in tools:
- **answer_connectonion_question()** - Expert answers from embedded docs
- **create_agent_from_template()** - Generate complete agent code
- **generate_tool_code()** - Create tool functions
- **create_test_for_agent()** - Generate pytest test suites
- **think()** - Self-reflection to analyze task completion
- **generate_todo_list()** - Create structured plans (uses GPT-4o-mini)
- **suggest_project_structure()** - Architecture recommendations

## Try These Commands

Once your meta-agent is running, try these:

\`\`\`python
# Learn about ConnectOnion
result = agent.input("What is ConnectOnion and how do tools work?")

# Generate agent code
result = agent.input("Create a web scraper agent")

# Create tool functions
result = agent.input("Generate a tool for sending emails")

# Get project structure advice
result = agent.input("Suggest structure for a multi-agent system")

# Generate a structured plan
result = agent.input("Create a to-do list for building a REST API")
\`\`\`

## Choose a Different Template

ConnectOnion offers specialized templates:

### Playwright Agent (Web Automation)
\`\`\`bash
co init --template playwright
\`\`\`

Perfect for:
- Web scraping and data extraction
- Browser automation and testing
- Form filling and submission
- Screenshot capture
- Link crawling

Comes with stateful browser tools:
- \`start_browser()\` - Launch browser instance
- \`navigate()\` - Go to URLs
- \`scrape_content()\` - Extract page content
- \`fill_form()\` - Fill and submit forms
- \`take_screenshot()\` - Capture pages
- And many more browser automation tools

Note: Requires \`pip install playwright && playwright install\`

## Create a Custom Tool Agent

You can also create agents from scratch with custom tools:

\`\`\`python
from connectonion import Agent

def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions."""
    try:
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        else:
            return "Error: Invalid characters"
    except Exception as e:
        return f"Error: {str(e)}"

# Create agent with the tool
agent = Agent(
    name="calculator", 
    tools=[calculate],
    system_prompt="You are a helpful math tutor.",
    max_iterations=5  # Simple calculations need few iterations
)

# Use the agent
response = agent.input("What is 42 * 17 + 25?")
print(response)  # Result: 739
\`\`\`

## Debugging with @xray

See what your agent is thinking:

\`\`\`python
from connectonion import Agent
from connectonion.decorators import xray

@xray
def calculate(expression: str) -> str:
    """Math tool with debugging enabled."""
    print(f"🔍 Agent '{xray.agent.name}' is calculating: {expression}")
    print(f"🔍 User's original request: {xray.task}")
    print(f"🔍 This is iteration #{xray.iteration}")
    
    result = eval(expression)
    return f"Result: {result}"

agent = Agent("debug_calc", tools=[calculate], max_iterations=5)
response = agent.input("What's 50 + 30?")
\`\`\`

Output:
\`\`\`
🔍 Agent 'debug_calc' is calculating: 50 + 30
🔍 User's original request: What's 50 + 30?
🔍 This is iteration #1
Result: 80
\`\`\`

## Next Steps

- [System Prompts](/prompts) - Learn advanced prompting techniques
- [@xray Debugging](/xray) - Master agent debugging and introspection  
- [Examples](/examples) - See real-world agent implementations
- [Templates Guide](/templates) - Explore all available templates`

  return (
    <div className="max-w-4xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Header with Copy Button */}
      <div className="flex items-start justify-between mb-8">
        <div className="flex-1">
          {/* Breadcrumb */}
          <nav className="flex items-center gap-2 text-sm text-gray-400 mb-4">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <ArrowRight className="w-4 h-4" />
            <span className="text-white">Quick Start</span>
          </nav>
          
          <h1 className="text-4xl font-bold text-white mb-4">Quick Start Guide</h1>
          <p className="text-xl text-gray-300">
            Get up and running with ConnectOnion in under 2 minutes.
          </p>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="connectonion-quickstart.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Time Estimate */}
      <div className="flex items-center gap-2 mb-12 p-4 bg-gradient-to-b from-blue-900/30 to-blue-800/10 border border-blue-500/30 rounded-lg">
        <Clock className="w-5 h-5 text-blue-400" />
        <span className="text-blue-200">
          <strong>Estimated time:</strong> 2 minutes to first working agent
        </span>
      </div>

      {/* Installation */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-green-600 rounded-lg flex items-center justify-center text-white font-bold">1</div>
          Install ConnectOnion
        </h2>
        
        <CommandBlock 
          commands={['pip install connectonion']}
        />
      </section>

      {/* Create Meta-Agent */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">2</div>
          Create Your First Meta-Agent
        </h2>
        
        <p className="text-gray-300 mb-6">
          Initialize a ConnectOnion development assistant with powerful built-in capabilities:
        </p>

        <div className="mb-6">
          <CommandBlock 
            commands={[
              'mkdir meta-agent',
              'cd meta-agent',
              'co init'
            ]}
          />
        </div>

        <div className="bg-gradient-to-b from-blue-900/30 to-blue-800/10 border border-blue-500/30 rounded-lg p-6 mb-8">
          <h3 className="text-lg font-semibold text-blue-200 mb-4">Your meta-agent includes:</h3>
          <ul className="space-y-2 text-blue-100">
            <li className="flex items-start gap-2">
              <span className="text-blue-400 mt-1">•</span>
              <span><strong>answer_connectonion_question()</strong> - Expert answers from embedded docs</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-400 mt-1">•</span>
              <span><strong>create_agent_from_template()</strong> - Generate complete agent code</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-400 mt-1">•</span>
              <span><strong>generate_tool_code()</strong> - Create tool functions</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-400 mt-1">•</span>
              <span><strong>create_test_for_agent()</strong> - Generate pytest test suites</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-400 mt-1">•</span>
              <span><strong>think()</strong> - Self-reflection to analyze tasks</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-400 mt-1">•</span>
              <span><strong>generate_todo_list()</strong> - Create structured plans (uses GPT-4o-mini)</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-400 mt-1">•</span>
              <span><strong>suggest_project_structure()</strong> - Architecture recommendations</span>
            </li>
          </ul>
        </div>
      </section>

      {/* Set Up API Key */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-purple-600 rounded-lg flex items-center justify-center text-white font-bold">3</div>
          Set Up Your API Key
        </h2>
        
        <div className="mb-4">
          <CommandBlock 
            commands={['cp .env.example .env']}
          />
        </div>

        <p className="text-gray-300 mb-4">Then edit <code className="bg-gray-800 px-2 py-1 rounded text-blue-300">.env</code> and add your OpenAI API key:</p>

        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-2 border-b border-gray-700">
            <span className="text-sm text-gray-400 font-mono">.env</span>
          </div>
          <div className="bg-black p-4 font-mono text-sm">
            <span className="text-gray-400"># OpenAI API Configuration</span><br/>
            <span className="text-white">OPENAI_API_KEY=sk-your-actual-api-key-here</span>
          </div>
        </div>
      </section>

      {/* Try Commands */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white font-bold">4</div>
          Try These Commands
        </h2>
        
        <p className="text-gray-300 mb-6">
          Your meta-agent can help you build ConnectOnion projects:
        </p>

        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden mb-6">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
            <span className="text-sm text-gray-300 font-mono">example_usage.py</span>
            <button
              onClick={() => copyToClipboard(`# Learn about ConnectOnion
result = agent.input("What is ConnectOnion and how do tools work?")

# Generate agent code
result = agent.input("Create a web scraper agent")

# Create tool functions  
result = agent.input("Generate a tool for sending emails")

# Get project structure advice
result = agent.input("Suggest structure for a multi-agent system")

# Generate a structured plan
result = agent.input("Create a to-do list for building a REST API")`, 'meta-examples')}
              className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-700"
            >
              {copiedId === 'meta-examples' ? (
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
{`# Learn about ConnectOnion
result = agent.input("What is ConnectOnion and how do tools work?")

# Generate agent code
result = agent.input("Create a web scraper agent")

# Create tool functions  
result = agent.input("Generate a tool for sending emails")

# Get project structure advice
result = agent.input("Suggest structure for a multi-agent system")

# Generate a structured plan
result = agent.input("Create a to-do list for building a REST API")`}
            </SyntaxHighlighter>
          </div>
        </div>
      </section>

      {/* Playwright Template */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-yellow-600 rounded-lg flex items-center justify-center text-white font-bold">5</div>
          Alternative: Playwright Web Automation
        </h2>
        
        <p className="text-gray-300 mb-6">
          For web automation tasks, use the Playwright template:
        </p>

        <div className="mb-6">
          <CommandBlock 
            commands={['co init --template playwright']}
          />
        </div>

        <div className="bg-gradient-to-b from-yellow-900/30 to-yellow-800/10 border border-yellow-500/30 rounded-lg p-6 mb-8">
          <h3 className="text-lg font-semibold text-yellow-200 mb-4">Stateful browser tools included:</h3>
          <div className="grid md:grid-cols-2 gap-3 text-yellow-100 text-sm">
            <div className="flex items-start gap-2">
              <span className="text-yellow-400 mt-1">•</span>
              <span><strong>start_browser()</strong> - Launch browser</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-yellow-400 mt-1">•</span>
              <span><strong>navigate()</strong> - Go to URLs</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-yellow-400 mt-1">•</span>
              <span><strong>scrape_content()</strong> - Extract content</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-yellow-400 mt-1">•</span>
              <span><strong>fill_form()</strong> - Complete forms</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-yellow-400 mt-1">•</span>
              <span><strong>take_screenshot()</strong> - Capture pages</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-yellow-400 mt-1">•</span>
              <span><strong>extract_links()</strong> - Get all links</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-yellow-400 mt-1">•</span>
              <span><strong>click()</strong> - Click elements</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-yellow-400 mt-1">•</span>
              <span><strong>execute_javascript()</strong> - Run JS</span>
            </div>
          </div>
          <p className="text-yellow-200 mt-4 text-sm">
            <strong>Note:</strong> Requires <code className="bg-black/30 px-2 py-1 rounded">pip install playwright && playwright install</code>
          </p>
        </div>
      </section>

      {/* Custom Tool Example */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-green-600 rounded-lg flex items-center justify-center text-white font-bold">6</div>
          Create a Custom Tool Agent
        </h2>
        
        <p className="text-gray-300 mb-6">
          You can also create agents from scratch with custom tools:
        </p>

        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden mb-6">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
            <span className="text-sm text-gray-300 font-mono">calculator_agent.py</span>
            <button
              onClick={() => copyToClipboard(`from connectonion import Agent

def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions."""
    try:
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        else:
            return "Error: Invalid characters"
    except Exception as e:
        return f"Error: {str(e)}"

# Create agent with the tool
agent = Agent(
    name="calculator", 
    tools=[calculate],
    system_prompt="You are a helpful math tutor.",
    max_iterations=5  # Simple calculations need few iterations
)

# Use the agent
response = agent.input("What is 42 * 17 + 25?")
print(response)  # Result: 739`, 'custom-tool')}
              className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-700"
            >
              {copiedId === 'custom-tool' ? (
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

def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions."""
    try:
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        else:
            return "Error: Invalid characters"
    except Exception as e:
        return f"Error: {str(e)}"

# Create agent with the tool
agent = Agent(
    name="calculator", 
    tools=[calculate],
    system_prompt="You are a helpful math tutor.",
    max_iterations=5  # Simple calculations need few iterations
)

# Use the agent
response = agent.input("What is 42 * 17 + 25?")
print(response)  # Result: 739`}
            </SyntaxHighlighter>
          </div>
        </div>

        {/* Output */}
        <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-4 mb-8">
          <div className="flex items-center gap-3 mb-3">
            <Terminal className="w-5 h-5 text-green-400" />
            <span className="font-semibold text-green-300">Output:</span>
          </div>
          <div className="font-mono text-green-200 bg-black/30 rounded p-3">
            Result: 739
          </div>
        </div>
      </section>

      {/* Debugging with @xray */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-red-600 rounded-lg flex items-center justify-center text-white font-bold">7</div>
          Debugging with @xray
        </h2>
        
        <p className="text-gray-300 mb-6">
          Use the @xray decorator to see what your agent is thinking:
        </p>

        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden mb-6">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
            <span className="text-sm text-gray-300 font-mono">debug_example.py</span>
            <button
              onClick={() => copyToClipboard(`from connectonion import Agent
from connectonion.decorators import xray

@xray
def calculate(expression: str) -> str:
    """Math tool with debugging enabled."""
    print(f"🔍 Agent '{xray.agent.name}' is calculating: {expression}")
    print(f"🔍 User's original request: {xray.task}")
    print(f"🔍 This is iteration #{xray.iteration}")
    
    result = eval(expression)
    return f"Result: {result}"

agent = Agent("debug_calc", tools=[calculate], max_iterations=5)
response = agent.input("What's 50 + 30?")`, 'xray-debug')}
              className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-700"
            >
              {copiedId === 'xray-debug' ? (
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
from connectonion.decorators import xray

@xray
def calculate(expression: str) -> str:
    """Math tool with debugging enabled."""
    print(f"🔍 Agent '{xray.agent.name}' is calculating: {expression}")
    print(f"🔍 User's original request: {xray.task}")
    print(f"🔍 This is iteration #{xray.iteration}")
    
    result = eval(expression)
    return f"Result: {result}"

agent = Agent("debug_calc", tools=[calculate], max_iterations=5)
response = agent.input("What's 50 + 30?")`}
            </SyntaxHighlighter>
          </div>
        </div>

        {/* Output */}
        <div className="bg-gradient-to-b from-red-900/30 to-red-800/10 border border-red-500/30 rounded-lg p-4 mb-8">
          <div className="flex items-center gap-3 mb-3">
            <Terminal className="w-5 h-5 text-red-400" />
            <span className="font-semibold text-red-300">Debug Output:</span>
          </div>
          <div className="font-mono text-red-200 bg-black/30 rounded p-3 text-sm">
            🔍 Agent 'debug_calc' is calculating: 50 + 30<br/>
            🔍 User's original request: What's 50 + 30?<br/>
            🔍 This is iteration #1<br/>
            Result: 80
          </div>
        </div>
      </section>

      {/* Next Steps */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-8">🎯 What's Next?</h2>
        
        <div className="grid md:grid-cols-2 gap-6">
          <Link 
            href="/prompts" 
            className="group bg-gradient-to-r from-purple-900/20 to-purple-800/20 border border-purple-500/30 rounded-xl p-6 hover:border-purple-400/50 transition-all"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 bg-purple-600 rounded-xl flex items-center justify-center">
                <FileText className="w-6 h-6 text-white" />
              </div>
              <ArrowRight className="w-5 h-5 text-purple-400 group-hover:translate-x-1 transition-transform" />
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">Master System Prompts</h3>
            <p className="text-purple-100 text-sm">
              Learn advanced prompting techniques to create expert agents for any domain.
            </p>
          </Link>

          <Link 
            href="/xray" 
            className="group bg-gradient-to-r from-green-900/20 to-green-800/20 border border-green-500/30 rounded-xl p-6 hover:border-green-400/50 transition-all"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 bg-green-600 rounded-xl flex items-center justify-center">
                <Zap className="w-6 h-6 text-white" />
              </div>
              <ArrowRight className="w-5 h-5 text-green-400 group-hover:translate-x-1 transition-transform" />
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">Deep Dive into @xray</h3>
            <p className="text-green-100 text-sm">
              Master debugging and get complete visibility into your agent's decision-making.
            </p>
          </Link>

          <Link 
            href="/examples" 
            className="group bg-gradient-to-r from-blue-900/20 to-blue-800/20 border border-blue-500/30 rounded-xl p-6 hover:border-blue-400/50 transition-all"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center">
                <Code className="w-6 h-6 text-white" />
              </div>
              <ArrowRight className="w-5 h-5 text-blue-400 group-hover:translate-x-1 transition-transform" />
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">Real-World Examples</h3>
            <p className="text-blue-100 text-sm">
              See complete agent implementations for various use cases.
            </p>
          </Link>

          <Link 
            href="/tools" 
            className="group bg-gradient-to-r from-orange-900/20 to-orange-800/20 border border-orange-500/30 rounded-xl p-6 hover:border-orange-400/50 transition-all"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 bg-orange-600 rounded-xl flex items-center justify-center">
                <Wrench className="w-6 h-6 text-white" />
              </div>
              <ArrowRight className="w-5 h-5 text-orange-400 group-hover:translate-x-1 transition-transform" />
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">Build Custom Tools</h3>
            <p className="text-orange-100 text-sm">
              Learn how to create powerful tools for your agents.
            </p>
          </Link>
        </div>
      </section>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-8 border-t border-gray-800">
        <Link 
          href="/" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <ArrowRight className="w-4 h-4 rotate-180" />
          Introduction
        </Link>
        <Link 
          href="/prompts" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          System Prompts
          <ArrowRight className="w-4 h-4" />
        </Link>
      </nav>
    </div>
  )
}