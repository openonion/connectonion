'use client'

import { useState } from 'react'
import { Copy, Check, FileText } from 'lucide-react'

interface CopyMarkdownButtonProps {
  content: string
  filename?: string
  className?: string
}

export function CopyMarkdownButton({ content, filename = 'content.md', className = '' }: CopyMarkdownButtonProps) {
  const [copied, setCopied] = useState(false)

  const copyToClipboard = () => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const downloadMarkdown = () => {
    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className={`flex gap-2 ${className}`}>
      <button
        onClick={copyToClipboard}
        className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors text-sm font-medium"
        title="Copy page content as Markdown"
      >
        {copied ? (
          <>
            <Check className="w-4 h-4 text-green-400" />
            Copied!
          </>
        ) : (
          <>
            <Copy className="w-4 h-4" />
            Copy as Markdown
          </>
        )}
      </button>
      
      <button
        onClick={downloadMarkdown}
        className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors text-sm font-medium"
        title="Download page as Markdown file"
      >
        <FileText className="w-4 h-4" />
        Download MD
      </button>
    </div>
  )
}