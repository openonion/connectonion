/**
 * @purpose Main sidebar navigation component with search, collapsible sections, and copy features
 * @context Primary navigation for desktop users, always visible on lg+ screens
 * @llm-note Integrates full-text search from searchIndex, markdown search from markdownLoader,
 *           manages section collapse state, highlights active page, provides copy-all-docs button
 */
'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { 
  Search, ChevronRight, ChevronDown, Copy, Check, X, 
  Package, MessageCircle, Loader2, GitBranch
} from 'lucide-react'
import { DifficultyBadge } from './DifficultyBadge'
import { copyAllDocsToClipboard } from '../utils/copyAllDocs'
import { SearchHighlight } from './SearchHighlight'
import { performFullTextSearch, pageContentIndex } from '../utils/searchIndex'
import { searchPages } from '../utils/enhancedSearch'
import { searchMarkdownDocuments, getMatchSnippet } from '../utils/markdownLoader'
import { useCopyMarkdown } from '../hooks/useCopyMarkdown'
import { hasMarkdownContent } from '../utils/markdownMapping'
import { navigation as navData } from '../lib/navigation'

interface SearchResult {
  item: typeof navData[0]
  score: number
  matches: string[]
}

export function DocsSidebar() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [openSections, setOpenSections] = useState<string[]>(['Getting Started', 'Core Concepts'])
  const [isClientMounted, setIsClientMounted] = useState(false)
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copying' | 'success'>('idle')
  const pathname = usePathname()
  const searchInputRef = useRef<HTMLInputElement>(null)
  const { copyMarkdown, status: itemCopyStatus, copiedPath } = useCopyMarkdown()

  // Group navigation items by section for sidebar display
  const navigationSections = useMemo(() => {
    const sections: Record<string, typeof navData> = {}
    navData.forEach(item => {
      // Skip admin pages in sidebar
      if (item.section === 'Admin') return
      
      if (!sections[item.section]) {
        sections[item.section] = []
      }
      sections[item.section].push(item)
    })
    return sections
  }, [])

  // Auto-expand section containing current page
  useEffect(() => {
    const currentPage = navData.find(page => page.href === pathname)
    if (currentPage && !openSections.includes(currentPage.section)) {
      setOpenSections(prev => [...prev, currentPage.section])
    }
  }, [pathname])

  // Initialize from localStorage after client mount
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

  // Save to localStorage whenever sections change
  useEffect(() => {
    if (isClientMounted) {
      localStorage.setItem('docs-open-sections', JSON.stringify(openSections))
    }
  }, [openSections, isClientMounted])

  // Enhanced search
  const performSearch = async (query: string) => {
    if (!query.trim()) {
      setSearchResults([])
      return
    }

    const markdownResults = await searchMarkdownDocuments(query)
    const enhancedResults = searchPages(query)
    
    const results: SearchResult[] = []
    const processedHrefs = new Set<string>()
    
    // Process markdown search results first
    markdownResults.forEach(docResult => {
      const navItem = navData.find(item => item.href === docResult.href)
      if (navItem && !processedHrefs.has(navItem.href)) {
        processedHrefs.add(navItem.href)
        results.push({
          item: navItem,
          score: 150,
          matches: ['documentation']
        })
      }
    })
    
    // Process enhanced search results
    enhancedResults.forEach(pageResult => {
      const navItem = navData.find(item => item.href === pageResult.href)
      if (navItem && !processedHrefs.has(navItem.href)) {
        processedHrefs.add(navItem.href)
        results.push({
          item: navItem,
          score: 100,
          matches: ['content']
        })
      }
    })

    // Check navigation items directly
    if (results.length < 5) {
      const q = query.toLowerCase()
      navData.forEach(item => {
        if (processedHrefs.has(item.href)) return
        
        let score = 0
        const matches: string[] = []

        if (item.title.toLowerCase().includes(q)) {
          score += 10
          matches.push('title')
        }

        if (item.keywords?.some(k => k.includes(q))) {
          score += 5
          matches.push('keywords')
        }

        if (score > 0 && results.length < 10) {
          results.push({ item, score, matches })
        }
      })
    }

    results.sort((a, b) => b.score - a.score)
    setSearchResults(results.slice(0, 5))
    setSelectedIndex(0)
  }

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        searchInputRef.current?.focus()
        return
      }

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

  const toggleSection = (section: string) => {
    setOpenSections(prev => 
      prev.includes(section) 
        ? prev.filter(s => s !== section)
        : [...prev, section]
    )
  }

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

      {/* Search */}
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
        
        {!searchQuery && (
          <div className="mt-1.5 text-[11px] text-gray-500">
            Search everything • Typo-tolerant • Smart matching
          </div>
        )}
        
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

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-2 custom-scrollbar bg-gray-900/50">
        {/* Search Results Preview */}
        {searchQuery && searchResults.length > 0 && (
          <div className="mb-4 mx-1">
            <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg p-3 border border-purple-500/20">
              <div className="text-xs font-medium text-purple-400 mb-2">
                Top Matches ({searchResults.length} found)
              </div>
              <div className="space-y-1">
                {searchResults.map((result, idx) => (
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
                          <span className="text-xs text-gray-500">{result.item.section}</span>
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Regular Navigation */}
        {Object.entries(navigationSections).map(([section, items]) => (
          <div key={section} className="mb-2">
            <button
              onClick={() => toggleSection(section)}
              className="w-full flex items-center justify-between px-3 py-2 mb-2 text-left text-xs font-bold text-gray-400 uppercase tracking-wider hover:text-gray-200 transition-colors"
            >
              <SearchHighlight 
                text={section} 
                query={searchQuery}
              />
              {openSections.includes(section) ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
            </button>
            
            {openSections.includes(section) && (
              <ul className="space-y-0.5" role="list">
                {items.map((item) => {
                  const isActive = pathname === item.href
                  const IconComponent = item.icon
                  
                  return (
                    <li key={item.href} role="listitem" className="relative group">
                      <Link
                        href={item.href}
                        className={`block px-3 py-2.5 text-sm font-normal rounded-lg mx-1 transition-all relative ${
                          isActive
                            ? 'bg-purple-500/25 text-white font-medium shadow-sm ring-1 ring-purple-400/30'
                            : 'text-gray-300 hover:text-white hover:bg-gray-700/40'
                        }`}
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
                      
                      {/* Copy button */}
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
            <span className="text-xs text-gray-400">v0.1.8</span>
          </div>
        </div>
      </div>
    </div>
  )
}