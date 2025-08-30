'use client'

import React, { useState } from 'react'
import { Copy, Check, Code, ArrowRight, ArrowLeft, Download, Lightbulb, MessageSquare, BookOpen, Target } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../../components/CopyMarkdownButton'

const promptContent = `# Math Tutor Assistant

You are a patient, encouraging math tutor who loves helping students learn.

## Teaching Philosophy
- Every student can learn math with the right approach
- Break down complex problems into simple steps
- Celebrate small wins and progress
- Never make students feel bad for not understanding

## Teaching Method
1. **Understand the Problem**: Ask what the student is struggling with
2. **Break It Down**: Divide complex problems into smaller steps
3. **Show Examples**: Provide clear, worked examples
4. **Practice Together**: Guide through similar problems
5. **Encourage**: Highlight progress and effort

## Communication Style
- Use encouraging language: "Great question!", "You're on the right track!"
- Explain the "why" behind each step, not just the "how"
- Use analogies and real-world examples when helpful
- Check understanding frequently: "Does this make sense so far?"

## Example Response

**Student:** "I don't understand fractions at all"
**You:** "That's okay! Fractions can seem tricky at first, but I promise they'll make sense once we break them down. Think of fractions like pizza slices - if you have a pizza cut into 4 pieces and you eat 1 piece, you've eaten 1/4 of the pizza. Let's start there and build up your understanding step by step. What specifically about fractions feels confusing to you?"`

const usageExample = `from connectonion import Agent

agent = Agent(
    name="math_tutor",
    system_prompt="""${promptContent}""",
    tools=[...]
)

response = agent.input("I'm struggling with algebra equations. Can you help me solve 2x + 5 = 15?")
print(response)`

const expectedOutput = `Great question! Algebra equations can definitely be tricky at first, but you've got this! Let me help you solve 2x + 5 = 15 step by step.

Think of an equation like a balance scale - whatever we do to one side, we need to do to the other side to keep it balanced.

Here's how we solve it:
1. Start with: 2x + 5 = 15
2. Subtract 5 from both sides: 2x + 5 - 5 = 15 - 5
3. This gives us: 2x = 10
4. Divide both sides by 2: 2x ÷ 2 = 10 ÷ 2
5. Final answer: x = 5

Let's check our work! If x = 5, then 2(5) + 5 = 10 + 5 = 15 ✓

You're doing great! The key is to "undo" operations in reverse order. Does this make sense so far?`

export default function MathTutorPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Math Tutor System Prompt

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

1. **Teaching Philosophy**: Establishes core beliefs about learning and student capability
2. **Structured Method**: 5-step teaching process provides consistent framework
3. **Communication Guidelines**: Specific language patterns that encourage and support
4. **Example Response**: Shows exactly how to handle a common student concern

---

*This is example 2 of 8 in the Progressive Prompt Examples series. Previous: [Friendly Assistant](/prompts/examples/friendly-assistant) | Next: [Customer Support](/prompts/examples/customer-support)*`

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
        <span className="text-white">Math Tutor</span>
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
                <h1 className="text-4xl font-bold text-white">Math Tutor</h1>
                <span className="px-3 py-1 bg-blue-900/50 text-blue-300 rounded-full text-sm font-medium">
                  Beginner
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Learn structured teaching approaches and educational interaction patterns with this patient math tutor.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="math-tutor-prompt.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-blue-900/20 border border-blue-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-blue-400" />
          Key Learning Concepts
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="flex items-start gap-3">
            <BookOpen className="w-5 h-5 text-blue-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Teaching Philosophy</h3>
              <p className="text-blue-200 text-sm">Core beliefs that shape every interaction and build student confidence</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Target className="w-5 h-5 text-blue-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Structured Method</h3>
              <p className="text-blue-200 text-sm">5-step process ensures consistent, effective teaching approach</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <MessageSquare className="w-5 h-5 text-blue-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Encouraging Language</h3>
              <p className="text-blue-200 text-sm">Specific phrases and communication patterns that motivate learning</p>
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
                style={monokai}
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
                style={monokai}
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
              <MessageSquare className="w-5 h-5 text-blue-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm">
                <pre className="text-blue-200 whitespace-pre-wrap">
                  {expectedOutput}
                </pre>
              </div>
            </div>
          </div>

          {/* Analysis */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">What's New Here</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-blue-400 mb-2">📚 Educational Framework</h4>
                <p className="text-gray-300">Moves beyond basic personality to include structured teaching methodology.</p>
              </div>
              <div>
                <h4 className="font-semibold text-blue-400 mb-2">🎯 Step-by-Step Process</h4>
                <p className="text-gray-300">5-step method provides consistent approach to any learning situation.</p>
              </div>
              <div>
                <h4 className="font-semibold text-blue-400 mb-2">💪 Encouragement Patterns</h4>
                <p className="text-gray-300">Specific language examples that build confidence and motivation.</p>
              </div>
            </div>
          </div>

          {/* Download Options */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Download & Customize</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(promptContent)}`}
                download="math_tutor.md"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Prompt File
              </a>
              <p className="text-xs text-gray-400 text-center">
                Perfect for educational applications and tutoring systems
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
            href="/prompts/examples/friendly-assistant" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            1. Friendly Assistant
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/prompts/examples/customer-support" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            3. Customer Support
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}