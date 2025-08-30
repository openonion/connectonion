'use client'

import { useState } from 'react'
import { Menu, X, Copy, Check } from 'lucide-react'
import Link from 'next/link'

interface MobileNavHeaderProps {
  onCopyMarkdown?: () => void
  hasCopyContent?: boolean
}

export default function MobileNavHeader({ onCopyMarkdown, hasCopyContent = false }: MobileNavHeaderProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    if (onCopyMarkdown) {
      onCopyMarkdown()
      setCopied(true)
      
      // Haptic feedback
      if ('vibrate' in navigator) {
        navigator.vibrate(50)
      }
      
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <>
      {/* Mobile Navigation Header - Only visible on mobile */}
      <header className="lg:hidden fixed top-0 left-0 right-0 z-50 bg-gray-950/95 backdrop-blur-xl border-b border-gray-800">
        <div className="flex items-center justify-between px-4 h-14">
          {/* Logo/Home */}
          <Link href="/" className="flex items-center gap-2">
            <span className="text-xl font-bold text-white">🧅</span>
            <span className="text-lg font-semibold text-white">ConnectOnion</span>
          </Link>

          {/* Right side buttons */}
          <div className="flex items-center gap-2">
            {/* Copy button - only show if page has content */}
            {hasCopyContent && (
              <button
                onClick={handleCopy}
                className={`p-2 rounded-lg transition-all duration-200 ${
                  copied 
                    ? 'bg-green-600/20 text-green-400' 
                    : 'text-gray-300 hover:text-white hover:bg-gray-800'
                }`}
                aria-label={copied ? "Copied!" : "Copy page content"}
              >
                {copied ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
              </button>
            )}

            {/* Menu button */}
            <button
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              className="p-2 rounded-lg text-gray-300 hover:text-white hover:bg-gray-800 transition-colors"
              aria-label="Toggle menu"
            >
              {isMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Dropdown menu */}
        {isMenuOpen && (
          <nav className="border-t border-gray-800 bg-gray-950/95 backdrop-blur-xl">
            <div className="px-4 py-4 space-y-3">
              <Link 
                href="/quickstart" 
                onClick={() => setIsMenuOpen(false)}
                className="block py-2 text-gray-300 hover:text-white transition-colors"
              >
                Quick Start
              </Link>
              <Link 
                href="/examples" 
                onClick={() => setIsMenuOpen(false)}
                className="block py-2 text-gray-300 hover:text-white transition-colors"
              >
                Examples
              </Link>
              <Link 
                href="/cli" 
                onClick={() => setIsMenuOpen(false)}
                className="block py-2 text-gray-300 hover:text-white transition-colors"
              >
                CLI
              </Link>
              <a 
                href="https://github.com/wu-changxing/connectonion" 
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setIsMenuOpen(false)}
                className="block py-2 text-gray-300 hover:text-white transition-colors"
              >
                GitHub
              </a>
              <a 
                href="https://discord.gg/4xfD9k8AUF" 
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setIsMenuOpen(false)}
                className="block py-2 text-gray-300 hover:text-white transition-colors"
              >
                Discord
              </a>
            </div>
          </nav>
        )}
      </header>

      {/* Spacer for fixed header on mobile */}
      <div className="lg:hidden h-14" />
    </>
  )
}