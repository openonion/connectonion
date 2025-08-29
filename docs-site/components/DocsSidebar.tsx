'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Search, FileText, Zap, Code, Settings, BookOpen, ChevronRight, ChevronDown, User, Users, Database, Brain, Play, Lightbulb, FolderOpen, GitBranch, Shield, TrendingUp, Gauge, Copy, Check, Terminal, Rocket, Cloud, MoreHorizontal } from 'lucide-react'
import { DifficultyBadge } from './DifficultyBadge'
import { copyAllDocsToClipboard } from '../utils/copyAllDocs'

type NavItem = {
  title: string
  href: string
  icon?: any
  difficulty?: string
}
type NavigationSection = {
  title: string
  items: NavItem[]
}

const navigation: NavigationSection[] = [
  {
    title: 'Getting Started',
    items: [
      { title: 'Introduction', href: '/' },
      { title: 'Quick Start', href: '/quickstart' },
      { title: 'CLI Reference', href: '/cli', icon: Terminal },
    ]
  },
  {
    title: 'Core Concepts',
    items: [
      { title: 'max_iterations', href: '/max-iterations', icon: Gauge, difficulty: 'Start Here' },
      { title: 'LLM Function', href: '/llm', icon: Zap },
      { title: 'Tools', href: '/tools', icon: Code },
      { title: 'System Prompts', href: '/prompts', icon: Code },
      { title: 'Trust Parameter', href: '/trust', icon: Shield },
    ]
  },
  {
    title: 'Prompt Formats',
    items: [
      { title: 'Format Support', href: '/prompts/formats', icon: FileText, difficulty: 'Interactive Demo' },
    ]
  },
  {
    title: 'Debugging',
    items: [
      { title: '@xray Decorator', href: '/xray' },
      { title: 'trace() Visual Flow', href: '/xray/trace' },
    ]
  },
  {
    title: 'Security',
    items: [
      { title: 'Threat Model', href: '/threat-model', icon: Shield },
    ]
  },
  {
    title: 'Examples',
    items: [
      { title: 'All Examples', href: '/examples', icon: FolderOpen, difficulty: 'Browse' },
      { title: 'Hello World', href: '/examples/hello-world', icon: Play, difficulty: 'Beginner' },
      { title: 'Calculator', href: '/examples/calculator', icon: Code, difficulty: 'Beginner' },
      { title: 'Weather Bot', href: '/examples/weather-bot', icon: Cloud, difficulty: 'Intermediate' },
      { title: 'More Examples', href: '/examples#advanced', icon: MoreHorizontal },
    ]
  },
  {
    title: 'Blog',
    items: [
      { title: 'All Posts', href: '/blog', icon: BookOpen },
      { title: 'Network Protocol Design', href: '/blog/network-protocol-design', icon: GitBranch, difficulty: 'Architecture' },
      { title: 'Why We Chose "Trust"', href: '/blog/trust-keyword', icon: Users, difficulty: 'Design Decision' },
    ]
  },
  {
    title: 'Roadmap',
    items: [
      { title: 'Coming Soon Features', href: '/roadmap', icon: Rocket, difficulty: 'Preview' },
    ]
  },
]

export function DocsSidebar() {
  const [searchQuery, setSearchQuery] = useState('')
  const [openSections, setOpenSections] = useState<string[]>(['Getting Started'])
  const [isClientMounted, setIsClientMounted] = useState(false)
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copying' | 'success'>('idle')
  const pathname = usePathname()

  // Auto-expand section containing current page
  useEffect(() => {
    const currentSection = navigation.find(section => 
      section.items.some(item => item.href === pathname)
    )
    if (currentSection && !openSections.includes(currentSection.title)) {
      setOpenSections(prev => [...prev, currentSection.title])
    }
  }, [pathname])

  // Initialize from localStorage after client mount to prevent hydration mismatch
  useEffect(() => {
    setIsClientMounted(true)
    const saved = localStorage.getItem('docs-open-sections')
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        if (parsed && parsed.length > 0) {
          setOpenSections(parsed)
        }
      } catch {
        // Keep default if parsing fails
      }
    }
  }, [])

  // Save to localStorage whenever sections change (only after client mount)
  useEffect(() => {
    if (isClientMounted) {
      localStorage.setItem('docs-open-sections', JSON.stringify(openSections))
    }
  }, [openSections, isClientMounted])

  // Auto-expand current section when navigating
  useEffect(() => {
    const currentSection = navigation.find(section => 
      section.items.some(item => item.href === pathname)
    )
    if (currentSection && !openSections.includes(currentSection.title)) {
      setOpenSections(prev => {
        // Only keep Getting Started and the current section open
        const newSections = ['Getting Started']
        if (currentSection.title !== 'Getting Started') {
          newSections.push(currentSection.title)
        }
        return newSections
      })
    }
  }, [pathname])

  const toggleSection = (title: string) => {
    setOpenSections(prev => 
      prev.includes(title) 
        ? prev.filter(t => t !== title)
        : [...prev, title]
    )
  }

  const filteredNavigation = navigation.map(section => ({
    ...section,
    items: section.items.filter(item => 
      searchQuery === '' || 
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      section.title.toLowerCase().includes(searchQuery.toLowerCase())
    )
  })).filter(section => section.items.length > 0)

  const handleCopyAllDocs = async () => {
    setCopyStatus('copying')
    try {
      const success = await copyAllDocsToClipboard()
      if (success) {
        setCopyStatus('success')
        setTimeout(() => setCopyStatus('idle'), 3000)
      } else {
        setCopyStatus('idle')
      }
    } catch (error) {
      console.error('Failed to copy docs:', error)
      setCopyStatus('idle')
    }
  }

  return (
    <div className="w-[85vw] sm:w-64 lg:w-72 xl:w-80 bg-gray-900 border-r border-gray-800 flex flex-col h-screen sticky top-0 z-40">
      {/* Header */}
      <div className="p-6 border-b border-gray-800">
        <Link href="/" className="flex items-center gap-3 group">
          <img src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" alt="ConnectOnion" className="w-8 h-8 rounded-lg object-cover" />
          <div>
            <div className="text-lg font-bold text-white">ConnectOnion</div>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span>Documentation v0.0.1b6</span>
              <span className="px-1.5 py-0.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-full text-[10px] font-semibold">BETA</span>
            </div>
          </div>
        </Link>
      </div>

      {/* Search */}
      <div className="p-4 border-b border-gray-800">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search docs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:border-purple-500 focus:ring-2 focus:ring-purple-500/30 focus:outline-none transition-all text-sm"
          />
        </div>
        {searchQuery && (
          <div className="mt-2 text-xs text-gray-400">
            {filteredNavigation.reduce((acc, section) => acc + section.items.length, 0)} results
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4">
        {filteredNavigation.map((section) => (
          <div key={section.title} className="mb-6">
            <button
              onClick={() => toggleSection(section.title)}
              className="w-full flex items-center justify-between px-4 py-2 text-left text-sm font-semibold text-gray-300 hover:text-white transition-colors"
            >
              <span>{section.title}</span>
              {openSections.includes(section.title) ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </button>
            
            {openSections.includes(section.title) && (
              <ul className="mt-2 space-y-1" role="list">
                {section.items.map((item) => {
                  const isActive = pathname === item.href
                  const IconComponent = item.icon
                  const isPromptExample = item.href.includes('/prompts/examples/') && item.href !== '/prompts/examples'
                  
                  return (
                    <li key={item.href} role="listitem">
                      <Link
                        href={item.href}
                        className={`block px-4 py-2.5 min-h-[40px] text-sm rounded-md mx-2 transition-all relative ${
                          isActive
                            ? 'nav-current'
                            : 'text-gray-300 hover:text-white hover:bg-gray-800/50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-inset'
                        } ${isPromptExample ? 'pl-6' : ''}`}
                        aria-current={isActive ? 'page' : undefined}
                      >
                        <div className="flex items-center gap-3">
                          {IconComponent ? (
                            <IconComponent className="w-4 h-4 flex-shrink-0" />
                          ) : (
                            <div className="w-1.5 h-1.5 rounded-full bg-current opacity-50 flex-shrink-0" />
                          )}
                          <span className="truncate flex-1">{item.title}</span>
                          {item.difficulty && (
                            <DifficultyBadge 
                              level={item.difficulty as 'Beginner' | 'Intermediate' | 'Advanced' | 'Expert'}
                              size="sm"
                              showIcon={false}
                              className="flex-shrink-0"
                            />
                          )}
                        </div>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-800 space-y-3">
        {/* Copy All Docs Button */}
        <button
          onClick={handleCopyAllDocs}
          disabled={copyStatus === 'copying'}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 disabled:from-gray-600 disabled:to-gray-700 rounded-lg text-white text-sm font-medium transition-all duration-200 transform hover:scale-[1.02] disabled:scale-100"
        >
          {copyStatus === 'copying' ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Copying...
            </>
          ) : copyStatus === 'success' ? (
            <>
              <Check className="w-4 h-4" />
              Copied to Clipboard!
            </>
          ) : (
            <>
              <Copy className="w-4 h-4" />
              Copy All Docs
            </>
          )}
        </button>
        
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            <span>v0.0.1b6</span>
            <span className="px-1.5 py-0.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-full text-[10px] font-semibold">BETA</span>
          </div>
        </div>
        
        {/* Quick Links */}
        <div className="flex gap-2">
          <a
            href="https://github.com/wu-changxing/connectonion"
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 text-center text-xs py-1.5 px-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-300 hover:text-white transition-colors"
          >
            GitHub
          </a>
          <a
            href="https://pypi.org/project/connectonion/"
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 text-center text-xs py-1.5 px-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-300 hover:text-white transition-colors"
          >
            PyPI
          </a>
        </div>
      </div>
    </div>
  )
}
