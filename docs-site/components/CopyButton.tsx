'use client'

import { useState } from 'react'
import { Copy, Check, AlertCircle } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface CopyButtonProps {
  text: string
  label?: string
  className?: string
}

export default function CopyButton({ text, label = 'Copy to clipboard', className = '' }: CopyButtonProps) {
  const [status, setStatus] = useState<'idle' | 'copying' | 'copied' | 'error'>('idle')

  const handleCopy = async () => {
    setStatus('copying')
    try {
      await navigator.clipboard.writeText(text)
      setStatus('copied')
      setTimeout(() => setStatus('idle'), 2000)
    } catch (err) {
      setStatus('error')
      setTimeout(() => setStatus('idle'), 2000)
    }
  }

  const getButtonClass = () => {
    const baseClass = `btn-copy touch-target ${className}`
    if (status === 'copied') return `${baseClass} btn-copy-success`
    if (status === 'error') return `${baseClass} btn-copy-error`
    return baseClass
  }

  return (
    <button
      onClick={handleCopy}
      disabled={status === 'copying'}
      className={getButtonClass()}
      aria-label={label}
      title={label}
    >
      <AnimatePresence mode="wait">
        {status === 'copying' && (
          <motion.div
            key="copying"
            initial={{ rotate: 0 }}
            animate={{ rotate: 360 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
            className="w-4 h-4 border-2 border-current border-t-transparent rounded-full"
          />
        )}
        {status === 'copied' && (
          <motion.div
            key="copied"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            exit={{ scale: 0 }}
            transition={{ type: "spring", duration: 0.3 }}
          >
            <Check className="w-4 h-4" />
          </motion.div>
        )}
        {status === 'error' && (
          <motion.div
            key="error"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            exit={{ scale: 0 }}
            transition={{ type: "spring", duration: 0.3 }}
          >
            <AlertCircle className="w-4 h-4 text-red-400" />
          </motion.div>
        )}
        {status === 'idle' && (
          <motion.div
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <Copy className="w-4 h-4" />
          </motion.div>
        )}
      </AnimatePresence>
      <span className="sr-only">
        {status === 'copied' && 'Copied!'}
        {status === 'error' && 'Failed to copy'}
        {(status === 'idle' || status === 'copying') && label}
      </span>
    </button>
  )
}