'use client'

import { useState } from 'react'
import { Copy, Check } from 'lucide-react'

interface CommandBlockProps {
  title?: string
  commands: string[]
  id?: string
}

export function CommandBlock({ title, commands, id }: CommandBlockProps) {
  const [copied, setCopied] = useState(false)
  
  const copyToClipboard = () => {
    navigator.clipboard.writeText(commands.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between bg-gray-800 px-4 py-2 border-b border-gray-700">
        <span className="text-sm text-gray-400 font-mono">{title || 'Terminal'}</span>
        <button
          onClick={copyToClipboard}
          className="text-gray-400 hover:text-white transition-colors p-1.5 rounded hover:bg-gray-700"
          title="Copy commands"
        >
          {copied ? (
            <Check className="w-4 h-4 text-green-400" />
          ) : (
            <Copy className="w-4 h-4" />
          )}
        </button>
      </div>
      <div className="bg-black/90 p-4 font-mono text-sm overflow-x-auto">
        {commands.map((cmd, index) => (
          <div key={index} className="group hover:bg-white/5 -mx-4 px-4 py-0.5">
            <span className="select-none text-gray-500 mr-2">$</span>
            <span className="text-gray-100">{cmd}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
