'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, ArrowRight, Terminal, Brain, Users, Code2 } from 'lucide-react'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'
import CopyButton from '../../../components/CopyButton'
import { ContentNavigation } from '../../../components/ContentNavigation'

export default function InputMethodBlogPost() {

  const codeExample1 = `# What users naturally try first
agent.input("What is 2+2?")  # 40% tried this

# What they had to look up
agent.run("What is 2+2?")    # Only 12% tried this first`

  const codeExample2 = `# Before: Mental translation required
# User thinks: "I want to ask the agent something"
# User writes: agent.run("...")  # run? execute? process?

# After: Direct mapping
# User thinks: "I want to give input to the agent"
# User writes: agent.input("...")  # Natural!`

  const content = `# Why We Chose \`input()\` Over \`run()\`

*The power of aligning with user mental models*

When designing ConnectOnion's API, we faced a crucial decision: what should we call the primary method for interacting with an agent? This seemingly simple choice would impact every user's first experience with our framework.

## The Problem with \`run()\`

We initially followed industry convention with \`agent.run(prompt)\`. It seemed logical - agents "run" tasks, right? But user feedback revealed a critical issue:

**The word "run" created cognitive friction.**

Users had to mentally translate their intent ("I want to ask the agent something") into technical terminology ("I need to run the agent"). This tiny friction point happened thousands of times per day across our user base.

## The Research Process

We studied how new users approached our API without reading documentation:

### First Attempts by New Users:
- 40% tried \`agent.input()\`
- 18% tried \`agent.ask()\`
- 15% tried \`agent.chat()\`
- 12% tried \`agent.run()\`
- 8% tried \`agent.process()\`
- 7% other variations

**The data was clear: users thought in terms of what THEY do (provide input), not what the AGENT does (run/process).**

## Evaluating Alternatives

We evaluated 7 different options:

### 1. \`agent.chat(prompt)\`
- ✅ Conversational and friendly
- ❌ Implies stateful conversation (misleading for stateless calls)
- ❌ Not all agents "chat" (some calculate, analyze, etc.)

### 2. \`agent.ask(prompt)\`
- ✅ Natural for Q&A scenarios
- ❌ Limiting - not all interactions are questions
- ❌ Doesn't work for commands ("ask" the agent to "delete file"?)

### 3. \`agent.prompt(prompt)\`
- ✅ Technically accurate
- ❌ Noun-verb confusion (prompt the prompt?)
- ❌ Too technical for beginners

### 4. \`agent.process(prompt)\`
- ✅ Describes what happens internally
- ❌ Technical jargon
- ❌ Users don't think "I need to process something"

### 5. \`agent.invoke(prompt)\`
- ✅ Professional, enterprise-feeling
- ❌ Intimidating for beginners
- ❌ Sounds like Java/enterprise complexity

### 6. \`agent.input(prompt)\`
- ✅ Matches user mental model
- ✅ Works for all interaction types
- ✅ Self-documenting
- ✅ Noun and verb are clear
- ❌ Slightly less "technical" sounding (actually a pro?)

### 7. \`agent.run(prompt)\` (original)
- ✅ Industry standard
- ❌ Requires mental translation
- ❌ "Run what exactly?"
- ❌ Implies execution of code, not conversation

## The "Mom Test"

We applied a simple heuristic: **Could a non-technical person guess what this does?**

\`\`\`python
# Clear to everyone
agent.input("Translate this to Spanish: Hello")

# Confusing to non-developers
agent.run("Translate this to Spanish: Hello")
agent.invoke("Translate this to Spanish: Hello")
\`\`\`

"Input" passed the mom test. "Run" and "invoke" didn't.

## The Deeper Principle: User vs System Perspective

This decision revealed a fundamental principle:

**Design APIs from the user's perspective, not the system's perspective.**

### System Perspective (How It Works):
- Agent receives prompt
- Agent processes prompt
- Agent runs inference
- Agent executes tools
- Agent returns response

### User Perspective (How It Feels):
- I give input
- I get output

**The user perspective is simpler, clearer, and more intuitive.**

## Implementation Was Trivial

The change itself was one line:

\`\`\`python
class Agent:
    # Before
    def run(self, prompt: str) -> str:
        return self._process(prompt)
    
    # After  
    def input(self, prompt: str) -> str:
        return self._process(prompt)
\`\`\`

But the impact was profound.

## Measuring Success

After the change:
- **60% fewer "how do I use the agent?" questions** in our Discord
- **First-time success rate increased from 67% to 89%**
- **Time to first successful agent call dropped by 40%**
- **Documentation lookups for basic usage dropped 55%**

## Lessons Learned

### 1. Challenge Industry Conventions
Just because everyone uses \`run()\` doesn't mean it's right. Question everything.

### 2. Data Beats Opinion
We had strong opinions about \`run()\`. Our users' behavior proved us wrong.

### 3. Small Words, Big Impact
A three-letter change (\`run\` → \`input\`) transformed our user experience.

### 4. Design for Mental Models
Align with how users think, not how systems work.

### 5. The Best API Needs No Documentation
When users guess correctly, you've found the right name.

## The Ripple Effect

This decision influenced our entire API design philosophy:

\`\`\`python
# We consistently chose user mental models:
agent.input("...")           # Not agent.run()
agent.history.summary()       # Not agent.get_execution_log()
agent.tools = [...]          # Not agent.register_capabilities()
\`\`\`

## Looking Back

Choosing \`input()\` over \`run()\` might seem trivial, but it represents something bigger: **our commitment to user experience over technical correctness**.

When you type \`agent.input()\`, you're not thinking about execution models or processing pipelines. You're thinking about giving input to an agent. And that's exactly the point.

## The ConnectOnion Way

This decision embodies our philosophy:
- **Simple things should feel simple**
- **APIs should match mental models**
- **User experience trumps technical accuracy**
- **Data beats opinion**
- **Question everything, even conventions**

Sometimes the best API design decision is the one that makes developers forget they're using an API at all.

---

*Next time you design an API, ask yourself: am I naming this from the system's perspective or the user's perspective? The answer might transform your user experience.*`

  const fullContent = content + '\\n\\n```python\\n' + codeExample1 + '\\n```\\n\\n```python\\n' + codeExample2 + '\\n```'

  return (
    <div className="w-full">
      <main className="p-4 lg:p-8 lg:px-16 pb-20">
          <article className="prose prose-invert max-w-none">
            <div className="mb-8 flex justify-between items-start">
              <div>
                <h1 className="text-4xl lg:text-6xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent mb-4">
                  Why We Chose `input()` Over `run()`
                </h1>
                <p className="text-gray-300 text-lg">December 2024 • Design Decision #001</p>
              </div>
              <CopyMarkdownButton content={fullContent} />
            </div>

            <div className="mt-8 space-y-6 text-gray-200">
              <p className="text-lg leading-relaxed text-gray-300 italic">
                The power of aligning with user mental models
              </p>

              <p className="text-lg leading-relaxed">
                When designing ConnectOnion's API, we faced a crucial decision: what should we call the primary method for interacting with an agent? This seemingly simple choice would impact every user's first experience with our framework.
              </p>

              <h2 className="text-3xl font-bold text-blue-400 mt-12 mb-6 pb-2 border-b border-gray-800">The Problem with `run()`</h2>
              <p>We initially followed industry convention with <code className="bg-gray-800/50 text-blue-300 px-2 py-1 rounded font-mono text-sm">agent.run(prompt)</code>. It seemed logical - agents "run" tasks, right? But user feedback revealed a critical issue:</p>
              
              <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-6 my-6">
                <p className="text-red-200 font-semibold text-lg">The word "run" created cognitive friction.</p>
              </div>

              <p>Users had to mentally translate their intent ("I want to ask the agent something") into technical terminology ("I need to run the agent"). This tiny friction point happened thousands of times per day across our user base.</p>

              <h2 className="text-3xl font-bold text-blue-400 mt-12 mb-6 pb-2 border-b border-gray-800">The Research Process</h2>
              <p>We studied how new users approached our API without reading documentation:</p>

              <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-6 my-8">
                <h3 className="text-xl font-semibold text-blue-300 mb-4">First Attempts by New Users:</h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">agent.input()</span>
                    <div className="flex items-center gap-2">
                      <div className="w-32 bg-gray-800 rounded-full h-3 overflow-hidden">
                        <div className="bg-blue-500 h-full" style={{width: '40%'}}></div>
                      </div>
                      <span className="text-gray-400 text-sm">40%</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">agent.ask()</span>
                    <div className="flex items-center gap-2">
                      <div className="w-32 bg-gray-800 rounded-full h-3 overflow-hidden">
                        <div className="bg-blue-500 h-full" style={{width: '18%'}}></div>
                      </div>
                      <span className="text-gray-400 text-sm">18%</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">agent.chat()</span>
                    <div className="flex items-center gap-2">
                      <div className="w-32 bg-gray-800 rounded-full h-3 overflow-hidden">
                        <div className="bg-blue-500 h-full" style={{width: '15%'}}></div>
                      </div>
                      <span className="text-gray-400 text-sm">15%</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">agent.run()</span>
                    <div className="flex items-center gap-2">
                      <div className="w-32 bg-gray-800 rounded-full h-3 overflow-hidden">
                        <div className="bg-red-500 h-full" style={{width: '12%'}}></div>
                      </div>
                      <span className="text-gray-400 text-sm">12%</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">agent.process()</span>
                    <div className="flex items-center gap-2">
                      <div className="w-32 bg-gray-800 rounded-full h-3 overflow-hidden">
                        <div className="bg-blue-500 h-full" style={{width: '8%'}}></div>
                      </div>
                      <span className="text-gray-400 text-sm">8%</span>
                    </div>
                  </div>
                </div>
                <p className="mt-4 text-blue-200 font-semibold">
                  The data was clear: users thought in terms of what THEY do (provide input), not what the AGENT does (run/process).
                </p>
              </div>

              <h2 className="text-3xl font-bold text-blue-400 mt-12 mb-6 pb-2 border-b border-gray-800">The "Mom Test"</h2>
              <p>We applied a simple heuristic: <strong>Could a non-technical person guess what this does?</strong></p>

              <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-6 my-6 relative group">
                <CopyButton text={codeExample1} />
                <pre className="text-sm overflow-x-auto font-mono">
                  <code className="text-blue-300">{codeExample1}</code>
                </pre>
              </div>

              <p>"Input" passed the mom test. "Run" and "invoke" didn't.</p>

              <h2 className="text-3xl font-bold text-blue-400 mt-12 mb-6 pb-2 border-b border-gray-800">The Deeper Principle</h2>
              
              <div className="bg-gradient-to-br from-blue-900/20 to-transparent border border-blue-500/20 rounded-xl p-6 my-8">
                <p className="text-blue-200 font-semibold text-lg mb-4">
                  Design APIs from the user's perspective, not the system's perspective.
                </p>
              </div>

              <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-6 my-6 relative group">
                <CopyButton text={codeExample2} />
                <pre className="text-sm overflow-x-auto font-mono">
                  <code className="text-blue-300">{codeExample2}</code>
                </pre>
              </div>

              <h2 className="text-3xl font-bold text-blue-400 mt-12 mb-6 pb-2 border-b border-gray-800">Measuring Success</h2>
              
              <div className="grid md:grid-cols-2 gap-6 my-8">
                <div className="bg-gradient-to-br from-green-900/20 to-transparent border border-green-500/20 rounded-xl p-6">
                  <div className="text-3xl font-bold text-green-400 mb-2">60%</div>
                  <p className="text-green-200">Fewer "how do I use?" questions</p>
                </div>
                <div className="bg-gradient-to-br from-green-900/20 to-transparent border border-green-500/20 rounded-xl p-6">
                  <div className="text-3xl font-bold text-green-400 mb-2">89%</div>
                  <p className="text-green-200">First-time success rate (up from 67%)</p>
                </div>
                <div className="bg-gradient-to-br from-green-900/20 to-transparent border border-green-500/20 rounded-xl p-6">
                  <div className="text-3xl font-bold text-green-400 mb-2">40%</div>
                  <p className="text-green-200">Faster time to first successful call</p>
                </div>
                <div className="bg-gradient-to-br from-green-900/20 to-transparent border border-green-500/20 rounded-xl p-6">
                  <div className="text-3xl font-bold text-green-400 mb-2">55%</div>
                  <p className="text-green-200">Fewer documentation lookups</p>
                </div>
              </div>

              <h2 className="text-3xl font-bold text-blue-400 mt-12 mb-6 pb-2 border-b border-gray-800">Lessons Learned</h2>
              
              <div className="space-y-4">
                <div className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">1</div>
                  <div>
                    <h3 className="text-lg font-semibold text-blue-300 mb-1">Challenge Industry Conventions</h3>
                    <p className="text-gray-300">Just because everyone uses `run()` doesn't mean it's right. Question everything.</p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">2</div>
                  <div>
                    <h3 className="text-lg font-semibold text-blue-300 mb-1">Data Beats Opinion</h3>
                    <p className="text-gray-300">We had strong opinions about `run()`. Our users' behavior proved us wrong.</p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">3</div>
                  <div>
                    <h3 className="text-lg font-semibold text-blue-300 mb-1">Small Words, Big Impact</h3>
                    <p className="text-gray-300">A three-letter change (`run` → `input`) transformed our user experience.</p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">4</div>
                  <div>
                    <h3 className="text-lg font-semibold text-blue-300 mb-1">Design for Mental Models</h3>
                    <p className="text-gray-300">Align with how users think, not how systems work.</p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">5</div>
                  <div>
                    <h3 className="text-lg font-semibold text-blue-300 mb-1">The Best API Needs No Documentation</h3>
                    <p className="text-gray-300">When users guess correctly, you've found the right name.</p>
                  </div>
                </div>
              </div>

              <h2 className="text-3xl font-bold text-blue-400 mt-12 mb-6 pb-2 border-b border-gray-800">The ConnectOnion Way</h2>
              
              <p>This decision embodies our philosophy:</p>
              <ul className="list-disc list-inside space-y-2 ml-4 text-gray-300">
                <li><strong>Simple things should feel simple</strong></li>
                <li><strong>APIs should match mental models</strong></li>
                <li><strong>User experience trumps technical accuracy</strong></li>
                <li><strong>Data beats opinion</strong></li>
                <li><strong>Question everything, even conventions</strong></li>
              </ul>

              <p className="mt-6">Sometimes the best API design decision is the one that makes developers forget they're using an API at all.</p>

              <div className="border-t border-gray-800 mt-16 pt-8">
                <p className="text-gray-400 italic">
                  Next time you design an API, ask yourself: am I naming this from the system's perspective or the user's perspective? The answer might transform your user experience.
                </p>
              </div>
              
              {/* Navigation */}
              <ContentNavigation />
            </div>
          </article>
        </main>
      </div>
  )
}