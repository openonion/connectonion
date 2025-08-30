'use client'

import { useState, useEffect } from 'react'
import { Menu, X, BookOpen, Copy, Check, Loader2 } from 'lucide-react'
import { DocsSidebar } from './DocsSidebar'
import { motion, AnimatePresence } from 'framer-motion'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useCopyMarkdown } from '../hooks/useCopyMarkdown'
import { hasMarkdownContent } from '../utils/markdownMapping'

export function MobileDocsNav() {
  const [isOpen, setIsOpen] = useState(false)
  const pathname = usePathname()
  const { copyMarkdown, status } = useCopyMarkdown(pathname)
  const hasMarkdown = hasMarkdownContent(pathname)
  
  // Auto-close menu when route changes
  useEffect(() => {
    setIsOpen(false)
  }, [pathname])

  return (
    <>
      {/* Mobile Header Bar */}
      <div className="lg:hidden sticky top-0 z-50 bg-gray-900/95 backdrop-blur-sm border-b border-gray-800">
        <div className="flex items-center justify-between px-4 py-3">
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="p-2 rounded-md bg-gray-800/60 text-white border border-gray-700/60 hover:bg-gray-700/60 transition-colors"
            aria-label="Toggle documentation menu"
          >
            {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          
          <Link href="/" className="flex items-center gap-2">
            <img src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" alt="ConnectOnion" className="w-6 h-6 rounded-md object-cover" />
            <span className="font-semibold text-white">ConnectOnion</span>
          </Link>
          
          {/* Copy button - only shows if current page has markdown */}
          {hasMarkdown ? (
            <button
              onClick={() => copyMarkdown()}
              className="p-2 rounded-md bg-gray-800/60 text-white border border-gray-700/60 hover:bg-gray-700/60 transition-colors"
              title="Copy page as markdown"
              aria-label="Copy page as markdown"
            >
              {status === 'loading' ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : status === 'success' ? (
                <Check className="w-5 h-5 text-green-400" />
              ) : (
                <Copy className="w-5 h-5" />
              )}
            </button>
          ) : (
            <div className="w-10" /> /* Balance spacing when no copy button */
          )}
        </div>
      </div>

      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="lg:hidden fixed inset-0 bg-black/60 z-40"
              onClick={() => setIsOpen(false)}
            />
            
            {/* Mobile Sidebar */}
            <motion.div
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'tween', duration: 0.3 }}
              className="lg:hidden fixed left-0 top-0 h-screen z-50"
            >
              <DocsSidebar />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
