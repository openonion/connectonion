/*
  DESIGN ISSUES TO FIX:
  
  1. **Accessibility Issues** (Priority: HIGH)
     - Missing keyboard navigation support
     - No visual focus indicators on copy button
     - aria-label changes but screen readers won't announce it
     - Fix: Add focus-visible styles, announce copy success to screen readers
  
  2. **Visual Feedback** (Priority: MEDIUM)
     - Copy feedback only shown in button - easy to miss
     - No hover state on individual commands
     - Button hover state inconsistent with site design
     - Fix: Add toast notification, improve hover states, standardize button styles
  
  3. **Code Maintainability** (Priority: MEDIUM)
     - Command colorization logic is repetitive
     - Hard-coded color values instead of theme variables
     - No extensibility for new command types
     - Fix: Create command pattern registry, use CSS variables, modular structure
  
  4. **Mobile Experience** (Priority: LOW)
     - Horizontal scroll on long commands not smooth
     - Copy button too small for touch targets (32px)
     - Terminal padding too large on mobile
     - Fix: Add scroll indicators, increase touch target to 44px, responsive padding
  
  5. **Feature Gaps** (Priority: LOW)
     - No support for command output preview
     - Can't copy individual commands
     - No syntax for comments or explanations
     - Fix: Add output support, per-line copy buttons, comment syntax
*/

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

  // Function to colorize terminal commands
  const colorizeCommand = (cmd: string) => {
    // Check for common command patterns
    if (cmd.startsWith('pip install')) {
      return (
        <>
          <span className="text-green-400">pip</span>
          <span className="text-gray-100"> install</span>
          <span className="text-blue-400"> {cmd.slice(12)}</span>
        </>
      )
    }
    if (cmd.startsWith('mkdir')) {
      return (
        <>
          <span className="text-yellow-400">mkdir</span>
          <span className="text-gray-100"> {cmd.slice(6)}</span>
        </>
      )
    }
    if (cmd.startsWith('cd')) {
      return (
        <>
          <span className="text-yellow-400">cd</span>
          <span className="text-gray-100"> {cmd.slice(3)}</span>
        </>
      )
    }
    if (cmd.startsWith('co init')) {
      return (
        <>
          <span className="text-purple-400">co</span>
          <span className="text-gray-100"> init</span>
          {cmd.length > 7 && <span className="text-blue-400"> {cmd.slice(8)}</span>}
        </>
      )
    }
    if (cmd.startsWith('co')) {
      return (
        <>
          <span className="text-purple-400">co</span>
          <span className="text-gray-100"> {cmd.slice(3)}</span>
        </>
      )
    }
    if (cmd.startsWith('cp')) {
      return (
        <>
          <span className="text-yellow-400">cp</span>
          <span className="text-gray-100"> {cmd.slice(3)}</span>
        </>
      )
    }
    if (cmd.startsWith('python')) {
      return (
        <>
          <span className="text-blue-400">python</span>
          <span className="text-gray-100"> {cmd.slice(7)}</span>
        </>
      )
    }
    if (cmd.startsWith('npm')) {
      return (
        <>
          <span className="text-red-400">npm</span>
          <span className="text-gray-100"> {cmd.slice(4)}</span>
        </>
      )
    }
    
    // Default: return as is
    return <span className="text-gray-100">{cmd}</span>
  }

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between bg-gray-800 px-4 py-2 border-b border-gray-700">
        <span className="text-sm text-gray-400 font-mono">{title || 'Terminal'}</span>
        <button
          onClick={copyToClipboard}
          className="btn-ghost p-2 min-h-[32px] min-w-[32px] !px-2 !py-2"
          title="Copy commands"
          aria-label={copied ? 'Copied!' : 'Copy commands'}
        >
          {copied ? (
            <Check className="w-4 h-4 text-green-400" />
          ) : (
            <Copy className="w-4 h-4" />
          )}
        </button>
      </div>
      <div className="bg-black p-4 font-mono text-sm overflow-x-auto">
        {commands.map((cmd, index) => (
          <div key={index} className="group hover:bg-white/5 -mx-4 px-4 py-0.5 transition-colors">
            <span className="select-none text-green-400 mr-2">$</span>
            {colorizeCommand(cmd)}
          </div>
        ))}
      </div>
    </div>
  )
}