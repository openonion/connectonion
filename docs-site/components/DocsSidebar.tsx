'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { 
  Search, FileText, Zap, Code, Settings, BookOpen, 
  ChevronRight, ChevronDown, User, Users, Database, Brain, 
  Play, Lightbulb, FolderOpen, GitBranch, Shield, TrendingUp, 
  Gauge, Copy, Check, Terminal, Rocket, Cloud, MoreHorizontal,
  X, ArrowUp, ArrowDown, Home, BookOpenText, Bug, MessageSquare,
  Layers, Sparkles, Calculator, Bot, Package, MessageCircle
} from 'lucide-react'
import { DifficultyBadge } from './DifficultyBadge'
import { copyAllDocsToClipboard } from '../utils/copyAllDocs'
import { SearchHighlight } from './SearchHighlight'

type NavItem = {
  title: string
  href: string
  icon?: any
  difficulty?: string
  keywords?: string[]
}
type NavigationSection = {
  title: string
  items: NavItem[]
}

const navigation: NavigationSection[] = [
  {
    title: 'Getting Started',
    items: [
      { title: 'Introduction', href: '/', icon: Home, keywords: ['intro', 'overview', 'start', 'begin'] },
      { title: 'Quick Start', href: '/quickstart', icon: Rocket, keywords: ['setup', 'install', 'begin', 'tutorial'] },
      { title: 'CLI Reference', href: '/cli', icon: Terminal, keywords: ['command', 'terminal', 'co', 'commands'] },
    ]
  },
  {
    title: 'Core Concepts',
    items: [
      { title: 'max_iterations', href: '/max-iterations', icon: Gauge, difficulty: 'Start Here', keywords: ['loop', 'limit', 'iteration', 'control'] },
      { title: 'LLM Function', href: '/llm', icon: Zap, keywords: ['ai', 'model', 'openai', 'language'] },
      { title: 'Tools', href: '/tools', icon: Code, keywords: ['function', 'utility', 'actions', 'capabilities'] },
      { title: 'System Prompts', href: '/prompts', icon: MessageSquare, keywords: ['template', 'prompt', 'system', 'message'] },
      { title: 'Trust Parameter', href: '/trust', icon: Shield, keywords: ['security', 'safety', 'trust', 'permission'] },
    ]
  },
  {
    title: 'Prompt Formats',
    items: [
      { title: 'Format Support', href: '/prompts/formats', icon: FileText, difficulty: 'Interactive Demo', keywords: ['format', 'prompt', 'template', 'syntax'] },
    ]
  },
  {
    title: 'Debugging',
    items: [
      { title: '@xray Decorator', href: '/xray', icon: Bug, keywords: ['debug', 'xray', 'decorator', 'trace', 'monitor'] },
      { title: 'trace() Visual Flow', href: '/xray/trace', icon: GitBranch, keywords: ['trace', 'flow', 'visual', 'debug', 'execution'] },
    ]
  },
  {
    title: 'Security',
    items: [
      { title: 'Threat Model', href: '/threat-model', icon: Shield, keywords: ['security', 'threat', 'risk', 'safety', 'vulnerability'] },
    ]
  },
  {
    title: 'Examples',
    items: [
      { title: 'All Examples', href: '/examples', icon: FolderOpen, difficulty: 'Browse', keywords: ['examples', 'samples', 'demos', 'tutorials'] },
      { title: 'Hello World', href: '/examples/hello-world', icon: Sparkles, difficulty: 'Beginner', keywords: ['hello', 'basic', 'simple', 'first'] },
      { title: 'Calculator', href: '/examples/calculator', icon: Calculator, difficulty: 'Beginner', keywords: ['calculator', 'math', 'compute', 'arithmetic'] },
      { title: 'Weather Bot', href: '/examples/weather-bot', icon: Cloud, difficulty: 'Intermediate', keywords: ['weather', 'bot', 'api', 'forecast'] },
      { title: 'More Examples', href: '/examples#advanced', icon: Layers, keywords: ['advanced', 'more', 'complex', 'additional'] },
    ]
  },
  {
    title: 'Blog',
    items: [
      { title: 'All Posts', href: '/blog', icon: BookOpen, keywords: ['blog', 'posts', 'articles', 'news'] },
      { title: 'Network Protocol Design', href: '/blog/network-protocol-design', icon: GitBranch, difficulty: 'Architecture', keywords: ['network', 'protocol', 'architecture', 'design'] },
      { title: 'Why We Chose "Trust"', href: '/blog/trust-keyword', icon: Users, difficulty: 'Design Decision', keywords: ['trust', 'design', 'decision', 'philosophy'] },
    ]
  },
  {
    title: 'Roadmap',
    items: [
      { title: 'Coming Soon Features', href: '/roadmap', icon: Rocket, difficulty: 'Preview', keywords: ['roadmap', 'future', 'upcoming', 'features', 'soon'] },
    ]
  },
]

interface SearchResult {
  item: NavItem
  section: string
  score: number
  matches: string[]
}

export function DocsSidebar() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [openSections, setOpenSections] = useState<string[]>(['Getting Started'])
  const [isClientMounted, setIsClientMounted] = useState(false)
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copying' | 'success'>('idle')
  const pathname = usePathname()
  const searchInputRef = useRef<HTMLInputElement>(null)

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

  // Fuzzy search with scoring
  const performSearch = (query: string) => {
    if (!query.trim()) {
      setSearchResults([])
      return
    }

    const q = query.toLowerCase()
    const results: SearchResult[] = []

    navigation.forEach(section => {
      section.items.forEach(item => {
        let score = 0
        const matches: string[] = []

        // Title match (highest score)
        if (item.title.toLowerCase().includes(q)) {
          score += 10
          matches.push('title')
        }

        // Keywords match (medium score)
        if (item.keywords?.some(k => k.includes(q))) {
          score += 5
          matches.push('keywords')
        }

        // Section title match (low score)
        if (section.title.toLowerCase().includes(q)) {
          score += 2
          matches.push('section')
        }

        // Fuzzy match on title (very low score)
        const titleWords = item.title.toLowerCase().split(/\s+/)
        if (titleWords.some(word => word.startsWith(q))) {
          score += 1
          matches.push('partial')
        }

        if (score > 0) {
          results.push({
            item,
            section: section.title,
            score,
            matches
          })
        }
      })
    })

    // Sort by score (highest first)
    results.sort((a, b) => b.score - a.score)
    setSearchResults(results)
    setSelectedIndex(0)
  }

  // Keyboard navigation and shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K or Ctrl+K to focus search
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        searchInputRef.current?.focus()
        return
      }

      // Only handle navigation when search is active
      if (!searchQuery) return

      switch(e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex(i => Math.min(i + 1, searchResults.length - 1))
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex(i => Math.max(i - 1, 0))
          break
        case 'Enter':
          e.preventDefault()
          if (searchResults[selectedIndex]) {
            window.location.href = searchResults[selectedIndex].item.href
          }
          break
        case 'Escape':
          setSearchQuery('')
          setSearchResults([])
          searchInputRef.current?.blur()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [searchQuery, searchResults, selectedIndex])

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      performSearch(searchQuery)
    }, 150)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const toggleSection = (title: string) => {
    setOpenSections(prev => 
      prev.includes(title) 
        ? prev.filter(t => t !== title)
        : [...prev, title]
    )
  }

  // Filter navigation based on search
  const filteredNavigation = useMemo(() => {
    if (!searchQuery.trim()) return navigation

    const resultItems = new Set(searchResults.map(r => r.item))
    
    return navigation.map(section => ({
      ...section,
      items: section.items.filter(item => resultItems.has(item))
    })).filter(section => section.items.length > 0)
  }, [searchResults, searchQuery])

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
    <div className="w-[75vw] max-w-sm sm:w-64 lg:w-72 xl:w-80 bg-gray-900 border-r border-gray-800 flex flex-col h-screen sticky top-0 z-40">
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <Link href="/" className="flex items-center gap-3 group">
          <img src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" alt="ConnectOnion" className="w-8 h-8 rounded-lg object-cover" />
          <div>
            <div className="text-lg font-bold text-white">ConnectOnion</div>
            <div className="text-xs text-gray-400">Documentation</div>
          </div>
        </Link>
      </div>

      {/* Enhanced Search */}
      <div className="p-4 border-b border-gray-800">
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 transition-colors group-focus-within:text-purple-400" />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search docs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-8 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:border-purple-500 focus:ring-2 focus:ring-purple-500/30 focus:outline-none transition-all text-sm"
          />
          {searchQuery ? (
            <button
              onClick={() => {
                setSearchQuery('')
                setSearchResults([])
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 hover:bg-gray-700 rounded transition-colors"
              aria-label="Clear search"
            >
              <X className="w-4 h-4 text-gray-400 hover:text-white" />
            </button>
          ) : (
            <div className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-gray-500 font-mono px-1.5 py-0.5 bg-gray-700 rounded">
              ⌘K
            </div>
          )}
        </div>
        
        {/* Search help text - always visible */}
        {!searchQuery && (
          <div className="mt-2 text-[11px] text-gray-500">
            Search by title, keywords, or sections
          </div>
        )}
        
        {/* Search Results Summary */}
        {searchQuery && (
          <div className="mt-2 space-y-1">
            <div className="text-xs text-gray-400">
              {searchResults.length === 0 ? 'No' : searchResults.length} result{searchResults.length !== 1 ? 's' : ''} found
            </div>
            {searchResults.length > 0 && (
              <div className="text-[11px] text-gray-500 flex items-center gap-2">
                <div className="flex items-center gap-1">
                  <kbd className="px-1 py-0.5 text-[10px] bg-gray-700 rounded">↑</kbd>
                  <kbd className="px-1 py-0.5 text-[10px] bg-gray-700 rounded">↓</kbd>
                  <span>Navigate</span>
                </div>
                <span className="text-gray-600">•</span>
                <div className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 text-[10px] bg-gray-700 rounded">↵</kbd>
                  <span>Select</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="px-4 py-2 border-b border-gray-800">
        <button
          onClick={handleCopyAllDocs}
          disabled={copyStatus === 'copying'}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-gray-800 hover:bg-gray-700 disabled:bg-gray-800 rounded-md text-gray-300 hover:text-white disabled:text-gray-500 text-sm transition-all"
        >
          {copyStatus === 'copying' ? (
            <>
              <div className="w-3 h-3 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
              <span>Copying...</span>
            </>
          ) : copyStatus === 'success' ? (
            <>
              <Check className="w-4 h-4 text-green-400" />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-4 h-4" />
              <span>Copy All Docs</span>
            </>
          )}
        </button>
      </div>

      {/* Navigation with Search Highlighting */}
      <nav className="flex-1 overflow-y-auto py-4">
        {/* Quick Jump when searching */}
        {searchQuery && searchResults.length > 0 && (
          <div className="mb-4 px-4">
            <div className="text-xs text-gray-500 mb-2">Quick Jump</div>
            <div className="space-y-1">
              {searchResults.slice(0, 3).map((result, idx) => (
                <Link
                  key={result.item.href}
                  href={result.item.href}
                  className={`block px-3 py-2 rounded-md text-sm transition-all ${
                    idx === selectedIndex 
                      ? 'bg-purple-500/20 text-purple-200 ring-2 ring-purple-400/50' 
                      : 'bg-gray-800/50 text-gray-300 hover:bg-gray-800 hover:text-white'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {result.item.icon && <result.item.icon className="w-3 h-3" />}
                      <SearchHighlight 
                        text={result.item.title} 
                        query={searchQuery}
                      />
                    </div>
                    <div className="flex items-center gap-1">
                      {result.matches.includes('title') && (
                        <span className="text-[10px] px-1 bg-purple-900/30 text-purple-400 rounded">exact</span>
                      )}
                      {result.matches.includes('keywords') && (
                        <span className="text-[10px] px-1 bg-purple-900/30 text-purple-400 rounded">tag</span>
                      )}
                    </div>
                  </div>
                  <div className="text-[10px] text-gray-500 mt-1">{result.section}</div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Regular Navigation */}
        {filteredNavigation.map((section) => (
          <div key={section.title} className="mb-6">
            <button
              onClick={() => toggleSection(section.title)}
              className="w-full flex items-center justify-between px-4 py-2 text-left text-sm font-semibold text-gray-300 hover:text-white transition-colors"
            >
              <SearchHighlight 
                text={section.title} 
                query={searchQuery}
              />
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
                  
                  const isInResults = searchResults.some(r => r.item === item)
                  
                  return (
                    <li key={item.href} role="listitem">
                      <Link
                        href={item.href}
                        className={`block px-4 py-2.5 min-h-[40px] text-sm rounded-md mx-2 transition-all relative ${
                          isActive
                            ? 'bg-purple-500/20 text-purple-200 border-l-4 border-purple-400 font-medium'
                            : isInResults && searchQuery
                            ? 'bg-purple-500/10 text-purple-300 ring-1 ring-purple-500/30'
                            : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:ring-inset'
                        } ${isPromptExample ? 'pl-6' : ''}`}
                        aria-current={isActive ? 'page' : undefined}
                      >
                        <div className="flex items-center gap-3">
                          {IconComponent && (
                            <IconComponent className="w-4 h-4 flex-shrink-0" />
                          )}
                          <SearchHighlight 
                            text={item.title} 
                            query={searchQuery}
                            className="truncate flex-1"
                          />
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

        {/* No Results */}
        {searchQuery && searchResults.length === 0 && (
          <div className="px-4 py-8 text-center">
            <div className="text-gray-500 mb-2">No results found</div>
            <div className="text-xs text-gray-600">Try different keywords</div>
          </div>
        )}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-gray-800 space-y-2">
        {/* Community Links */}
        <div className="grid grid-cols-3 gap-1.5">
          <a
            href="https://github.com/wu-changxing/connectonion"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-1 py-2 px-2 bg-gray-800/30 hover:bg-gray-800/60 rounded-md text-gray-400 hover:text-white transition-all group"
            title="GitHub Repository"
          >
            <GitBranch className="w-4 h-4 group-hover:text-purple-400 transition-colors" />
            <span className="text-[10px]">GitHub</span>
          </a>
          <a
            href="https://pypi.org/project/connectonion/"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-1 py-2 px-2 bg-gray-800/30 hover:bg-gray-800/60 rounded-md text-gray-400 hover:text-white transition-all group"
            title="PyPI Package"
          >
            <Package className="w-4 h-4 group-hover:text-purple-400 transition-colors" />
            <span className="text-[10px]">PyPI</span>
          </a>
          <a
            href="https://discord.gg/4xfD9k8AUF"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-1 py-2 px-2 bg-gray-800/30 hover:bg-gray-800/60 rounded-md text-gray-400 hover:text-white transition-all group"
            title="Join Discord"
          >
            <MessageCircle className="w-4 h-4 group-hover:text-purple-400 transition-colors" />
            <span className="text-[10px]">Discord</span>
          </a>
        </div>
        
        {/* Version Status */}
        <div className="flex items-center justify-between px-2 py-1.5 bg-gray-800/20 rounded-md">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" title="Status: Active"></div>
            <span className="text-[11px] text-gray-400">v0.0.1b6</span>
          </div>
          <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded text-[10px] font-medium">BETA</span>
        </div>
      </div>
    </div>
  )
}
