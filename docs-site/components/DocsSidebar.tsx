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
  Layers, Sparkles, Calculator, Bot, Package, MessageCircle, Loader2
} from 'lucide-react'
import { DifficultyBadge } from './DifficultyBadge'
import { copyAllDocsToClipboard } from '../utils/copyAllDocs'
import { SearchHighlight } from './SearchHighlight'
import { performFullTextSearch, pageContentIndex } from '../utils/searchIndex'
import { searchPages } from '../utils/enhancedSearch'
import { searchMarkdownDocuments, getMatchSnippet } from '../utils/markdownLoader'
import { useCopyMarkdown } from '../hooks/useCopyMarkdown'
import { hasMarkdownContent } from '../utils/markdownMapping'

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
      { title: 'System Prompts', href: '/prompts', icon: MessageSquare, difficulty: 'Start Here', keywords: ['template', 'prompt', 'system', 'message', 'personality', 'behavior'] },
      { title: 'Tools', href: '/tools', icon: Code, keywords: ['function', 'utility', 'actions', 'capabilities', 'tools'] },
      { title: 'max_iterations', href: '/max-iterations', icon: Gauge, keywords: ['loop', 'limit', 'iteration', 'control', 'safety'] },
      { title: 'LLM Function', href: '/llm_do', icon: Zap, keywords: ['ai', 'model', 'openai', 'language', 'llm_do', 'direct'] },
      { title: 'Trust Parameter', href: '/trust', icon: Shield, keywords: ['security', 'safety', 'trust', 'permission', 'multi-agent'] },
      { title: '@xray Decorator', href: '/xray', icon: Bug, keywords: ['debug', 'xray', 'decorator', 'trace', 'monitor', 'visibility'] },
    ]
  },
  {
    title: 'Advanced Features',
    items: [
      { title: 'trace() Visual Flow', href: '/xray/trace', icon: GitBranch, keywords: ['trace', 'flow', 'visual', 'debug', 'execution'] },
      { title: 'Prompt Formats', href: '/prompts/formats', icon: FileText, difficulty: 'Interactive Demo', keywords: ['format', 'prompt', 'template', 'syntax'] },
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
      { title: 'More Examples', href: '/examples', icon: Layers, keywords: ['advanced', 'more', 'complex', 'additional'] },
    ]
  },
  {
    title: 'Blog',
    items: [
      { title: 'All Posts', href: '/blog', icon: BookOpen, keywords: ['blog', 'posts', 'articles', 'news'] },
      { title: 'Network Protocol Design', href: '/blog/network-protocol-design', icon: GitBranch, difficulty: 'Architecture', keywords: ['network', 'protocol', 'architecture', 'design'] },
      { title: 'Why We Chose "Trust"', href: '/blog/trust-keyword', icon: Users, difficulty: 'Design Decision', keywords: ['trust', 'design', 'decision', 'authentication'] },
      { title: 'Why `llm_do()` Over `llm()`', href: '/blog/llm-do', icon: Code, difficulty: 'Design Decision', keywords: ['llm', 'function', 'naming', 'api', 'design'] },
      { title: 'Why `input()` Over `run()`', href: '/blog/input-method', icon: Terminal, difficulty: 'Design Decision', keywords: ['input', 'run', 'api', 'mental', 'model', 'ux'] },
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
  const [copyPageStatus, setCopyPageStatus] = useState<'idle' | 'copying' | 'success'>('idle')
  const pathname = usePathname()
  const searchInputRef = useRef<HTMLInputElement>(null)
  const { copyMarkdown, status: itemCopyStatus, copiedPath } = useCopyMarkdown()

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

  // Enhanced full-text search with fuzzy matching and typo tolerance
  const performSearch = async (query: string) => {
    if (!query.trim()) {
      setSearchResults([])
      return
    }

    // Search markdown documents for comprehensive results
    const markdownResults = await searchMarkdownDocuments(query)
    
    // Use the enhanced search with fuzzy matching  
    const enhancedResults = searchPages(query)
    
    // Map results back to navigation items
    const results: SearchResult[] = []
    const processedHrefs = new Set<string>()
    
    // Process markdown search results first (highest priority)
    markdownResults.forEach(docResult => {
      // Find the corresponding navigation item
      navigation.forEach(section => {
        const navItem = section.items.find(item => item.href === docResult.href)
        if (navItem && !processedHrefs.has(navItem.href)) {
          processedHrefs.add(navItem.href)
          results.push({
            item: navItem,
            section: docResult.section || section.title,
            score: 150, // Highest score for markdown content matches
            matches: ['documentation']
          })
        }
      })
    })
    
    // Process enhanced search results
    enhancedResults.forEach(pageResult => {
      // Find the corresponding navigation item
      navigation.forEach(section => {
        const navItem = section.items.find(item => item.href === pageResult.href)
        if (navItem && !processedHrefs.has(navItem.href)) {
          processedHrefs.add(navItem.href)
          results.push({
            item: navItem,
            section: section.title,
            score: 100, // High score for enhanced matches
            matches: ['content']
          })
        }
      })
    })

    // If we have fewer than 5 results, also check navigation items directly
    if (results.length < 5) {
      const q = query.toLowerCase()
      navigation.forEach(section => {
        section.items.forEach(item => {
          if (processedHrefs.has(item.href)) return // Skip if already added
          
          let score = 0
          const matches: string[] = []

          // Title match
          if (item.title.toLowerCase().includes(q)) {
            score += 10
            matches.push('title')
          }

          // Keywords match
          if (item.keywords?.some(k => k.includes(q))) {
            score += 5
            matches.push('keywords')
          }

          if (score > 0 && results.length < 10) { // Limit total results
            results.push({
              item,
              section: section.title,
              score,
              matches
            })
          }
        })
      })
    }

    // Sort by score (highest first)
    results.sort((a, b) => b.score - a.score)
    setSearchResults(results.slice(0, 5)) // Show top 5 results
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
    <div className="w-[75vw] max-w-sm sm:w-64 lg:w-72 xl:w-80 bg-gray-900 border-r border-gray-700/50 flex flex-col h-screen sticky top-0 z-40">
      {/* Header */}
      <div className="p-4 border-b border-gray-700/50">
        <Link href="/" className="flex items-center gap-3 group">
          <img src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" alt="ConnectOnion" className="w-8 h-8 rounded-lg object-cover" />
          <div>
            <div className="text-lg font-bold text-white">ConnectOnion</div>
            <div className="text-sm text-gray-300">Documentation</div>
          </div>
        </Link>
      </div>

      {/* Enhanced Search */}
      <div className="p-4 pb-2 bg-gray-800/30">
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 transition-colors group-focus-within:text-purple-400" />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search docs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-8 py-2.5 bg-gray-800/50 border border-gray-600 rounded-lg text-gray-100 placeholder-gray-400 focus:border-purple-400 focus:ring-2 focus:ring-purple-400/20 focus:outline-none transition-all text-sm font-normal"
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
        
        {/* Search help text - more informative */}
        {!searchQuery && (
          <div className="mt-1.5 text-[11px] text-gray-500">
            Search everything • Typo-tolerant • Smart matching
          </div>
        )}
        
        {/* Search Results Summary */}
        {searchQuery && (
          <div className="mt-1.5">
            <div className="text-[11px] text-gray-500">
              {searchResults.length === 0 
                ? 'No results found' 
                : `${searchResults.length} result${searchResults.length !== 1 ? 's' : ''} • Use arrow keys`
              }
            </div>
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="px-3 py-2 border-b border-gray-700/50">
        <button
          onClick={handleCopyAllDocs}
          disabled={copyStatus === 'copying'}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-gradient-to-r from-purple-600/80 to-pink-600/80 hover:from-purple-600 hover:to-pink-600 disabled:from-gray-600 disabled:to-gray-700 rounded-lg text-white font-medium text-sm transition-all transform hover:scale-[1.02] shadow-lg shadow-purple-500/20"
        >
          {copyStatus === 'copying' ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              <span>Copying...</span>
            </>
          ) : copyStatus === 'success' ? (
            <>
              <Check className="w-4 h-4" />
              <span>Copied to Clipboard!</span>
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
      <nav className="flex-1 overflow-y-auto py-4 px-2 custom-scrollbar bg-gray-900/50">
        {/* Search Results Preview */}
        {searchQuery && searchResults.length > 0 && (
          <div className="mb-4 mx-1">
            <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg p-3 border border-purple-500/20">
              <div className="text-xs font-medium text-purple-400 mb-2 flex items-center gap-2">
                <Sparkles className="w-3 h-3" />
                Top Matches
                <span className="text-[10px] text-gray-500">({searchResults.length} found)</span>
              </div>
              <div className="space-y-1">
                {searchResults.slice(0, 5).map((result, idx) => (
                  <Link
                    key={result.item.href}
                    href={result.item.href}
                    className={`block px-3 py-2 rounded-md text-sm transition-all ${
                      idx === selectedIndex 
                        ? 'bg-purple-500/20 text-purple-100' 
                        : 'hover:bg-purple-500/10 text-gray-300 hover:text-purple-200'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {result.item.icon && <result.item.icon className={`w-4 h-4 ${idx === selectedIndex ? 'text-purple-300' : 'text-gray-500'}`} />}
                      <div className="flex-1">
                        <SearchHighlight 
                          text={result.item.title} 
                          query={searchQuery}
                        />
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-xs text-gray-500">{result.section}</span>
                          {result.matches.includes('content') && (
                            <span className="text-[9px] px-1 py-0.5 bg-blue-500/20 text-blue-300 rounded">content</span>
                          )}
                        </div>
                      </div>
                      {idx === 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 bg-purple-500/20 text-purple-300 rounded-full font-medium">BEST</span>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
              {searchResults.length > 5 && (
                <div className="text-[10px] text-gray-500 text-center mt-2">
                  +{searchResults.length - 5} more results
                </div>
              )}
            </div>
          </div>
        )}

        {/* Regular Navigation */}
        {filteredNavigation.map((section, sectionIdx) => (
          <div key={section.title} className={`${sectionIdx > 0 ? 'mt-4' : ''} mb-2`}>
            <button
              onClick={() => toggleSection(section.title)}
              className="w-full flex items-center justify-between px-3 py-2 mb-2 text-left text-xs font-bold text-gray-400 uppercase tracking-wider hover:text-gray-200 transition-colors"
            >
              <SearchHighlight 
                text={section.title} 
                query={searchQuery}
              />
              {openSections.includes(section.title) ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
            </button>
            
            {openSections.includes(section.title) && (
              <ul className="space-y-0.5" role="list">
                {section.items.map((item) => {
                  const isActive = pathname === item.href
                  const IconComponent = item.icon
                  const isPromptExample = item.href.includes('/prompts/examples/') && item.href !== '/prompts/examples'
                  
                  const isInResults = searchResults.some(r => r.item === item)
                  
                  return (
                    <li key={item.href} role="listitem" className="relative group">
                      <Link
                        href={item.href}
                        className={`block px-3 py-2.5 text-sm font-normal rounded-lg mx-1 transition-all relative ${
                          isActive
                            ? 'bg-purple-500/25 text-white font-medium shadow-sm ring-1 ring-purple-400/30'
                            : isInResults && searchQuery
                            ? 'bg-purple-500/10 text-purple-100'
                            : 'text-gray-300 hover:text-white hover:bg-gray-700/40'
                        } ${isPromptExample ? 'ml-3' : ''}`}
                        aria-current={isActive ? 'page' : undefined}
                      >
                        <div className="flex items-center gap-2.5">
                          {IconComponent && (
                            <IconComponent className={`w-4 h-4 flex-shrink-0 ${
                              isActive ? 'text-purple-300' : 'text-gray-400'
                            }`} />
                          )}
                          <SearchHighlight 
                            text={item.title} 
                            query={searchQuery}
                            className="truncate flex-1"
                          />
                          {item.difficulty && (
                            <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${
                              item.difficulty === 'Start Here' 
                                ? 'bg-purple-500/20 text-purple-400' 
                                : item.difficulty === 'Beginner'
                                ? 'bg-green-500/20 text-green-400'
                                : item.difficulty === 'Intermediate'
                                ? 'bg-yellow-500/20 text-yellow-400'
                                : 'bg-gray-500/20 text-gray-400'
                            }`}>
                              {item.difficulty}
                            </span>
                          )}
                        </div>
                      </Link>
                      
                      {/* Copy button - only shows on hover for desktop, and only if page has markdown */}
                      {hasMarkdownContent(item.href) && (
                        <button
                          onClick={(e) => {
                            e.preventDefault()
                            e.stopPropagation()
                            copyMarkdown(item.href)
                          }}
                          className="absolute right-2 top-1/2 -translate-y-1/2
                                     opacity-0 group-hover:opacity-100
                                     transition-opacity duration-200
                                     p-1.5 rounded-md hover:bg-gray-600/50
                                     hidden lg:block"
                          title="Copy page as markdown"
                        >
                          {itemCopyStatus === 'loading' && copiedPath === item.href ? (
                            <Loader2 className="w-4 h-4 text-gray-400 animate-spin" />
                          ) : itemCopyStatus === 'success' && copiedPath === item.href ? (
                            <Check className="w-4 h-4 text-green-400" />
                          ) : (
                            <Copy className="w-4 h-4 text-gray-400 hover:text-white" />
                          )}
                        </button>
                      )}
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
      <div className="border-t border-gray-700/50 bg-gray-800/30">
        {/* Community Links */}
        <div className="flex items-center justify-around py-2 px-2">
          <a
            href="https://github.com/wu-changxing/connectonion"
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-lg text-gray-400 hover:text-purple-300 hover:bg-gray-700/50 transition-all"
            title="GitHub"
          >
            <GitBranch className="w-4 h-4" />
          </a>
          <a
            href="https://pypi.org/project/connectonion/"
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-lg text-gray-400 hover:text-purple-300 hover:bg-gray-700/50 transition-all"
            title="PyPI"
          >
            <Package className="w-4 h-4" />
          </a>
          <a
            href="https://discord.gg/4xfD9k8AUF"
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-lg text-gray-400 hover:text-purple-300 hover:bg-gray-700/50 transition-all"
            title="Discord"
          >
            <MessageCircle className="w-4 h-4" />
          </a>
          <div className="flex items-center gap-2 px-2">
            <div className="w-1.5 h-1.5 bg-green-500 rounded-full" />
            <span className="text-xs text-gray-400">v0.0.1b6</span>
            <span className="text-[9px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded-full font-bold">BETA</span>
          </div>
        </div>
      </div>
    </div>
  )
}
