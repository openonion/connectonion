'use client'

import Link from 'next/link'
import { useState, useEffect } from 'react'
import { Menu, X, Github, ExternalLink, Zap, FileText, Terminal, Copy, Check, Download } from 'lucide-react'
import { FaDiscord } from 'react-icons/fa'
import { motion, AnimatePresence } from 'framer-motion'

interface NavigationProps {
  markdownContent?: string
  markdownPath?: string
  filename?: string
}

export default function Navigation({ markdownContent, markdownPath, filename = 'content.md' }: NavigationProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const [copied, setCopied] = useState(false)
  const [content, setContent] = useState(markdownContent || '')

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  // Fetch markdown content if path is provided
  useEffect(() => {
    if (markdownPath && !markdownContent) {
      fetch(markdownPath)
        .then(res => res.text())
        .then(text => setContent(text))
        .catch(err => console.error('Failed to load markdown:', err))
    } else if (markdownContent) {
      setContent(markdownContent)
    }
  }, [markdownPath, markdownContent])

  const handleCopy = async () => {
    if (!content) return
    
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      
      // Haptic feedback for mobile
      if ('vibrate' in navigator) {
        navigator.vibrate(50)
      }
      
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleDownload = () => {
    if (!content) return
    
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
    <header className={`fixed top-0 w-full z-50 transition-all duration-300 ${
      scrolled 
        ? 'bg-gray-950/80 backdrop-blur-xl border-b border-gray-800/50 shadow-xl' 
        : 'bg-transparent'
    }`}>
      <nav className="container mx-auto px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 lg:h-20">
          {/* Premium Logo */}
          <Link href="/" className="flex items-center gap-3 group">
            <div className="relative">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 opacity-0 group-hover:opacity-20 blur-lg transition-opacity duration-300" />
            </div>
            <div className="text-xl font-bold text-white group-hover:text-transparent group-hover:bg-gradient-to-r group-hover:from-purple-400 group-hover:to-pink-400 group-hover:bg-clip-text transition-all duration-300">
              ConnectOnion
            </div>
          </Link>
          
          {/* Desktop Navigation */}
          <div className="hidden lg:flex items-center gap-8">
            <NavLink href="/quickstart" icon={<FileText className="w-4 h-4" />}>
              Docs
            </NavLink>
            <NavLink href="/cli" icon={<Terminal className="w-4 h-4" />}>
              CLI
            </NavLink>
            <NavLink href="/xray" icon={<Zap className="w-4 h-4" />}>
              @xray
            </NavLink>
            <NavLink href="https://github.com/wu-changxing/connectonion" icon={<Github className="w-4 h-4" />} external>
              GitHub
            </NavLink>
            <NavLink href="https://pypi.org/project/connectonion/" icon={<ExternalLink className="w-4 h-4" />} external>
              PyPI
            </NavLink>
            <NavLink href="https://discord.gg/4xfD9k8AUF" icon={<FaDiscord className="w-4 h-4" />} external>
              Discord
            </NavLink>
            
            {/* CTA Button */}
            <motion.div
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="ml-4"
            >
              <button className="btn-gradient text-white font-medium px-6 py-2.5 rounded-full shadow-lg">
                Get Started
              </button>
            </motion.div>
          </div>

          {/* Mobile Menu and Copy Buttons */}
          <div className="lg:hidden flex items-center gap-2">
            {/* Mobile Copy Button - Always visible in header */}
            {content && (
              <button
                onClick={handleCopy}
                className={`p-2 rounded-lg transition-all duration-200 ${
                  copied 
                    ? 'bg-green-600/20 text-green-400' 
                    : 'text-gray-300 hover:text-white hover:bg-gray-800'
                }`}
                aria-label={copied ? "Copied!" : "Copy page as markdown"}
              >
                {copied ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
              </button>
            )}
            
            {/* Mobile Menu Button */}
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="p-2 rounded-lg text-gray-300 hover:text-white hover:bg-gray-800 transition-colors"
              aria-label="Toggle navigation menu"
            >
              {isOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>

        {/* Mobile Menu */}
        <AnimatePresence>
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="lg:hidden border-t border-gray-800/50 bg-gray-950/95 backdrop-blur-xl"
            >
              <div className="py-6 space-y-4">
                <MobileNavLink href="/quickstart" onClick={() => setIsOpen(false)}>
                  Docs
                </MobileNavLink>
                <MobileNavLink href="/cli" onClick={() => setIsOpen(false)}>
                  CLI
                </MobileNavLink>
                <MobileNavLink href="/xray" onClick={() => setIsOpen(false)}>
                  @xray
                </MobileNavLink>
                <MobileNavLink href="https://github.com/wu-changxing/connectonion" onClick={() => setIsOpen(false)} external>
                  GitHub
                </MobileNavLink>
                <MobileNavLink href="https://pypi.org/project/connectonion/" onClick={() => setIsOpen(false)} external>
                  PyPI
                </MobileNavLink>
                <MobileNavLink href="https://discord.gg/4xfD9k8AUF" onClick={() => setIsOpen(false)} external>
                  Discord
                </MobileNavLink>
                <div className="pt-4 border-t border-gray-800">
                  <button className="w-full btn-gradient text-white font-medium py-3 rounded-full">
                    Get Started
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>
    </header>
  )
}

// Premium NavLink Component
function NavLink({ href, children, icon, external = false }: {
  href: string
  children: React.ReactNode
  icon?: React.ReactNode
  external?: boolean
}) {
  const Component = external ? 'a' : Link
  const props = external ? { href, target: '_blank', rel: 'noopener noreferrer' } : { href }
  
  return (
    <Component
      {...props}
      className="group flex items-center gap-2 px-3 py-2 rounded-lg text-gray-300 hover:text-white transition-all duration-300 hover:bg-gray-800/50 relative overflow-hidden"
    >
      <span className="relative z-10 flex items-center gap-2">
        {icon}
        {children}
      </span>
      <div className="absolute inset-0 bg-gradient-to-r from-purple-500/10 to-pink-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
    </Component>
  )
}

function MobileNavLink({ href, children, external = false, onClick }: {
  href: string
  children: React.ReactNode
  external?: boolean
  onClick: () => void
}) {
  const Component = external ? 'a' : Link
  const props = external ? { href, target: '_blank', rel: 'noopener noreferrer' } : { href }
  
  return (
    <Component
      {...props}
      onClick={onClick}
      className="block px-4 py-3 text-gray-300 hover:text-white hover:bg-gray-800/50 rounded-lg transition-colors"
    >
      {children}
    </Component>
  )
}