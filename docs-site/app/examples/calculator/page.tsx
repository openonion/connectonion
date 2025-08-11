'use client'

import React, { useState } from 'react'
import { Copy, Check, Code, ArrowRight, ArrowLeft, Download, Play, Terminal, Lightbulb, Shield, AlertTriangle } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'

const agentCode = `from connectonion import Agent

def calculate(expression: str) -> str:
    """Safely evaluate basic math expressions."""
    try:
        # Only allow safe characters
        allowed = set('0123456789+-*/()., ')
        if not all(c in allowed for c in expression):
            return "Error: Only basic math operations allowed"
        
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def get_help() -> str:
    """Get help about available math operations."""
    return """Available operations:
    + Addition
    - Subtraction  
    * Multiplication
    / Division
    () Parentheses for grouping
    
    Example: 2 + 3 * 4"""

# Create calculator agent
agent = Agent(
    name="calculator",
    tools=[calculate, get_help]
)

response = agent.input("What's 25 + 17 * 3?")
print(response)`

const expectedOutput = `25 + 17 * 3 = 76`

const fullExampleCode = `# calculator_agent.py
import os
from connectonion import Agent

# Set your OpenAI API key
os.environ['OPENAI_API_KEY'] = 'your-api-key-here'

def calculate(expression: str) -> str:
    """Safely evaluate basic math expressions like 2+3*4."""
    try:
        # Input validation - only allow safe mathematical characters
        allowed_chars = set('0123456789+-*/()., ')
        if not all(c in allowed_chars for c in expression):
            return "Error: Only basic math operations (+, -, *, /, parentheses) are allowed"
        
        # Prevent empty expressions
        if not expression.strip():
            return "Error: Please provide a math expression"
            
        # Evaluate the expression safely
        result = eval(expression)
        return f"Calculation: {expression} = {result}"
    except ZeroDivisionError:
        return f"Error: Division by zero in expression '{expression}'"
    except Exception as e:
        return f"Math Error: {str(e)} in expression '{expression}'"

def get_help() -> str:
    """Get help about available math operations and examples."""
    return """🧮 Calculator Help
    
Available operations:
• Addition: +
• Subtraction: -  
• Multiplication: *
• Division: /
• Parentheses: () for grouping
• Decimals: . (like 3.14)

Examples:
• Simple: 2 + 3
• Complex: (10 + 5) * 2 / 3
• Decimals: 3.14 * 2.5
• Order of operations: 2 + 3 * 4 = 14 (not 20!)"""

def validate_expression(expression: str) -> str:
    """Check if a math expression is valid before calculating."""
    if not expression or not expression.strip():
        return "❌ Empty expression - please provide a math problem"
    
    allowed_chars = set('0123456789+-*/()., ')
    invalid_chars = [c for c in expression if c not in allowed_chars]
    
    if invalid_chars:
        return f"❌ Invalid characters found: {', '.join(set(invalid_chars))}. Only use: 0-9, +, -, *, /, (, ), ."
    
    # Check for basic syntax issues
    if expression.count('(') != expression.count(')'):
        return "❌ Mismatched parentheses"
    
    return "✅ Expression looks valid!"

# Create the calculator agent
agent = Agent(
    name="calculator",
    system_prompt="""You are a helpful calculator assistant. 
    Always use the calculate() function for math operations.
    If users ask for help or seem confused, use get_help().
    If they want to check an expression first, use validate_expression().""",
    tools=[calculate, get_help, validate_expression]
)

if __name__ == "__main__":
    print("=== Calculator Agent Demo ===\\n")
    
    # Test various calculations
    test_cases = [
        "What's 25 + 17 * 3?",
        "Help me understand what operations are available",
        "Is '2 + 3 *' a valid expression?",
        "Calculate (100 - 25) / 5 + 10",
        "What's 22 / 7?"
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test}")
        response = agent.input(test)
        print(f"Response: {response}\\n")
        print("-" * 50)`

export default function CalculatorAgentPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Basic Calculator Agent - ConnectOnion Tutorial

Learn input validation, error handling, and multiple tool integration by building a safe math calculator agent.

## What You'll Learn

- Input validation and security best practices
- Error handling in agent tools
- Multiple tool integration patterns
- System prompts for tool selection guidance

## Key Features

- ✅ Safe mathematical expression evaluation
- 🛡️ Input validation and security filtering
- ❌ Comprehensive error handling
- 💡 Built-in help system
- ✔️ Expression validation before calculation

## Complete Example

\`\`\`python
${fullExampleCode}
\`\`\`

## Security Considerations

This example demonstrates important security practices:
- Character whitelist validation
- Safe eval() usage with input filtering
- Proper error handling and user feedback
- Expression syntax validation

Build on this foundation for more complex agents that need to handle user input safely!`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/examples" className="hover:text-white transition-colors">Agent Building</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">Basic Calculator</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-blue-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">2</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Code className="w-8 h-8 text-blue-400" />
                <h1 className="text-4xl font-bold text-white">Basic Calculator Agent</h1>
                <span className="px-3 py-1 bg-blue-900/50 text-blue-300 rounded-full text-sm font-medium">
                  Beginner
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Learn input validation, error handling, and security best practices by building a safe math calculator.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="calculator-agent.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-blue-900/20 border border-blue-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-blue-400" />
          What You'll Learn
        </h2>
        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-blue-600 rounded-lg flex items-center justify-center">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Input Validation</h3>
            <p className="text-blue-200 text-sm">Secure input filtering and validation</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-blue-600 rounded-lg flex items-center justify-center">
              <AlertTriangle className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Error Handling</h3>
            <p className="text-blue-200 text-sm">Graceful error management and feedback</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-blue-600 rounded-lg flex items-center justify-center">
              <Code className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Multiple Tools</h3>
            <p className="text-blue-200 text-sm">Integrating several tools in one agent</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-blue-600 rounded-lg flex items-center justify-center">
              <Terminal className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">System Prompts</h3>
            <p className="text-blue-200 text-sm">Guide tool selection with prompts</p>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-12">
        {/* Code Examples */}
        <div className="space-y-8">
          {/* Basic Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Basic Calculator</h3>
              <button
                onClick={() => copyToClipboard(agentCode, 'basic')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'basic' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
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
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {agentCode}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Complete Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Complete Example with Security</h3>
              <button
                onClick={() => copyToClipboard(fullExampleCode, 'complete')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'complete' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
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
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {fullExampleCode}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="space-y-8">
          {/* Output */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
              <Terminal className="w-5 h-5 text-blue-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm">
                <pre className="text-blue-200 whitespace-pre-wrap">
                  {`=== Calculator Agent Demo ===

Test 1: What's 25 + 17 * 3?
Response: Calculation: 25 + 17 * 3 = 76

Test 2: Help me understand what operations are available
Response: 🧮 Calculator Help
    
Available operations:
• Addition: +
• Subtraction: -  
• Multiplication: *
• Division: /
• Parentheses: () for grouping
• Decimals: . (like 3.14)

Test 3: Is '2 + 3 *' a valid expression?
Response: ❌ Expression looks invalid - incomplete operation

Test 4: Calculate (100 - 25) / 5 + 10
Response: Calculation: (100 - 25) / 5 + 10 = 25.0`}
                </pre>
              </div>
            </div>
          </div>

          {/* Security Features */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">Security Features</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-blue-400 mb-2">🛡️ Input Validation</h4>
                <p className="text-gray-300">Only allows safe mathematical characters (0-9, +, -, *, /, (, ), ., space).</p>
              </div>
              <div>
                <h4 className="font-semibold text-blue-400 mb-2">⚡ Safe Evaluation</h4>
                <p className="text-gray-300">Pre-filters input before using eval() to prevent code injection.</p>
              </div>
              <div>
                <h4 className="font-semibold text-blue-400 mb-2">🚨 Error Handling</h4>
                <p className="text-gray-300">Catches division by zero, syntax errors, and invalid operations gracefully.</p>
              </div>
            </div>
          </div>

          {/* Advanced Features */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Advanced Features</h3>
            <div className="space-y-3 text-sm">
              <div className="p-3 bg-blue-900/20 border border-blue-500/30 rounded">
                <p className="text-blue-300 font-medium mb-1">🔧 Multiple Tools</p>
                <ul className="text-blue-200 space-y-1">
                  <li>• <code>calculate()</code> - Core math operations</li>
                  <li>• <code>get_help()</code> - User assistance</li>
                  <li>• <code>validate_expression()</code> - Input checking</li>
                </ul>
              </div>
              <div className="p-3 bg-blue-900/20 border border-blue-500/30 rounded">
                <p className="text-blue-300 font-medium mb-1">🎯 System Prompt</p>
                <p className="text-blue-200">Guides the agent on when to use which tool based on user needs.</p>
              </div>
            </div>
          </div>

          {/* Download */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Try It Yourself</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(fullExampleCode)}`}
                download="calculator_agent.py"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Complete Example
              </a>
              <p className="text-xs text-gray-400 text-center">
                Complete calculator with security features and error handling
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Previous in series</p>
          <Link 
            href="/examples/hello-world" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            1. Hello World Agent
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/examples/weather-bot" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            3. Weather Bot
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}