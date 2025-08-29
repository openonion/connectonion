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
                <span className="text-sm text-gray-300 font-mono">Result</span>
              </div>
              {showRunButton && (
                <span className="text-xs text-gray-500 italic">After running</span>
              )}
            </div>
            <div className="p-4 overflow-x-auto">
              <pre className="text-sm text-gray-300 font-mono whitespace-pre-wrap">
                {result}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}