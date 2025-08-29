'use client'

import { useState } from 'react'
import { Copy, Check, FileText, Play, ArrowRight, Info, AlertTriangle, FolderOpen } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyPromptButton } from '../../components/CopyPromptButton'

export default function PromptsOverviewPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const quickStartCode = `from connectonion import Agent

# Method 1 (Recommended): Load from Markdown file
agent = Agent(
    name="expert",
    system_prompt="prompts/expert.md",  # Versioned prompt content
    tools=[...]
)

# Method 2: Path object
from pathlib import Path
agent = Agent(
    name="specialist",
    system_prompt=Path("prompts/specialist.txt"),
    tools=[...]
)`

  const recommendedMarkdown = `# Assistant
You are a helpful, concise assistant. When answering:

- Be direct and use simple language
- Prefer bullet points over long paragraphs
- Ask one clarifying question if necessary before acting

Output format:
- Start with a one-sentence summary
- Then provide numbered steps if applicable
`

  const loadFromMarkdown = `from connectonion import Agent

agent = Agent(
    name="assistant",
    system_prompt="prompts/assistant.md",  # Recommended: Markdown file
    tools=[...]
)

print(agent.input("Summarize the key points of our meeting notes."))`

  const folderTree = `prompts/
  assistant.md
  expert/
    researcher.md
`

  const iterationCode = `from connectonion import Agent

# Set a global limit for this agent
agent = Agent(
    name="helper",
    system_prompt="You are precise and concise.",
    tools=[...],
    max_iterations=15  # default limit for this agent
)

# For one-off complex tasks, override per call
result = agent.input(
    "Plan a 3-step workflow using the available tools",
    max_iterations=25
)`


  return (
    <div className="max-w-4xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Header with Copy Button */}
      <div className="flex items-start justify-between mb-8">
        <div className="flex-1">
          {/* Breadcrumb */}
          <nav className="flex items-center gap-2 text-sm text-gray-400 mb-4">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <ArrowRight className="w-4 h-4" />
            <span className="text-white">System Prompts</span>
          </nav>

          <h1 className="text-4xl font-bold text-white mb-4">System Prompts</h1>
          <p className="text-xl text-gray-300 max-w-3xl">
            Learn how to craft effective system prompts that define your agent's personality, 
            behavior, and approach to tasks.
          </p>
        </div>
        
        <CopyPromptButton />
      </div>

      {/* Recommended: Markdown Files */}
      <section className="mb-16">
        <div className="bg-gradient-to-b from-emerald-900/30 to-emerald-800/10 border border-emerald-500/30 rounded-xl p-6 mb-6">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-emerald-400 mt-0.5" />
            <div>
              <h2 className="text-xl font-semibold text-white mb-2">Recommended: Keep prompts in Markdown files</h2>
              <p className="text-gray-300 text-sm mb-3">
                Store prompts in versioned <code className="bg-black/30 px-1 py-0.5 rounded">.md</code> files. This keeps code clean, enables easy edits and reviews, and works across tools.
              </p>
              <ul className="list-disc list-inside text-gray-300 text-sm space-y-1">
                <li>Readable and diff-friendly</li>
                <li>Reusable across multiple agents</li>
                <li>Simple to test and iterate</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6">
          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
              <span className="text-sm text-gray-300 font-mono flex items-center gap-2"><FolderOpen className="w-4 h-4"/>project structure</span>
              <button
                onClick={() => copyToClipboard(folderTree, 'folderTree')}
                className="text-gray-400 hover:text-white transition-colors p-1"
              >
                {copiedId === 'folderTree' ? (
                  <Check className="w-4 h-4 text-green-400" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
            <div className="p-6">
              <SyntaxHighlighter 
                language="bash" 
                style={vscDarkPlus}
                customStyle={{ background: 'transparent', padding: 0, margin: 0, fontSize: '0.875rem', lineHeight: '1.6' }}
              >
                {folderTree}
              </SyntaxHighlighter>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-gray-800">
              <span className="text-sm text-gray-300 font-mono">prompts/assistant.md</span>
              <button
                onClick={() => copyToClipboard(recommendedMarkdown, 'recommendedMarkdown')}
                className="text-gray-400 hover:text-white transition-colors p-1"
              >
                {copiedId === 'recommendedMarkdown' ? (
                  <Check className="w-4 h-4 text-green-400" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
            <div className="p-6">
              <SyntaxHighlighter 
                language="markdown" 
                style={vscDarkPlus}
                customStyle={{ background: 'transparent', padding: 0, margin: 0, fontSize: '0.875rem', lineHeight: '1.6' }}
              >
                {recommendedMarkdown}
              </SyntaxHighlighter>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-gray-800">
              <span className="text-sm text-gray-300 font-mono">load_markdown.py</span>
              <button
                onClick={() => copyToClipboard(loadFromMarkdown, 'loadFromMarkdown')}
                className="text-gray-400 hover:text-white transition-colors p-1"
              >
                {copiedId === 'loadFromMarkdown' ? (
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
                customStyle={{ background: 'transparent', padding: 0, margin: 0, fontSize: '0.875rem', lineHeight: '1.6' }}
              >
                {loadFromMarkdown}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>

        <div className="bg-gradient-to-b from-rose-900/30 to-rose-800/10 border border-rose-500/30 rounded-xl p-5 mt-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-rose-400 mt-0.5" />
            <p className="text-gray-300 text-sm">
              Avoid embedding large prompt strings directly in code. It makes diffs noisy and complicates collaboration. Prefer <code className="bg-black/30 px-1 py-0.5 rounded">.md</code> files and reference them from your agent.
            </p>
          </div>
        </div>
      </section>

      {/* Quick Start */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Quick Start</h2>
        
        <p className="text-gray-300 mb-8">
          ConnectOnion offers three ways to provide system prompts. We recommend Markdown files.
        </p>

        <div className="grid grid-cols-1 gap-8 mb-8">
          <div className="space-y-6">
            <div className="flex items-start gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg">
              <div className="w-8 h-8 bg-green-900/50 border border-green-500 rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-green-400 font-bold text-sm">1</span>
              </div>
              <div>
                <h4 className="font-semibold text-green-400 mb-2">Markdown File (Recommended)</h4>
                <p className="text-gray-300 text-sm">
                  Store prompts in <code className="bg-black/30 px-1 py-0.5 rounded">prompts/*.md</code> and reference by path. Best for collaboration, reviews, and reuse.
                </p>
              </div>
            </div>
            
            <div className="flex items-start gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg">
              <div className="w-8 h-8 bg-blue-900/50 border border-blue-500 rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-blue-400 font-bold text-sm">2</span>
              </div>
              <div>
                <h4 className="font-semibold text-blue-400 mb-2">Path Object</h4>
                <p className="text-gray-300 text-sm">
                  Use <code className="bg-black/30 px-1 py-0.5 rounded">pathlib.Path</code> when you need explicit file existence checks.
                </p>
              </div>
            </div>
            
            <div className="flex items-start gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg">
              <div className="w-8 h-8 bg-purple-900/50 border border-purple-500 rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-purple-400 font-bold text-sm">3</span>
              </div>
              <div>
                <h4 className="font-semibold text-purple-400 mb-2">Direct String (for quick demos)</h4>
                <p className="text-gray-300 text-sm">
                  Acceptable for tiny demos or notebooks, but keep production prompts in Markdown files.
                </p>
              </div>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
              <span className="text-sm text-gray-300 font-mono">quick_start.py</span>
              <button
                onClick={() => copyToClipboard(quickStartCode, 'quick-start')}
                className="text-gray-400 hover:text-white transition-colors p-1"
              >
                {copiedId === 'quick-start' ? (
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
                {quickStartCode}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>
      </section>

      {/* Iteration Control */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Iteration Control (max_iterations)</h2>
        <p className="text-gray-300 mb-6">
          You can set a default iteration limit on the agent, and still override it for specific tasks.
        </p>

        <div className="bg-gray-900 border border-gray-700 rounded-lg">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
            <span className="text-sm text-gray-300 font-mono">iterations.py</span>
            <button
              onClick={() => copyToClipboard(iterationCode, 'iterations')}
              className="text-gray-400 hover:text-white transition-colors p-1"
            >
              {copiedId === 'iterations' ? (
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
              customStyle={{ background: 'transparent', padding: 0, margin: 0, fontSize: '0.875rem', lineHeight: '1.5' }}
            >
              {iterationCode}
            </SyntaxHighlighter>
          </div>
        </div>
      </section>

      {/* Supported Formats */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Supported File Formats</h2>
        
        <div className="grid grid-cols-1 gap-4">
          {[
            { ext: '.md', name: 'Markdown', desc: 'Human-readable, structured prompts', color: 'text-blue-400' },
            { ext: '.yaml', name: 'YAML', desc: 'Structured data with metadata', color: 'text-green-400' },
            { ext: '.json', name: 'JSON', desc: 'Machine-readable with schemas', color: 'text-purple-400' },
            { ext: '.txt', name: 'Plain Text', desc: 'Simple text prompts', color: 'text-yellow-400' },
            { ext: 'none', name: 'No Extension', desc: 'Any text file works', color: 'text-gray-400' },
          ].map((format) => (
            <div key={format.ext} className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-gray-600 transition-colors">
              <div className="flex items-center gap-2 mb-2">
                <FileText className={`w-5 h-5 ${format.color}`} />
                <span className={`font-mono font-bold ${format.color}`}>
                  {format.ext === 'none' ? '(none)' : format.ext}
                </span>
              </div>
              <h3 className="font-semibold text-white mb-1">{format.name}</h3>
              <p className="text-gray-400 text-sm">{format.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* What's Next */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">What's Next</h2>
        
        <div className="grid md:grid-cols-2 gap-6">
          <Link 
            href="/prompts/best-practices" 
            className="group bg-gray-900 border border-gray-700 rounded-lg p-6 hover:border-blue-500/50 transition-all"
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-white">Best Practices</h3>
              <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-blue-400 transition-colors" />
            </div>
            <p className="text-gray-400 text-sm mb-4">
              Learn proven patterns for writing effective system prompts that guide agent behavior.
            </p>
            <div className="text-xs text-blue-400">Read guide →</div>
          </Link>

          <Link 
            href="/prompts/examples" 
            className="group bg-gray-900 border border-gray-700 rounded-lg p-6 hover:border-green-500/50 transition-all"
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-white">Examples</h3>
              <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-green-400 transition-colors" />
            </div>
            <p className="text-gray-400 text-sm mb-4">
              Browse real-world prompt examples for different roles and domains.
            </p>
            <div className="text-xs text-green-400">View examples →</div>
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
          href="/prompts/best-practices" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          Best Practices
          <ArrowRight className="w-4 h-4" />
        </Link>
      </nav>
    </div>
  )
}