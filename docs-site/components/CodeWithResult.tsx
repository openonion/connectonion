'use client'

import { useState } from 'react'
import { Copy, Check, Play, Terminal } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface CodeWithResultProps {
  code: string
  result?: string
  language?: string
  className?: string
  showRunButton?: boolean
}

export default function CodeWithResult({ 
  code, 
  result, 
  language = 'python',
  className = '',
  showRunButton = false
}: CodeWithResultProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Function to render Python REPL output with syntax highlighting
  const renderPythonRepl = (text: string) => {
    const lines = text.split('\n')
    
    return lines.map((line, index) => {
      const trimmedLine = line.trimStart()
      const indent = line.length - trimmedLine.length
      
      // Python prompt lines
      if (trimmedLine.startsWith('>>>') || trimmedLine.startsWith('...')) {
        const prompt = trimmedLine.substring(0, 3)
        const code = trimmedLine.substring(3)
        
        return (
          <div key={index} className="font-mono text-sm">
            <span className="text-green-400">{' '.repeat(indent)}{prompt}</span>
            <span className="text-gray-100">{code}</span>
          </div>
        )
      }
      
      // Comments (both in prompts and outputs)
      if (trimmedLine.includes('#')) {
        const parts = line.split('#')
        const beforeComment = parts[0]
        const comment = parts.slice(1).join('#')
        
        return (
          <div key={index} className="font-mono text-sm">
            <span className="text-gray-100">{beforeComment}</span>
            <span className="text-gray-500">#{comment}</span>
          </div>
        )
      }
      
      // String outputs (in quotes)
      if (trimmedLine.match(/^["'].*["']$/)) {
        return (
          <div key={index} className="font-mono text-sm">
            <span className="text-yellow-300">{line}</span>
          </div>
        )
      }
      
      // Numbers
      if (trimmedLine.match(/^\d+(\.\d+)?$/)) {
        return (
          <div key={index} className="font-mono text-sm">
            <span className="text-cyan-300">{line}</span>
          </div>
        )
      }
      
      // Boolean values
      if (trimmedLine === 'True' || trimmedLine === 'False' || trimmedLine === 'None') {
        return (
          <div key={index} className="font-mono text-sm">
            <span className="text-purple-400">{line}</span>
          </div>
        )
      }
      
      // Dict/List representations
      if (trimmedLine.startsWith('{') || trimmedLine.startsWith('[') || trimmedLine.startsWith('(')) {
        return (
          <div key={index} className="font-mono text-sm">
            <span className="text-blue-300">{line}</span>
          </div>
        )
      }
      
      // Object representations like <ClassName>
      if (trimmedLine.match(/^<.*>$/)) {
        return (
          <div key={index} className="font-mono text-sm">
            <span className="text-purple-300">{line}</span>
          </div>
        )
      }
      
      // Default output
      return (
        <div key={index} className="font-mono text-sm text-gray-100">
          {line || '\u00A0'}
        </div>
      )
    })
  }

  return (
    <div className={`bg-gray-900 rounded-lg overflow-hidden ${className}`}>
      <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-gray-800">
        {/* Code Section */}
        <div className="relative">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-2 border-b border-gray-700">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-gray-400" />
              <span className="text-sm text-gray-300 font-mono">Code</span>
            </div>
            <button
              onClick={handleCopy}
              className="text-gray-400 hover:text-white transition-colors p-1.5 rounded hover:bg-gray-700"
              title="Copy code"
            >
              {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <div className="p-4 overflow-x-auto">
            <SyntaxHighlighter 
              language={language} 
              style={vscDarkPlus} 
              customStyle={{ 
                background: 'transparent', 
                padding: 0, 
                margin: 0, 
                fontSize: '0.875rem',
                lineHeight: '1.5'
              }}
              showLineNumbers={false}
            >
              {code}
            </SyntaxHighlighter>
          </div>
        </div>

        {/* Result Section */}
        {result && (
          <div className="relative">
            <div className="flex items-center justify-between bg-gray-800 px-4 py-2 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <Play className="w-4 h-4 text-green-400" />
                <span className="text-sm text-gray-300 font-mono">Python REPL</span>
              </div>
            </div>
            <div className="p-4 overflow-x-auto bg-gray-950">
              <div className="space-y-0.5">
                {renderPythonRepl(result)}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}