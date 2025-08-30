'use client'

import React, { useState } from 'react'
import { Copy, Check, FileText, Database, Code, File, FileCode } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'

const samePrompt = {
  markdown: `# AI Assistant

You are a helpful AI assistant with expertise in Python programming and software development.

## Core Principles
- Be concise and clear in responses
- Provide code examples when helpful
- Explain complex concepts simply
- Focus on practical solutions

## Communication Style
Professional yet friendly, using technical terms when appropriate but always ensuring clarity.`,

  yaml: `role: AI Assistant
description: A helpful AI assistant with expertise in Python programming and software development

core_principles:
  - Be concise and clear in responses
  - Provide code examples when helpful
  - Explain complex concepts simply
  - Focus on practical solutions

communication_style: Professional yet friendly, using technical terms when appropriate but always ensuring clarity`,

  json: `{
  "role": "AI Assistant",
  "description": "A helpful AI assistant with expertise in Python programming and software development",
  "core_principles": [
    "Be concise and clear in responses",
    "Provide code examples when helpful",
    "Explain complex concepts simply",
    "Focus on practical solutions"
  ],
  "communication_style": "Professional yet friendly, using technical terms when appropriate but always ensuring clarity"
}`,

  txt: `You are a helpful AI assistant with expertise in Python programming and software development.

Core Principles:
- Be concise and clear in responses
- Provide code examples when helpful
- Explain complex concepts simply
- Focus on practical solutions

Communication Style: Professional yet friendly, using technical terms when appropriate but always ensuring clarity.`,

  noext: `You are a helpful AI assistant with expertise in Python programming and software development.

Core Principles:
- Be concise and clear in responses
- Provide code examples when helpful
- Explain complex concepts simply
- Focus on practical solutions

Communication Style: Professional yet friendly, using technical terms when appropriate but always ensuring clarity.`,

  string: `You are a helpful AI assistant with expertise in Python programming and software development.

Core Principles:
- Be concise and clear in responses
- Provide code examples when helpful
- Explain complex concepts simply
- Focus on practical solutions

Communication Style: Professional yet friendly, using technical terms when appropriate but always ensuring clarity.`
}

const formats = [
  { 
    key: 'string', 
    name: 'Direct String', 
    ext: '', 
    icon: <Code className="w-5 h-5" />,
    description: 'Pass prompt directly in code (most common)',
    lang: 'text'
  },
  { 
    key: 'markdown', 
    name: 'Markdown File', 
    ext: '.md', 
    icon: <FileText className="w-5 h-5" />,
    description: 'Structured format with headers and sections',
    lang: 'markdown'
  },
  { 
    key: 'txt', 
    name: 'Plain Text File', 
    ext: '.txt', 
    icon: <File className="w-5 h-5" />,
    description: 'Simple text format',
    lang: 'text'
  },
  { 
    key: 'yaml', 
    name: 'YAML File', 
    ext: '.yaml', 
    icon: <Database className="w-5 h-5" />,
    description: 'Configuration-style key-value format',
    lang: 'yaml'
  },
  { 
    key: 'json', 
    name: 'JSON File', 
    ext: '.json', 
    icon: <Code className="w-5 h-5" />,
    description: 'Structured data format',
    lang: 'json'
  },
  { 
    key: 'noext', 
    name: 'No Extension File', 
    ext: '', 
    icon: <FileCode className="w-5 h-5" />,
    description: 'Any text file works',
    lang: 'text'
  }
]

export default function FormatsPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const getUsageCode = (formatKey: string) => {
    const format = formats.find(f => f.key === formatKey)
    
    if (formatKey === 'string') {
      return `from connectonion import Agent

# Pass prompt directly as string
agent = Agent(
    name="assistant",
    system_prompt="""You are a helpful AI assistant with expertise in Python programming and software development.

Core Principles:
- Be concise and clear in responses
- Provide code examples when helpful
- Explain complex concepts simply
- Focus on practical solutions

Communication Style: Professional yet friendly, using technical terms when appropriate but always ensuring clarity.""",
    tools=[your_tools]
)

# Use the agent
response = agent.input("Hello!")
print(response)`
    }
    
    return `from connectonion import Agent

# Load from ${format?.name.toLowerCase()}
agent = Agent(
    name="assistant",
    system_prompt="prompts/assistant${format?.ext}",
    tools=[your_tools]
)

# Use the agent
response = agent.input("Hello!")
print(response)`
  }

  return (
    <main className="max-w-6xl mx-auto px-8 py-12 lg:py-16 pt-16 lg:pt-20">
      {/* Header */}
      <header className="mb-16">
        <div className="text-center max-w-4xl mx-auto">
          <h1 className="text-4xl md:text-5xl font-bold text-white mb-6">
            File Format Support
          </h1>
          <p className="text-xl md:text-2xl text-gray-300 mb-8">
            Use any text file format for system prompts. ConnectOnion just reads the content.
          </p>
          
          <div className="bg-blue-900/20 border border-blue-500/30 rounded-xl p-6 mb-8">
            <div className="text-lg text-blue-100">
              <strong className="text-blue-300">Key Point:</strong> All formats below create <strong className="text-white">identical agents</strong>. 
              ConnectOnion doesn't parse the format - it just reads the text content and passes it to the LLM.
            </div>
          </div>
        </div>
      </header>

      {/* All Format Examples - Natural Order */}
      <section className="mb-16 space-y-12">
        {formats.map((format, index) => (
          <div key={format.key} className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between bg-gray-800 border-b border-gray-700 px-6 py-4">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-purple-600 flex items-center justify-center text-white font-bold">
                  {index + 1}
                </div>
                {format.icon}
                <div>
                  <h3 className="text-lg font-semibold text-white">{format.name}</h3>
                  <p className="text-sm text-gray-400">{format.description}</p>
                </div>
                {format.ext && (
                  <code className="text-sm text-purple-300 bg-purple-900/30 px-2 py-1 rounded">
                    {format.ext}
                  </code>
                )}
              </div>
            </div>
            
            {/* Usage Code */}
            <div className="border-b border-gray-700">
              <div className="flex items-center justify-between bg-gray-800/50 px-6 py-3">
                <span className="text-sm text-purple-300 font-mono font-semibold">
                  How to Use {format.name}
                </span>
                <button
                  onClick={() => copyToClipboard(getUsageCode(format.key), `usage-${format.key}`)}
                  className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
                >
                  {copiedId === `usage-${format.key}` ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4" />
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
                >
                  {getUsageCode(format.key)}
                </SyntaxHighlighter>
              </div>
            </div>

            {/* File Content */}
            <div>
              <div className="flex items-center justify-between bg-gray-800/30 px-6 py-3">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-400 font-mono">
                    {format.key === 'string' 
                      ? 'system_prompt=""" ... """' 
                      : `assistant${format.ext}`}
                  </span>
                  <span className="text-xs text-gray-500 bg-gray-700 px-2 py-1 rounded">
                    {format.key === 'string' ? 'Inline content' : 'File content'}
                  </span>
                </div>
                <button
                  onClick={() => copyToClipboard(samePrompt[format.key as keyof typeof samePrompt], `content-${format.key}`)}
                  className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
                >
                  {copiedId === `content-${format.key}` ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
              
              <div className="p-6">
                <SyntaxHighlighter 
                  language={format.lang}
                  style={monokai}
                  customStyle={{
                    background: 'transparent',
                    padding: 0,
                    margin: 0,
                    fontSize: '0.8rem',
                    lineHeight: '1.4'
                  }}
                  showLineNumbers={true}
                >
                  {samePrompt[format.key as keyof typeof samePrompt]}
                </SyntaxHighlighter>
              </div>
            </div>
          </div>
        ))}
      </section>

      {/* Summary */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 text-center">All Create the Same Agent</h2>
        
        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between bg-gray-800 border-b border-gray-700 px-4 py-3">
            <span className="text-sm text-gray-400 font-mono">Equivalent Usage</span>
            <button
              onClick={() => copyToClipboard(
                formats.map(f => `agent = Agent("bot", system_prompt="${f.key === 'string' ? '"""..."""' : `prompts/assistant${f.ext}`}")  # ${f.name}`).join('\n'),
                'all'
              )}
              className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
            >
              {copiedId === 'all' ? (
                <Check className="w-4 h-4 text-green-400" />
              ) : (
                <Copy className="w-4 h-4" />
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
                lineHeight: '1.5'
              }}
              showLineNumbers={true}
            >
{`# All of these create identical agents:
agent = Agent("bot", system_prompt="""You are a helpful...""")  # Direct String
agent = Agent("bot", system_prompt="prompts/assistant.md")      # Markdown File
agent = Agent("bot", system_prompt="prompts/assistant.txt")     # Plain Text File
agent = Agent("bot", system_prompt="prompts/assistant.yaml")    # YAML File
agent = Agent("bot", system_prompt="prompts/assistant.json")    # JSON File
agent = Agent("bot", system_prompt="prompts/assistant")         # No Extension File`}
            </SyntaxHighlighter>
          </div>
        </div>
      </section>

      {/* Benefits */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-8 text-center">Why This Matters</h2>
        
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="font-semibold text-white mb-3">✅ No Vendor Lock-in</h3>
            <p className="text-gray-400">Use any format your team prefers. Switch formats without changing code.</p>
          </div>
          
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="font-semibold text-white mb-3">✅ Future-Proof</h3>
            <p className="text-gray-400">New formats work automatically. No need to wait for framework updates.</p>
          </div>
          
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="font-semibold text-white mb-3">✅ Simple</h3>
            <p className="text-gray-400">No complex parsing or schemas. Just reads the text content.</p>
          </div>
          
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="font-semibold text-white mb-3">✅ Flexible</h3>
            <p className="text-gray-400">Team uses YAML? Use YAML. Prefer Markdown? Use Markdown.</p>
          </div>
        </div>
      </section>
    </main>
  )
}