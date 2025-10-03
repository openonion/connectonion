/*
  DESIGN INCONSISTENCY ISSUES FOUND (2025-01-02):
  
  1. **Navigation System Chaos** (Priority: CRITICAL)
     - Uses ContentNavigation component for automatic Previous/Next
     - Has breadcrumb but with "Back to Home" instead of standard breadcrumb
     - Has CopyMarkdownButton component
     - Consistent with main docs pages
     - BUT: Many pages have custom navigation implementations
     - Examples use custom "Previous/Next in series" navigation
     - Blog has simple "Back to Docs" link
     - Roadmap has no page navigation at all
     - FIX: Standardize on ContentNavigation component across ALL pages
  
  2. **Copy Button Implementation** (Priority: HIGH)
     - Some pages have CopyMarkdownButton component (good)
     - Some pages have custom copy implementations
     - Some pages missing copy functionality entirely
     - Different icons and placements
     - FIX: Use CopyMarkdownButton consistently on every documentation page
  
  3. **Code Display Patterns** (Priority: HIGH)  
     - CodeWithResult component used inconsistently
     - Some pages use raw SyntaxHighlighter
     - Line numbers sometimes present, sometimes not
     - Different font sizes and padding across pages
     - FIX: Always use CodeWithResult for code examples with output
  
  4. **Breadcrumb Navigation** (Priority: MEDIUM)
     - Some pages have breadcrumb navigation (Home > Page)
     - Some have "Back to Docs" or "Back to Home" link
     - Format inconsistent across site
     - Icon usage varies (ArrowRight vs ArrowLeft)
     - FIX: Implement consistent breadcrumb component
  
  5. **Page Header Structure** (Priority: MEDIUM)
     - Different layouts for page titles
     - Icon placement varies (left, right, inline)
     - Description text size inconsistent
     - FIX: Create standardized PageHeader component
*/

'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Cpu, Zap, Globe, Brain, DollarSign, Eye, Layers, AlertTriangle } from 'lucide-react'
import CodeWithResult from '../../components/CodeWithResult'
import { CommandBlock } from '../../components/CommandBlock'
import { ContentNavigation } from '../../components/ContentNavigation'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'

export default function ModelsPage() {
  const [activeProvider, setActiveProvider] = useState<'openai' | 'google' | 'anthropic'>('openai')

  const markdownContent = `# Models

ConnectOnion supports the latest models from OpenAI, Google Gemini, and Anthropic Claude. Simply specify the model name when creating an agent.

## Quick Start

\`\`\`python
from connectonion import Agent

# Just change the model name
agent = Agent("assistant", model="gpt-5")              # OpenAI
agent = Agent("assistant", model="gemini-2.5-pro")     # Google
agent = Agent("assistant", model="claude-opus-4.1")    # Anthropic
\`\`\`

## Supported Models

### OpenAI Models
- **gpt-5** - Best for coding and agentic tasks
- **gpt-5-mini** - Faster, cost-efficient version
- **gpt-5-nano** - Fastest, most cost-efficient
- **gpt-4.1** - Smartest non-reasoning model
- **o1** - Advanced reasoning model

### Google Gemini Models
- **gemini-2.5-pro** - Enhanced reasoning, multimodal (audio/video/PDF)
- **gemini-2.0-flash-exp** - Experimental with native tool use
- **gemini-1.5-pro** - 2M token context window
- **gemini-1.5-flash** - Fast and versatile

### Anthropic Claude Models
- **claude-opus-4.1** - Latest and most capable
- **claude-opus-4** - Previous flagship
- **claude-sonnet-4** - Balanced performance
- **claude-3-5-sonnet** - Excellent at coding

## Model Selection Guide

### By Use Case

**Best Overall Performance**
\`\`\`python
agent = Agent("assistant", model="gpt-5")           # OpenAI flagship
agent = Agent("assistant", model="gemini-2.5-pro")  # Google flagship
agent = Agent("assistant", model="claude-opus-4.1") # Anthropic flagship
\`\`\`

**Code Generation**
\`\`\`python
agent = Agent("coder", model="gpt-5")               # Best for coding
agent = Agent("coder", model="claude-opus-4.1")     # Alternative
\`\`\`

**Fast Responses**
\`\`\`python
agent = Agent("quick", model="gpt-5-nano")          # OpenAI fastest
agent = Agent("quick", model="gemini-1.5-flash")    # Google fast
\`\`\`

**Long Context (>200K tokens)**
\`\`\`python
agent = Agent("reader", model="gemini-2.5-pro")     # 2M tokens
agent = Agent("reader", model="gemini-1.5-pro")     # 2M tokens
\`\`\`

## Setting Up API Keys

\`\`\`bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Google Gemini (recommended - matches Google's official SDK)
export GEMINI_API_KEY="AIza..."
# Note: GOOGLE_API_KEY also works but GEMINI_API_KEY is preferred

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
\`\`\`

**Important:** For Gemini models, use \`GEMINI_API_KEY\` as recommended by [Google's official documentation](https://ai.google.dev/gemini-api/docs/api-key). While \`GOOGLE_API_KEY\` is supported for backward compatibility, \`GEMINI_API_KEY\` is the standard used by Google's Python SDK and most tools in the ecosystem.`

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href="/" className="inline-flex items-center text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 mb-8 transition-colors">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Home
      </Link>
      
      <div className="flex items-start justify-between mb-12">
        <div>
          <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-blue-500 to-purple-600 bg-clip-text text-transparent">
            Models
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-400">
            Use the latest AI models from OpenAI, Google, and Anthropic with a single interface.
          </p>
        </div>
        <CopyMarkdownButton content={markdownContent} filename="models.md" />
      </div>

      {/* Quick Start */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold mb-4">Quick Start</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          Simply specify the model name when creating an agent:
        </p>
        <CodeWithResult
          code={`from connectonion import Agent

# Just change the model name
agent = Agent("assistant", model="gpt-5")              # OpenAI
agent = Agent("assistant", model="gemini-2.5-pro")     # Google  
agent = Agent("assistant", model="claude-opus-4.1")    # Anthropic

# Same interface for all
response = agent.input("Explain quantum computing")`}
          result={`Quantum computing harnesses quantum mechanical phenomena...`}
        />
      </section>

      {/* Provider Tabs */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold mb-6">Available Models</h2>
        
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveProvider('openai')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeProvider === 'openai'
                ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            OpenAI
          </button>
          <button
            onClick={() => setActiveProvider('google')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeProvider === 'google'
                ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            Google Gemini
          </button>
          <button
            onClick={() => setActiveProvider('anthropic')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeProvider === 'anthropic'
                ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            Anthropic Claude
          </button>
        </div>

        {activeProvider === 'openai' && (
          <div className="space-y-4">
            <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
              <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
                <Cpu className="mr-2 h-5 w-5 text-blue-400" />
                GPT-5 Series
              </h3>
              <div className="space-y-3">
                <div className="flex items-start">
                  <code className="bg-blue-500/20 text-blue-300 px-2 py-1 rounded text-sm mr-3 font-mono">gpt-5</code>
                  <span className="text-gray-300">Best for coding and agentic tasks across domains</span>
                </div>
                <div className="flex items-start">
                  <code className="bg-blue-500/20 text-blue-300 px-2 py-1 rounded text-sm mr-3 font-mono">gpt-5-mini</code>
                  <span className="text-gray-300">Faster, cost-efficient version for well-defined tasks</span>
                </div>
                <div className="flex items-start">
                  <code className="bg-blue-500/20 text-blue-300 px-2 py-1 rounded text-sm mr-3 font-mono">gpt-5-nano</code>
                  <span className="text-gray-300">Fastest, most cost-efficient version</span>
                </div>
              </div>
            </div>

            <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
              <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
                <Brain className="mr-2 h-5 w-5 text-purple-400" />
                Reasoning Models
              </h3>
              <div className="space-y-3">
                <div className="flex items-start">
                  <code className="bg-purple-500/20 text-purple-300 px-2 py-1 rounded text-sm mr-3 font-mono">o1</code>
                  <span className="text-gray-300">Advanced reasoning and problem solving</span>
                </div>
                <div className="flex items-start">
                  <code className="bg-purple-500/20 text-purple-300 px-2 py-1 rounded text-sm mr-3 font-mono">o1-mini</code>
                  <span className="text-gray-300">Fast reasoning, cost-effective</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeProvider === 'google' && (
          <div className="space-y-4">
            <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
              <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
                <Eye className="mr-2 h-5 w-5 text-green-400" />
                Gemini 2.5
              </h3>
              <div className="space-y-3">
                <div className="flex items-start">
                  <code className="bg-green-500/20 text-green-300 px-2 py-1 rounded text-sm mr-3 font-mono">gemini-2.5-pro</code>
                  <span className="text-gray-300">Enhanced reasoning, supports audio/video/PDF (2M tokens)</span>
                </div>
              </div>
            </div>

            <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
              <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
                <Zap className="mr-2 h-5 w-5 text-yellow-400" />
                Gemini 1.5
              </h3>
              <div className="space-y-3">
                <div className="flex items-start">
                  <code className="bg-yellow-500/20 text-yellow-300 px-2 py-1 rounded text-sm mr-3 font-mono">gemini-1.5-pro</code>
                  <span className="text-gray-300">2M token context window</span>
                </div>
                <div className="flex items-start">
                  <code className="bg-yellow-500/20 text-yellow-300 px-2 py-1 rounded text-sm mr-3 font-mono">gemini-1.5-flash</code>
                  <span className="text-gray-300">Fast and versatile (1M tokens)</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeProvider === 'anthropic' && (
          <div className="space-y-4">
            <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
              <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
                <Layers className="mr-2 h-5 w-5 text-orange-400" />
                Claude Opus 4 Series
              </h3>
              <div className="space-y-3">
                <div className="flex items-start">
                  <code className="bg-orange-500/20 text-orange-300 px-2 py-1 rounded text-sm mr-3 font-mono">claude-opus-4.1</code>
                  <span className="text-gray-300">Latest and most capable (200K tokens)</span>
                </div>
                <div className="flex items-start">
                  <code className="bg-orange-500/20 text-orange-300 px-2 py-1 rounded text-sm mr-3 font-mono">claude-opus-4</code>
                  <span className="text-gray-300">Previous flagship model</span>
                </div>
              </div>
            </div>

            <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
              <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
                <Globe className="mr-2 h-5 w-5 text-purple-400" />
                Claude 3.5 Series
              </h3>
              <div className="space-y-3">
                <div className="flex items-start">
                  <code className="bg-purple-500/20 text-purple-300 px-2 py-1 rounded text-sm mr-3 font-mono">claude-3-5-sonnet</code>
                  <span className="text-gray-300">Excellent at coding</span>
                </div>
                <div className="flex items-start">
                  <code className="bg-purple-500/20 text-purple-300 px-2 py-1 rounded text-sm mr-3 font-mono">claude-3-5-haiku</code>
                  <span className="text-gray-300">Fast and cost-effective</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Model Selection Guide */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold mb-6">Model Selection Guide</h2>
        
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
            <h3 className="font-semibold mb-3 flex items-center text-white">
              <Cpu className="mr-2 h-5 w-5 text-blue-400" />
              Best for Coding
            </h3>
            <CodeWithResult
              code={`agent = Agent("coder", model="gpt-5")
# Alternative: claude-opus-4.1`}
              result=""
            />
          </div>

          <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
            <h3 className="font-semibold mb-3 flex items-center text-white">
              <Zap className="mr-2 h-5 w-5 text-yellow-400" />
              Fast Responses
            </h3>
            <CodeWithResult
              code={`agent = Agent("quick", model="gpt-5-nano")
# Alternative: gemini-1.5-flash`}
              result=""
            />
          </div>

          <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
            <h3 className="font-semibold mb-3 flex items-center text-white">
              <DollarSign className="mr-2 h-5 w-5 text-green-400" />
              Cost-Optimized
            </h3>
            <CodeWithResult
              code={`agent = Agent("budget", model="gpt-5-nano")
# Alternative: gemini-1.5-flash-8b`}
              result=""
            />
          </div>

          <div className="bg-gray-900 border border-gray-700 p-6 rounded-lg">
            <h3 className="font-semibold mb-3 flex items-center text-white">
              <Eye className="mr-2 h-5 w-5 text-purple-400" />
              Multimodal
            </h3>
            <CodeWithResult
              code={`agent = Agent("vision", model="gemini-2.5-pro")
# Supports: audio, video, images, PDF`}
              result=""
            />
          </div>
        </div>
      </section>

      {/* API Keys Setup */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold mb-4">Setting Up API Keys</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          Set environment variables for the providers you want to use:
        </p>
        <CommandBlock
          commands={[
            'export OPENAI_API_KEY="sk-..."',
            'export GEMINI_API_KEY="AIza..."',
            'export ANTHROPIC_API_KEY="sk-ant-..."'
          ]}
        />
      </section>

      {/* Smart Model Selection */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold mb-4">Smart Model Selection</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          Automatically select the best model based on your needs:
        </p>
        <CodeWithResult
          code={`def select_model(task_type: str, speed_priority: bool = False) -> str:
    """Select optimal model based on requirements."""
    
    if speed_priority:
        return {
            "code": "gpt-5-mini",
            "chat": "gpt-5-nano",
            "analysis": "gemini-1.5-flash"
        }.get(task_type, "gpt-5-nano")
    else:
        return {
            "code": "gpt-5",
            "reasoning": "gemini-2.5-pro",
            "analysis": "claude-opus-4.1"
        }.get(task_type, "gpt-5")

# Use appropriate model
model = select_model("code", speed_priority=False)
agent = Agent("coder", model=model)`}
          result={`Selected model: gpt-5`}
        />
      </section>

      {/* Fallback Chain */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold mb-4">Fallback Chain</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          Try multiple models if one fails:
        </p>
        <CodeWithResult
          code={`def create_agent_with_fallback(name: str):
    """Try multiple models if one fails."""
    
    model_chain = [
        "gpt-5",           # Best overall
        "claude-opus-4.1", # Strong alternative
        "gemini-2.5-pro",  # Multimodal option
        "gpt-5-mini"       # Faster fallback
    ]
    
    for model in model_chain:
        try:
            return Agent(name, model=model)
        except Exception as e:
            print(f"Failed with {model}: {e}")
            continue
    
    raise Exception("No models available")

# Will use best available model
agent = create_agent_with_fallback("assistant")`}
          result={`Using model: gpt-5`}
        />
      </section>

      {/* Comparison Table */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold mb-6">Model Comparison</h2>
        
        <div className="overflow-x-auto">
          <table className="w-full border border-gray-200 dark:border-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Model</th>
                <th className="px-4 py-3 text-left font-semibold">Provider</th>
                <th className="px-4 py-3 text-left font-semibold">Context</th>
                <th className="px-4 py-3 text-left font-semibold">Strengths</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              <tr>
                <td className="px-4 py-3"><code className="text-sm">gpt-5</code></td>
                <td className="px-4 py-3">OpenAI</td>
                <td className="px-4 py-3">200K</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">Best for coding & agentic tasks</td>
              </tr>
              <tr>
                <td className="px-4 py-3"><code className="text-sm">gemini-2.5-pro</code></td>
                <td className="px-4 py-3">Google</td>
                <td className="px-4 py-3">2M</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">Multimodal, huge context</td>
              </tr>
              <tr>
                <td className="px-4 py-3"><code className="text-sm">claude-opus-4.1</code></td>
                <td className="px-4 py-3">Anthropic</td>
                <td className="px-4 py-3">200K</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">Most capable Claude</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Warning Box */}
      <div className="bg-yellow-50 dark:bg-yellow-900/20 p-6 rounded-lg border border-yellow-200 dark:border-yellow-800 mb-12">
        <h3 className="font-semibold mb-2 flex items-center">
          <AlertTriangle className="mr-2 h-5 w-5 text-yellow-600" />
          Important Notes
        </h3>
        <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
          <li>• You need an API key from at least one provider to use ConnectOnion</li>
          <li>• Tool support works identically across all models</li>
          <li>• The same agent code works with any model - just change the model name</li>
          <li>• Some models may have different pricing and rate limits</li>
        </ul>
      </div>

      {/* Navigation */}
      <ContentNavigation />
    </div>
  )
}