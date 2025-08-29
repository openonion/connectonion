'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { 
  Search, FileText, Zap, Code, Shield, BookOpen, 
  ChevronRight, ChevronDown, Terminal, Rocket, Cloud, 
  MoreHorizontal, X, Command, ArrowUp, ArrowDown,
  FolderOpen, GitBranch, Users, Gauge, Copy, Check,
  Hash, Eye, EyeOff
} from 'lucide-react'
import { SearchHighlight } from './SearchHighlight'

// Same navigation data structure
const navigation = [
  {
    title: 'Getting Started',
    items: [
      { title: 'Introduction', href: '/', keywords: ['intro', 'overview', 'start'] },
      { title: 'Quick Start', href: '/quickstart', keywords: ['setup', 'install', 'begin'] },
      { title: 'CLI Reference', href: '/cli', icon: Terminal, keywords: ['command', 'terminal'] },
    ]
  },
  {
    title: 'Core Concepts',
    items: [
      { title: 'max_iterations', href: '/max-iterations', icon: Gauge, difficulty: 'Start Here', keywords: ['loop', 'limit'] },
      { title: 'LLM Function', href: '/llm_do', icon: Zap, keywords: ['ai', 'model', 'llm_do'] },
      { title: 'Tools', href: '/tools', icon: Code, keywords: ['function', 'utility'] },
      { title: 'System Prompts', href: '/prompts', icon: FileText, keywords: ['template', 'prompt'] },
      { title: 'Trust Parameter', href: '/trust', icon: Shield, keywords: ['security', 'safety'] },
    ]
  },
  // ... rest of navigation
]

interface SearchResult {
  item: any
  section: string
  score: number
  matches: string[]
}

export function EnhancedDocsSidebar() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [showAllSections, setShowAllSections] = useState(false)
  const [openSections, setOpenSections] = useState<string[]>(['Getting Started'])
  const pathname = usePathname()
  const searchInputRef = useRef<HTMLInputElement>(null)

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

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
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

  // Auto-expand sections with matches
  useEffect(() => {
    if (searchResults.length > 0) {
      const sectionsWithMatches = [...new Set(searchResults.map(r => r.section))]
      setOpenSections(prev => [...new Set([...prev, ...sectionsWithMatches])])
    }
  }, [searchResults])

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

  return (
    <div className="w-[75vw] max-w-sm sm:w-64 lg:w-72 xl:w-80 bg-gray-900 border-r border-gray-800 flex flex-col h-screen">
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <Link href="/" className="flex items-center gap-3">
          <img 
            src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" 
            alt="ConnectOnion" 
            className="w-8 h-8 rounded-lg"
          />
          <div>
            <div className="text-lg font-bold text-white">ConnectOnion</div>
            <div className="text-xs text-gray-400">Documentation</div>
          </div>
        </Link>
      </div>

      {/* Enhanced Search */}
      <div className="p-4 border-b border-gray-800">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search (⌘K)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-8 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:border-purple-500 focus:ring-2 focus:ring-purple-500/30 focus:outline-none text-sm"
          />
          {searchQuery && (
            <button
              onClick={() => {
                setSearchQuery('')
                setSearchResults([])
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-gray-700 rounded"
            >
              <X className="w-3 h-3 text-gray-400" />
            </button>
          )}
        </div>
        
        {/* Search Results Summary */}
        {searchQuery && (
          <div className="mt-2 space-y-1">
            <div className="text-xs text-gray-400">
              {searchResults.length} results for "{searchQuery}"
            </div>
            {searchResults.length > 0 && (
              <div className="text-xs text-gray-500 flex items-center gap-1">
                <ArrowUp className="w-3 h-3" />
                <ArrowDown className="w-3 h-3" />
                to navigate
                <span className="mx-1">·</span>
                <span className="font-mono text-[10px] border border-gray-700 px-1 rounded">↵</span>
                to select
              </div>
            )}
          </div>
        )}
      </div>

      {/* Navigation with Search Highlighting */}
      <nav className="flex-1 overflow-y-auto py-4">
        {/* Quick Actions when searching */}
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
                      ? 'bg-purple-600/20 text-purple-300 border border-purple-500/50' 
                      : 'bg-gray-800/50 text-gray-300 hover:bg-gray-800'
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
                        <span className="text-[10px] px-1 bg-green-900/50 text-green-400 rounded">title</span>
                      )}
                      {result.matches.includes('keywords') && (
                        <span className="text-[10px] px-1 bg-blue-900/50 text-blue-400 rounded">keyword</span>
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
        {(searchQuery ? filteredNavigation : navigation).map((section) => (
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
              <ul className="mt-2 space-y-1">
                {section.items.map((item) => {
                  const isActive = pathname === item.href
                  const isInResults = searchResults.some(r => r.item === item)
                  
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        className={`block px-4 py-2.5 min-h-[40px] text-sm rounded-md mx-2 transition-all relative ${
                          isActive
                            ? 'nav-current'
                            : isInResults && searchQuery
                            ? 'bg-yellow-900/10 text-yellow-200 border border-yellow-500/20'
                            : 'text-gray-300 hover:text-white hover:bg-gray-800/50'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          {item.icon ? (
                            <item.icon className="w-4 h-4 flex-shrink-0" />
                          ) : (
                            <Hash className="w-3 h-3 opacity-30" />
                          )}
                          <SearchHighlight 
                            text={item.title} 
                            query={searchQuery}
                            className="truncate flex-1"
                          />
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

      {/* Footer Actions */}
      <div className="p-4 border-t border-gray-800 space-y-2">
        <button
          onClick={() => setShowAllSections(!showAllSections)}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-gray-800 hover:bg-gray-700 rounded-md text-gray-300 text-sm transition-colors"
        >
          {showAllSections ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          {showAllSections ? 'Collapse All' : 'Expand All'}
        </button>
        
        <div className="flex items-center justify-center gap-2 text-xs text-gray-500">
          <Command className="w-3 h-3" />
          <span>K to search</span>
        </div>
      </div>
    </div>
  )
}