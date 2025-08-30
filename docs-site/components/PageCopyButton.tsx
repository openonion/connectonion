'use client'

import { useState, useEffect } from 'react'
import { Copy, Check, Download, Loader2 } from 'lucide-react'

interface PageCopyButtonProps {
  markdownPath?: string
  content?: string
  filename?: string
  variant?: 'default' | 'mobile' | 'floating'
}

export function PageCopyButton({ 
  markdownPath,
  content: directContent,
  filename = 'content.md',
  variant = 'default'
}: PageCopyButtonProps) {
  const [copied, setCopied] = useState(false)
  const [content, setContent] = useState(directContent || '')
  const [loading, setLoading] = useState(false)
  const [showFloating, setShowFloating] = useState(false)

  // Fetch content if markdownPath is provided
  useEffect(() => {
    if (markdownPath && !directContent) {
      setLoading(true)
      fetch(markdownPath)
        .then(res => res.text())
        .then(text => {
          setContent(text)
          setLoading(false)
        })
        .catch(err => {
          console.error('Failed to load markdown:', err)
          setLoading(false)
        })
    }
  }, [markdownPath, directContent])

  // Show floating button on scroll for mobile
  useEffect(() => {
    if (variant === 'floating') {
      const handleScroll = () => {
        setShowFloating(window.scrollY > 100)
      }
      window.addEventListener('scroll', handleScroll)
      return () => window.removeEventListener('scroll', handleScroll)
    }
  }, [variant])

  const handleCopy = async () => {
    if (!content || loading) return
    
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      
      if ('vibrate' in navigator) {
        navigator.vibrate(50)
      }
      
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  // Mobile navigation bar variant (icon only)
  if (variant === 'mobile') {
    return (
      <button
        onClick={handleCopy}
        disabled={loading || !content}
        className={`
          p-2 rounded-lg transition-all duration-200
          ${copied 
            ? 'bg-green-600/20 text-green-400' 
            : 'text-gray-300 hover:text-white hover:bg-gray-800'
          }
          ${loading || !content ? 'opacity-50 cursor-not-allowed' : ''}
        `}
        title={copied ? "Copied!" : "Copy page as markdown"}
      >
        {loading ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : copied ? (
          <Check className="w-5 h-5" />
        ) : (
          <Copy className="w-5 h-5" />
        )}
      </button>
    )
  }

  // Floating action button for mobile
  if (variant === 'floating') {
    return (
      <div className={`
        fixed bottom-6 right-6 z-40 lg:hidden
        transition-all duration-300 transform
        ${showFloating ? 'translate-y-0 opacity-100' : 'translate-y-20 opacity-0 pointer-events-none'}
      `}>
        <button
          onClick={handleCopy}
          disabled={loading || !content}
          className={`
            p-4 rounded-full shadow-2xl
            transition-all duration-200 transform active:scale-95
            ${copied 
              ? 'bg-green-600 hover:bg-green-700' 
              : 'bg-purple-600 hover:bg-purple-700'
            }
            text-white
            ${loading || !content ? 'opacity-50 cursor-not-allowed' : ''}
          `}
          title={copied ? "Copied!" : "Copy page as markdown"}
        >
          {loading ? (
            <Loader2 className="w-6 h-6 animate-spin" />
          ) : copied ? (
            <Check className="w-6 h-6" />
          ) : (
            <Copy className="w-6 h-6" />
          )}
        </button>
      </div>
    )
  }

  // Default desktop variant
  return (
    <div className="hidden lg:flex gap-2">
      <button
        onClick={handleCopy}
        disabled={loading || !content}
        className={`
          flex items-center gap-2 px-4 py-2 
          ${copied 
            ? 'bg-green-600 hover:bg-green-700' 
            : 'bg-purple-600 hover:bg-purple-700'
          }
          text-white rounded-lg 
          transition-all duration-200 ease-out
          text-sm font-medium
          ${loading || !content ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          transform active:scale-95
          shadow-lg hover:shadow-xl
        `}
        title={copied ? "Copied!" : "Copy to clipboard"}
      >
        {loading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading...
          </>
        ) : copied ? (
          <>
            <Check className="w-4 h-4" />
            Copied!
          </>
        ) : (
          <>
            <Copy className="w-4 h-4" />
            Copy
          </>
        )}
      </button>
      
      {markdownPath ? (
        <a
          href={markdownPath}
          download={markdownPath.split('/').pop() || filename}
          className="
            flex items-center gap-2 px-4 py-2 
            bg-gray-700 hover:bg-gray-600 
            text-white rounded-lg 
            transition-all duration-200 ease-out
            text-sm font-medium cursor-pointer
            transform active:scale-95
            shadow-lg hover:shadow-xl
          "
          title="Download markdown file"
        >
          <Download className="w-4 h-4" />
          Download
        </a>
      ) : content && (
        <button
          onClick={() => {
            const blob = new Blob([content], { type: 'text/markdown' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = filename
            document.body.appendChild(a)
            a.click()
            document.body.removeChild(a)
            URL.revokeObjectURL(url)
          }}
          disabled={loading || !content}
          className={`
            flex items-center gap-2 px-4 py-2 
            bg-gray-700 hover:bg-gray-600 
            text-white rounded-lg 
            transition-all duration-200 ease-out
            text-sm font-medium
            ${loading || !content ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
            transform active:scale-95
            shadow-lg hover:shadow-xl
          `}
          title="Download markdown file"
        >
          <Download className="w-4 h-4" />
          Download
        </button>
      )}
    </div>
  )
}