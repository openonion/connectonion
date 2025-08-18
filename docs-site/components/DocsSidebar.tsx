'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Search, FileText, Zap, Code, Settings, BookOpen, ChevronRight, ChevronDown, User, Database, Brain, Play, Lightbulb, FolderOpen, GitBranch, Shield, TrendingUp, Gauge, Copy, Check } from 'lucide-react'
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
    ]
  },
  {
    title: 'Core Concepts',
    items: [
      { title: 'Tools', href: '/tools', icon: Code },
      { title: 'System Prompts', href: '/prompts', icon: Code, difficulty: 'Start Here' },
      { title: 'max_iterations', href: '/max-iterations', icon: Gauge },
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
    title: 'Agent Building',
    items: [
      { title: 'Examples Overview', href: '/examples' },
      { title: '1. Hello World Agent', href: '/examples/hello-world', icon: User, difficulty: 'Beginner' },
      { title: '2. Basic Calculator', href: '/examples/calculator', icon: Code, difficulty: 'Beginner' },
      { title: '3. Weather Bot', href: '/examples/weather-bot', icon: Database, difficulty: 'Beginner' },
      { title: '4. Task Manager', href: '/examples/task-manager', icon: FileText, difficulty: 'Intermediate' },
      { title: '5. Math Tutor Agent', href: '/examples/math-tutor-agent', icon: Code, difficulty: 'Intermediate' },
      { title: '6. File Analyzer', href: '/examples/file-analyzer', icon: FileText, difficulty: 'Advanced' },
      { title: '7. API Client', href: '/examples/api-client', icon: Database, difficulty: 'Advanced' },
      { title: '8. E-commerce Manager', href: '/examples/ecommerce-manager', icon: TrendingUp, difficulty: 'Expert' },
    ]
  },
]

export function DocsSidebar() {
  const [searchQuery, setSearchQuery] = useState('')
  const [openSections, setOpenSections] = useState<string[]>(['Getting Started', 'Core Concepts', 'System Prompts', 'Agent Building'])
  const [isClientMounted, setIsClientMounted] = useState(false)
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copying' | 'success'>('idle')
  const pathname = usePathname()

  // Initialize from localStorage after client mount to prevent hydration mismatch
  useEffect(() => {
    setIsClientMounted(true)
    const saved = localStorage.getItem('docs-open-sections')
    if (saved) {
      try {
        setOpenSections(JSON.parse(saved))
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
      setOpenSections(prev => [...prev, currentSection.title])
    }
  }, [pathname, openSections])

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
    <div className="w-80 bg-gray-900 border-r border-gray-800 flex flex-col h-screen sticky top-0 z-40">
      {/* Header */}
      <div className="p-6 border-b border-gray-800">
        <Link href="/" className="flex items-center gap-3 group">
          <img src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" alt="ConnectOnion" className="w-8 h-8 rounded-lg object-cover" />
          <div>
            <div className="text-lg font-bold text-white">ConnectOnion</div>
            <div className="text-xs text-gray-400">Documentation v0.0.1b5</div>
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
              <ul className="mt-2 space-y-1">
                {section.items.map((item) => {
                  const isActive = pathname === item.href
                  const IconComponent = item.icon
                  const isPromptExample = item.href.includes('/prompts/examples/') && item.href !== '/prompts/examples'
                  
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        className={`block px-4 py-2 text-sm transition-colors relative ${
                          isActive
                            ? 'text-purple-400 bg-purple-900/20 border-r-2 border-purple-400'
                            : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
                        } ${isPromptExample ? 'pl-6' : ''}`}
                      >
                        <div className="flex items-center gap-3">
                          {IconComponent ? (
                            <IconComponent className="w-3.5 h-3.5 flex-shrink-0" />
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
          <div className="flex items-center gap-3 text-xs text-gray-400">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            <span>v0.0.1b5</span>
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