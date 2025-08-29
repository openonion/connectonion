'use client'

import { useState } from 'react'
import { Play, Terminal, ArrowRight, Zap, FileText, Clock, Code, Wrench, Copy, Check } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyPromptButton } from '../../components/CopyPromptButton'
import { CommandBlock } from '../../components/CommandBlock'
import CodeWithResult from '../../components/CodeWithResult'

export default function QuickStartPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)
  
  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }


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
        
        <CopyPromptButton />
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

        <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 mb-8">
          <h3 className="text-lg font-semibold text-gray-200 mb-4">Files created:</h3>
          <div className="font-mono text-sm space-y-1 text-gray-300">
            <div>meta-agent/</div>
            <div className="ml-4">├── agent.py <span className="text-gray-500"># Your meta-agent with tools</span></div>
            <div className="ml-4">├── prompt.md <span className="text-gray-500"># Main system prompt</span></div>
            <div className="ml-4">├── prompts/ <span className="text-gray-500"># Specialized prompts</span></div>
            <div className="ml-8">├── metagent.md</div>
            <div className="ml-8">├── docs_retrieve_prompt.md</div>
            <div className="ml-8">├── answer_prompt.md</div>
            <div className="ml-8">└── think_prompt.md</div>
            <div className="ml-4">├── .env.example <span className="text-gray-500"># API key template</span></div>
            <div className="ml-4">├── .gitignore <span className="text-gray-500"># Git config</span></div>
            <div className="ml-4">└── .co/ <span className="text-gray-500"># ConnectOnion config</span></div>
            <div className="ml-8">├── config.toml</div>
            <div className="ml-8">└── docs/</div>
            <div className="ml-12">└── connectonion.md</div>
          </div>
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

        <div className="space-y-6">
          {/* Learn about ConnectOnion */}
          <CodeWithResult 
            code={`# Learn about ConnectOnion
result = agent.input("What is ConnectOnion and how do tools work?")
print(result)`}
            result={`>>> result = agent.input("What is ConnectOnion and how do tools work?")
>>> print(result)
ConnectOnion is a Python framework for building AI agents with a focus on simplicity. 
Here's how it works:

1. **Agent Creation**: Create agents with a name, tools, and optional system prompt
2. **Tools**: Functions that agents can call. Any Python function can be a tool!
3. **Automatic Schema Generation**: Type hints are converted to OpenAI function schemas
4. **Iteration Control**: Use max_iterations to prevent infinite loops
5. **Built-in History**: All agent interactions are automatically saved

Tools work by:
- Converting Python functions to OpenAI-compatible schemas
- The agent decides when to call tools based on the task
- Tool results are fed back to the agent for further processing
- Multiple tools can be called in sequence to complete complex tasks`}
            className="mb-4"
          />

          {/* Generate agent code */}
          <CodeWithResult 
            code={`# Generate agent code
result = agent.input("Create a web scraper agent")
print(result[:500] + "...")  # Show first 500 chars`}
            result={`>>> result = agent.input("Create a web scraper agent")
>>> print(result[:500] + "...")
Here's a complete web scraper agent using ConnectOnion:

\`\`\`python
from connectonion import Agent
import requests
from bs4 import BeautifulSoup

def scrape_url(url: str) -> str:
    """Scrape content from a URL."""
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    return soup.get_text()[:1000]

def extract_links(url: str) -> list[str]:
    """Extract all links from a webpage."""
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    return [a['href'] for a in soup.find_all('a', href=True)]...`}
            className="mb-4"
          />

          {/* Create tool functions */}
          <CodeWithResult 
            code={`# Create tool functions
result = agent.input("Generate a tool for sending emails")
print(result)`}
            result={`>>> result = agent.input("Generate a tool for sending emails")
>>> print(result)
Here's an email sending tool for your agent:

\`\`\`python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(to: str, subject: str, body: str, from_email: str = "agent@example.com") -> str:
    """Send an email to the specified recipient.
    
    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body content
        from_email: Sender email address
        
    Returns:
        Status message indicating success or failure
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Configure your SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, 'your_app_password')
        server.send_message(msg)
        server.quit()
        
        return f"Email sent successfully to {to}"
    except Exception as e:
        return f"Failed to send email: {str(e)}"
\`\`\`

Usage: agent = Agent("mailer", tools=[send_email])`}
            className="mb-4"
          />
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
          <div className="grid sm:grid-cols-2 gap-3 text-yellow-100 text-sm">
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

        <CodeWithResult 
          code={`from connectonion import Agent

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
print(response)`}
          result={`Let me calculate that for you.

42 * 17 = 714
714 + 25 = 739

The answer is 739.`}
          className="mb-8"
        />

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

        <CodeWithResult 
          code={`from connectonion import Agent
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
print(response)`}
          result={`🔍 Agent 'debug_calc' is calculating: 50 + 30
🔍 User's original request: What's 50 + 30?
🔍 This is iteration #1
Result: 80

The result is 80.`}
          className="mb-8"
        />
      </section>

      {/* Next Steps */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-8">🎯 What's Next?</h2>
        
        <div className="grid sm:grid-cols-2 gap-4 sm:gap-6">
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