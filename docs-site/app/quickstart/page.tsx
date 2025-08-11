'use client'

import { useState } from 'react'
import { Copy, Check, Play, Terminal, ArrowRight, Zap, FileText, Clock } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'

export default function QuickStartPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# ConnectOnion Quick Start Guide

Get up and running with ConnectOnion in under 5 minutes. Build your first AI agent that can use tools and track behavior automatically.

## Installation

\`\`\`bash
pip install connectonion
\`\`\`

## Your First Agent (2 minutes)

Create a simple calculator agent:

\`\`\`python
from connectonion import Agent

def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions."""
    try:
        # Only allow safe mathematical expressions
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        else:
            return "Error: Invalid characters in expression"
    except Exception as e:
        return f"Error: {str(e)}"

# Create agent with the tool
agent = Agent(
    name="calculator", 
    tools=[calculate]
)

# Use the agent
response = agent.input("What is 42 * 17 + 25?")
print(response)
\`\`\`

**Output:**
\`\`\`
Result: 739
\`\`\`

## Adding Personality with System Prompts

Make your agent more helpful:

\`\`\`python
agent = Agent(
    name="math_tutor",
    system_prompt="""You are a friendly math tutor. When solving problems:
    1. Show your work step by step
    2. Explain the reasoning
    3. Encourage the user""",
    tools=[calculate]
)

response = agent.input("How do I calculate 15% of 240?")
print(response)
\`\`\`

**Output:**
\`\`\`
I'd be happy to help you calculate 15% of 240! Let me break this down:

To find 15% of 240, I need to multiply 240 by 0.15 (since 15% = 15/100 = 0.15).

Let me calculate that: 240 * 0.15

Result: 36.0

So 15% of 240 is 36. Great job asking for help with percentages - they're really useful in everyday life!
\`\`\`

## Multiple Tools Example

Create an agent with multiple capabilities:

\`\`\`python
from connectonion import Agent
import random
from datetime import datetime

def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions."""
    try:
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Calculation result: {result}"
        else:
            return "Error: Invalid characters in expression"
    except Exception as e:
        return f"Error: {str(e)}"

def roll_dice(sides: int = 6, count: int = 1) -> str:
    """Roll dice and return the results."""
    if count > 10:
        return "Maximum 10 dice allowed"
    
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    
    if count == 1:
        return f"🎲 Rolled a {rolls[0]} (d{sides})"
    else:
        return f"🎲 Rolled {count}d{sides}: {rolls} = {total}"

def get_current_time() -> str:
    """Get the current date and time."""
    now = datetime.now()
    return f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}"

# Create multi-tool agent
agent = Agent(
    name="assistant",
    system_prompt="You are a helpful assistant that can do math, roll dice, and tell time. Be friendly and explain what you're doing.",
    tools=[calculate, roll_dice, get_current_time]
)

# Test multiple capabilities
response = agent.input("Roll 3 six-sided dice, then calculate the sum times 2, and tell me the current time")
print(response)
\`\`\`

**Output:**
\`\`\`
I'll help you with all three tasks! Let me start by rolling the dice.

🎲 Rolled 3d6: [4, 2, 6] = 12

Now I'll calculate the sum times 2:
Calculation result: 24

And here's the current time:
Current time: 2024-01-15 14:30:22

So you rolled a total of 12, which times 2 equals 24. Hope that helps!
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
    
    try:
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        else:
            return "Error: Invalid characters"
    except Exception as e:
        return f"Error: {str(e)}"

agent = Agent("debug_calc", tools=[calculate])
response = agent.input("What's 50 + 30?")
\`\`\`

**Output:**
\`\`\`
🔍 Agent 'debug_calc' is calculating: 50 + 30
🔍 User's original request: What's 50 + 30?
🔍 This is iteration #1
Result: 80
\`\`\`

## File-Based System Prompts

For complex prompts, use external files:

Create \`prompts/customer_support.md\`:
\`\`\`markdown
# Customer Support Specialist

You are a professional customer support agent.

## Core Principles
- Always be empathetic and patient
- Focus on solving the customer's problem
- Provide clear, step-by-step solutions
- Follow up to ensure satisfaction

## Response Style
- Start with acknowledgment
- Ask clarifying questions if needed  
- Provide actionable solutions
- End with next steps
\`\`\`

Then use it in code:

\`\`\`python
agent = Agent(
    name="support",
    system_prompt="prompts/customer_support.md",  # Loads from file
    tools=[your_tools]
)
\`\`\`

## Next Steps

🎯 **What to explore next:**

1. **[System Prompts](/prompts)** - Learn advanced prompting techniques
2. **[@xray Debugging](/xray)** - Master agent debugging and introspection  
3. **[Examples](/examples)** - See real-world agent implementations
4. **[API Reference](/api)** - Complete technical documentation

## Common Patterns

### Environment-Specific Configuration

\`\`\`python
import os

# Different prompts for different environments
env = os.getenv("ENVIRONMENT", "development")
prompt_file = f"prompts/{env}/agent.md"

agent = Agent(
    name="app_assistant",
    system_prompt=prompt_file,
    tools=[your_tools]
)
\`\`\`

### Error Handling

\`\`\`python
def safe_tool(input_data: str) -> str:
    """Tool with proper error handling."""
    try:
        # Your tool logic here
        result = process_data(input_data)
        return f"Success: {result}"
    except ValueError as e:
        return f"Input error: {str(e)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
\`\`\`

### Testing Your Agent

\`\`\`python
def test_agent():
    """Simple agent testing."""
    agent = Agent("test", tools=[calculate])
    
    test_cases = [
        ("What is 2+2?", "4"),
        ("Calculate 10*5", "50"),
    ]
    
    for question, expected in test_cases:
        response = agent.input(question)
        print(f"Q: {question}")
        print(f"A: {response}")
        print("---")

test_agent()
\`\`\`

That's it! You now have a working AI agent with tools, personality, and debugging capabilities. 🚀
`

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
            Get up and running with ConnectOnion in under 5 minutes. Build your first AI agent with tools and automatic behavior tracking.
          </p>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="connectonion-quickstart.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Time Estimate */}
      <div className="flex items-center gap-2 mb-12 p-4 bg-blue-900/20 border border-blue-500/30 rounded-lg">
        <Clock className="w-5 h-5 text-blue-400" />
        <span className="text-blue-200">
          <strong>Estimated time:</strong> 5 minutes to first working agent
        </span>
      </div>

      {/* Installation */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-green-600 rounded-lg flex items-center justify-center text-white font-bold">1</div>
          Installation
        </h2>
        
        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-2 border-b border-gray-700">
            <span className="text-sm text-gray-400 font-mono">Terminal</span>
            <button
              onClick={() => copyToClipboard('pip install connectonion', 'install')}
              className="text-gray-400 hover:text-white transition-colors p-1"
            >
              {copiedId === 'install' ? (
                <Check className="w-4 h-4 text-green-400" />
              ) : (
                <Copy className="w-4 h-4" />
              )}
            </button>
          </div>
          <div className="bg-black p-4 font-mono text-sm">
            <span className="text-green-400">$</span> <span className="text-white">pip install connectonion</span>
          </div>
        </div>
      </section>

      {/* Your First Agent */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">2</div>
          Your First Agent (2 minutes)
        </h2>
        
        <p className="text-gray-300 mb-6">
          Let's create a simple calculator agent that can solve math problems:
        </p>

        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden mb-6">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
            <span className="text-sm text-gray-300 font-mono">first_agent.py</span>
            <button
              onClick={() => copyToClipboard(`from connectonion import Agent

def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions."""
    try:
        # Only allow safe mathematical expressions
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        else:
            return "Error: Invalid characters in expression"
    except Exception as e:
        return f"Error: {str(e)}"

# Create agent with the tool
agent = Agent(
    name="calculator", 
    tools=[calculate]
)

# Use the agent
response = agent.input("What is 42 * 17 + 25?")
print(response)`, 'first-agent')}
              className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-700"
            >
              {copiedId === 'first-agent' ? (
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
        # Only allow safe mathematical expressions
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        else:
            return "Error: Invalid characters in expression"
    except Exception as e:
        return f"Error: {str(e)}"

# Create agent with the tool
agent = Agent(
    name="calculator", 
    tools=[calculate]
)

# Use the agent
response = agent.input("What is 42 * 17 + 25?")
print(response)`}
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

      {/* System Prompts */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-purple-600 rounded-lg flex items-center justify-center text-white font-bold">3</div>
          Adding Personality with System Prompts
        </h2>
        
        <p className="text-gray-300 mb-6">
          Make your agent more helpful and educational by adding a system prompt:
        </p>

        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden mb-6">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
            <span className="text-sm text-gray-300 font-mono">math_tutor.py</span>
            <button
              onClick={() => copyToClipboard(`agent = Agent(
    name="math_tutor",
    system_prompt="""You are a friendly math tutor. When solving problems:
    1. Show your work step by step
    2. Explain the reasoning
    3. Encourage the user""",
    tools=[calculate]
)

response = agent.input("How do I calculate 15% of 240?")
print(response)`, 'system-prompt')}
              className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-700"
            >
              {copiedId === 'system-prompt' ? (
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
{`agent = Agent(
    name="math_tutor",
    system_prompt="""You are a friendly math tutor. When solving problems:
    1. Show your work step by step
    2. Explain the reasoning
    3. Encourage the user""",
    tools=[calculate]
)

response = agent.input("How do I calculate 15% of 240?")
print(response)`}
            </SyntaxHighlighter>
          </div>
        </div>

        {/* Output */}
        <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-4 mb-8">
          <div className="flex items-center gap-3 mb-3">
            <Terminal className="w-5 h-5 text-purple-400" />
            <span className="font-semibold text-purple-300">Output:</span>
          </div>
          <div className="font-mono text-purple-200 bg-black/30 rounded p-3 text-sm">
            I'd be happy to help you calculate 15% of 240! Let me break this down:<br/><br/>
            To find 15% of 240, I need to multiply 240 by 0.15 (since 15% = 15/100 = 0.15).<br/><br/>
            Let me calculate that: 240 * 0.15<br/><br/>
            Result: 36.0<br/><br/>
            So 15% of 240 is 36. Great job asking for help with percentages - they're really useful in everyday life!
          </div>
        </div>
      </section>

      {/* Debugging with @xray */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-yellow-600 rounded-lg flex items-center justify-center text-white font-bold">4</div>
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
    
    try:
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        else:
            return "Error: Invalid characters"
    except Exception as e:
        return f"Error: {str(e)}"

agent = Agent("debug_calc", tools=[calculate])
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
    
    try:
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        else:
            return "Error: Invalid characters"
    except Exception as e:
        return f"Error: {str(e)}"

agent = Agent("debug_calc", tools=[calculate])
response = agent.input("What's 50 + 30?")`}
            </SyntaxHighlighter>
          </div>
        </div>

        {/* Output */}
        <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-4 mb-8">
          <div className="flex items-center gap-3 mb-3">
            <Terminal className="w-5 h-5 text-yellow-400" />
            <span className="font-semibold text-yellow-300">Debug Output:</span>
          </div>
          <div className="font-mono text-yellow-200 bg-black/30 rounded p-3 text-sm">
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