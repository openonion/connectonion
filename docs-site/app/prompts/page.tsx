'use client'

import { useState } from 'react'
import { Copy, Check, FileText, Play, ArrowRight } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'

export default function PromptsOverviewPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const quickStartCode = `from connectonion import Agent

# Method 1: Direct string
agent = Agent(
    name="helper",
    system_prompt="You are a helpful and friendly assistant.",
    tools=[...]
)

# Method 2: Load from file
agent = Agent(
    name="expert",
    system_prompt="prompts/expert.md",  # Auto-loads content
    tools=[...]
)

# Method 3: Path object
from pathlib import Path
agent = Agent(
    name="specialist",
    system_prompt=Path("prompts/specialist.txt"),
    tools=[...]
)`

  const markdownContent = `# System Prompts Guide

Learn how to craft effective system prompts that define your agent's personality, behavior, and approach to tasks.

## Quick Start

ConnectOnion offers three flexible ways to provide system prompts to your agents:

### Method 1: Direct String
\`\`\`python
agent = Agent(
    name="helper",
    system_prompt="You are a helpful and friendly assistant.",
    tools=[...]
)
\`\`\`

### Method 2: Load from File
\`\`\`python
agent = Agent(
    name="expert",
    system_prompt="prompts/expert.md",  # Auto-loads content
    tools=[...]
)
\`\`\`

### Method 3: Path Object
\`\`\`python
from pathlib import Path
agent = Agent(
    name="specialist",
    system_prompt=Path("prompts/specialist.txt"),
    tools=[...]
)
\`\`\`

## Supported File Formats

ConnectOnion supports multiple prompt formats:

- **.md** - Markdown files for human-readable, structured prompts
- **.yaml/.yml** - YAML format for structured data with metadata
- **.json** - JSON format for machine-readable prompts with schemas
- **.txt** - Plain text files for simple prompts
- **No extension** - Any text file works

## Best Practices

1. **Define Clear Role** - Start with who the agent is and their expertise
2. **Set Behavioral Guidelines** - Specify how the agent should act and communicate
3. **Include Domain Knowledge** - Add specific knowledge areas and constraints
4. **Specify Output Format** - Define how responses should be structured

## What's Next

- [Best Practices](/prompts/best-practices) - Learn proven patterns for writing effective prompts
- [Examples](/prompts/examples) - Browse real-world prompt examples for different roles
- [File Organization](/prompts/organization) - Learn how to organize your prompt files
- [Testing](/prompts/testing) - Test and validate your system prompts
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
            <span className="text-white">System Prompts</span>
          </nav>

          <h1 className="text-4xl font-bold text-white mb-4">System Prompts</h1>
          <p className="text-xl text-gray-300 max-w-3xl">
            Learn how to craft effective system prompts that define your agent's personality, 
            behavior, and approach to tasks.
          </p>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="system-prompts-guide.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Quick Start */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Quick Start</h2>
        
        <p className="text-gray-300 mb-8">
          ConnectOnion offers three flexible ways to provide system prompts to your agents:
        </p>

        <div className="grid lg:grid-cols-2 gap-8 mb-8">
          <div className="space-y-6">
            <div className="flex items-start gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg">
              <div className="w-8 h-8 bg-blue-900/50 border border-blue-500 rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-blue-400 font-bold text-sm">1</span>
              </div>
              <div>
                <h4 className="font-semibold text-blue-400 mb-2">Direct String</h4>
                <p className="text-gray-300 text-sm">
                  Pass prompt text directly as a parameter. Perfect for simple, short prompts.
                </p>
              </div>
            </div>
            
            <div className="flex items-start gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg">
              <div className="w-8 h-8 bg-green-900/50 border border-green-500 rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-green-400 font-bold text-sm">2</span>
              </div>
              <div>
                <h4 className="font-semibold text-green-400 mb-2">File Path</h4>
                <p className="text-gray-300 text-sm">
                  Auto-loads content from .md, .txt, .yaml, or .json files. Best for complex prompts.
                </p>
              </div>
            </div>
            
            <div className="flex items-start gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg">
              <div className="w-8 h-8 bg-purple-900/50 border border-purple-500 rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-purple-400 font-bold text-sm">3</span>
              </div>
              <div>
                <h4 className="font-semibold text-purple-400 mb-2">Path Object</h4>
                <p className="text-gray-300 text-sm">
                  Use pathlib.Path for programmatic file handling with existence checking.
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

      {/* Supported Formats */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Supported File Formats</h2>
        
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
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