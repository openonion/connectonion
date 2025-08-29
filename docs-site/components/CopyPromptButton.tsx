'use client'

import { useState, useEffect } from 'react'
import { Copy, Check, FileText } from 'lucide-react'
import { getAllDocsContent } from '../utils/copyAllDocs'

export function CopyPromptButton() {
  const [copied, setCopied] = useState(false)
  const [content, setContent] = useState<string>('')

  useEffect(() => {
    // Use the utility to fetch documentation
    getAllDocsContent().then(setContent)
  }, [])

  const copyToClipboard = async () => {
    if (!content) return
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      console.error('Failed to copy:', error)
    }
  }

  const downloadMarkdown = () => {
    if (!content) return
    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'connectonion-llm-prompt.md'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={copyToClipboard}
        className="flex items-center gap-2 px-3 sm:px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors text-sm font-medium"
        title="Copy ConnectOnion prompt for AI assistants"
      >
        {copied ? (
          <>
            <Check className="w-4 h-4 text-green-400" />
            <span className="hidden sm:inline">Copied!</span>
            <span className="sm:hidden">✓</span>
          </>
        ) : (
          <>
            <Copy className="w-4 h-4" />
            <span className="hidden sm:inline">Copy AI Prompt</span>
            <span className="sm:hidden">Copy</span>
          </>
        )}
      </button>
      
      <button
        onClick={downloadMarkdown}
        className="flex items-center gap-2 px-3 sm:px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors text-sm font-medium"
        title="Download ConnectOnion prompt as Markdown file"
      >
        <FileText className="w-4 h-4" />
        <span className="hidden sm:inline">Download MD</span>
        <span className="sm:hidden">↓</span>
      </button>
    </div>
  )
}