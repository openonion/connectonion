'use client'

import { useState, useEffect } from 'react'
import { Copy, Check, Download, Loader2 } from 'lucide-react'

interface CopyMarkdownButtonProps {
  // For new implementation with static files
  markdownPath?: string
  // For backward compatibility with existing pages
  content?: string
  filename?: string
  className?: string
  // Control mobile behavior
  floatingMobile?: boolean
}

export function CopyMarkdownButton({ 
  markdownPath,
  content: directContent,
  filename = 'content.md', 
  className = '',
  floatingMobile = true
}: CopyMarkdownButtonProps) {
  const [copied, setCopied] = useState(false)
  const [content, setContent] = useState(directContent || '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [showFloating, setShowFloating] = useState(false)

  // If markdownPath is provided, fetch the content
  useEffect(() => {
    if (markdownPath && !directContent) {
      setLoading(true)
      setError(false)
      
      fetch(markdownPath)
        .then(res => {
          if (!res.ok) throw new Error('Failed to load markdown')
          return res.text()
        })
        .then(text => {
          setContent(text)
          setLoading(false)
        })
        .catch(err => {
          console.error('Failed to load markdown:', err)
          setError(true)
          setLoading(false)
        })
    }
  }, [markdownPath, directContent])

  // Handle floating button visibility on mobile
  useEffect(() => {
    if (floatingMobile) {
      const handleScroll = () => {
        setShowFloating(window.scrollY > 100)
      }
      window.addEventListener('scroll', handleScroll)
      return () => window.removeEventListener('scroll', handleScroll)
    }
  }, [floatingMobile])

  const handleCopy = async () => {
    if (!content || loading) return
    
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      
      // Haptic feedback for mobile (if supported)
      if ('vibrate' in navigator) {
        navigator.vibrate(50)
      }
      
      // Reset after 2 seconds
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleDownload = () => {
    // If we have a markdown path, use direct download
    if (markdownPath) {
      const link = document.createElement('a')
      link.href = markdownPath
      link.download = markdownPath.split('/').pop() || filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } 
    // Otherwise use the blob method for backward compatibility
    else if (content) {
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
  }

  // Don't render if there's an error loading
  if (error) {
    return (
      <div className={`flex gap-2 ${className}`}>
        <span className="text-red-400 text-sm">Failed to load content</span>
      </div>
    )
  }

  return (
    <>
      {/* Desktop buttons - hidden on mobile if using floating */}
      <div className={`${floatingMobile ? 'hidden lg:flex' : 'flex'} gap-2 ${className}`}>
        {/* Copy Button */}
        <button
          onClick={handleCopy}
          disabled={loading || !content}
          className={`
            relative flex items-center gap-2 px-3 py-2 
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
          title={copied ? "Copied to clipboard!" : "Copy to clipboard"}
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="hidden sm:inline">Loading...</span>
            </>
          ) : copied ? (
            <>
              <Check className="w-4 h-4 animate-in fade-in zoom-in duration-200" />
              <span className="hidden sm:inline">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-4 h-4" />
              <span className="hidden sm:inline">Copy</span>
            </>
          )}
        </button>
        
        {/* Download Button - only on larger screens */}
        <div className="hidden sm:block">
          {markdownPath ? (
            <a
              href={markdownPath}
              download={markdownPath.split('/').pop() || filename}
              className="
                flex items-center gap-2 px-3 py-2 
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
              <span className="hidden sm:inline">Download</span>
            </a>
          ) : (
            <button
              onClick={handleDownload}
              disabled={loading || !content}
              className={`
                flex items-center gap-2 px-3 py-2 
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
              <span className="hidden sm:inline">Download</span>
            </button>
          )}
        </div>
      </div>

      {/* Mobile floating button */}
      {floatingMobile && (
        <div className={`
          lg:hidden fixed bottom-6 right-6 z-40
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
      )}
    </>
  )
}