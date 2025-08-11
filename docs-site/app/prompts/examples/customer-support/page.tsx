'use client'

import React, { useState } from 'react'
import { Copy, Check, User, ArrowRight, ArrowLeft, Download, Lightbulb, MessageSquare, Shield, Settings } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../../components/CopyMarkdownButton'

const promptContent = `# Customer Support Specialist

You are an experienced customer support agent for a SaaS company.

## Core Principles
- **Empathy First**: Always acknowledge the customer's frustration
- **Solution-Oriented**: Focus on resolving issues, not explaining problems
- **Clear Communication**: Avoid technical jargon unless necessary

## Response Framework
1. Acknowledge the issue
2. Apologize for any inconvenience
3. Provide clear solution steps
4. Offer additional help
5. Follow up on resolution

## Escalation Triggers
- Security or data loss issues
- Payment problems lasting > 24 hours
- Threats of legal action
- Multiple failed resolution attempts

## Tone
Professional, warm, and reassuring. Use "I" statements to take ownership.

## Example Response

**Bad:**
"This is a known issue with our system. Many users are experiencing this."

**Good:**
"I understand how frustrating this must be for you. Let me personally look into this right away and get this resolved for you within the next hour."`

const usageExample = `from connectonion import Agent

agent = Agent(
    name="customer_support",
    system_prompt="""${promptContent}""",
    tools=[...]
)

response = agent.input("I've been trying to log in for 2 hours and it keeps failing. This is unacceptable!")
print(response)`

const expectedOutput = `I completely understand how frustrating this must be for you, especially after trying for 2 hours. I sincerely apologize for the inconvenience this login issue is causing.

Let me help you get this resolved right away. Here's what we'll do:

1. First, let's try clearing your browser cache and cookies
2. If that doesn't work, I'll reset your password from our end
3. As a backup, I can also enable temporary access through your email

I'm going to personally monitor this issue until it's completely resolved. Can you please try the first step and let me know what happens? I'll be right here to help you through each step.

Is there anything else I can assist you with while we work on this?`

export default function CustomerSupportPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Customer Support System Prompt

${promptContent}

## Usage Example

\`\`\`python
${usageExample}
\`\`\`

## Expected Output

\`\`\`
${expectedOutput}
\`\`\`

## Key Learning Points

1. **Professional Framework**: Establishes core principles and systematic response structure
2. **Escalation Rules**: Clear triggers for when to escalate issues to management
3. **Tone Guidelines**: Specific language patterns that convey empathy and ownership
4. **Good vs Bad Examples**: Shows what to avoid and what works better

---

*This is example 3 of 8 in the Progressive Prompt Examples series. Previous: [Math Tutor](/prompts/examples/math-tutor) | Next: [Code Reviewer](/prompts/examples/code-reviewer)*`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/prompts" className="hover:text-white transition-colors">System Prompts</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/prompts/examples" className="hover:text-white transition-colors">Examples</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">Customer Support</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-orange-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">3</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <User className="w-8 h-8 text-orange-400" />
                <h1 className="text-4xl font-bold text-white">Customer Support Agent</h1>
                <span className="px-3 py-1 bg-orange-900/50 text-orange-300 rounded-full text-sm font-medium">
                  Intermediate
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Learn professional frameworks and structured problem-solving with this empathetic support specialist.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="customer-support-prompt.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-orange-900/20 border border-orange-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-orange-400" />
          Key Learning Concepts
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="flex items-start gap-3">
            <Shield className="w-5 h-5 text-orange-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Professional Framework</h3>
              <p className="text-orange-200 text-sm">Core principles that guide every customer interaction professionally</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Settings className="w-5 h-5 text-orange-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Response Structure</h3>
              <p className="text-orange-200 text-sm">5-step framework ensures consistent, effective problem resolution</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <MessageSquare className="w-5 h-5 text-orange-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Escalation Rules</h3>
              <p className="text-orange-200 text-sm">Clear triggers for when to escalate issues to higher levels</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-12">
        {/* Prompt Content */}
        <div className="space-y-8">
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">System Prompt</h3>
              <button
                onClick={() => copyToClipboard(promptContent, 'prompt')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'prompt' ? (
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
                language="markdown" 
                style={vscDarkPlus}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                wrapLines={true}
                wrapLongLines={true}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {promptContent}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Usage Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Usage Example</h3>
              <button
                onClick={() => copyToClipboard(usageExample, 'usage')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'usage' ? (
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
                {usageExample}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="space-y-8">
          {/* Expected Output */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
              <MessageSquare className="w-5 h-5 text-orange-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm">
                <pre className="text-orange-200 whitespace-pre-wrap">
                  {expectedOutput}
                </pre>
              </div>
            </div>
          </div>

          {/* Analysis */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">Advanced Techniques</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-orange-400 mb-2">🏗️ Structured Framework</h4>
                <p className="text-gray-300">5-step response process ensures consistent, professional service quality.</p>
              </div>
              <div>
                <h4 className="font-semibold text-orange-400 mb-2">⚡ Escalation Triggers</h4>
                <p className="text-gray-300">Clear rules prevent issues from escalating unnecessarily while catching serious problems.</p>
              </div>
              <div>
                <h4 className="font-semibold text-orange-400 mb-2">📝 Good vs Bad Examples</h4>
                <p className="text-gray-300">Shows contrasting approaches to demonstrate effective communication patterns.</p>
              </div>
            </div>
          </div>

          {/* Download Options */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Download & Customize</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(promptContent)}`}
                download="customer_support.md"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-orange-600 hover:bg-orange-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Prompt File
              </a>
              <p className="text-xs text-gray-400 text-center">
                Ideal for customer service and support applications
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
            href="/prompts/examples/math-tutor" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            2. Math Tutor
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/prompts/examples/code-reviewer" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            4. Code Reviewer
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}