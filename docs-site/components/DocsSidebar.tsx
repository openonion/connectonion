'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Search, FileText, Zap, Code, Settings, BookOpen, ChevronRight, ChevronDown, User, Database, Brain, Play, Lightbulb, FolderOpen, GitBranch, Shield, TrendingUp } from 'lucide-react'

const navigation = [
  {
    title: 'Getting Started',
    items: [
      { title: 'Introduction', href: '/' },
      { title: 'Quick Start', href: '/quickstart' },
    ]
  },
  {
    title: 'System Prompts',
    items: [
      { title: 'Overview', href: '/prompts' },
      { title: 'Examples Overview', href: '/prompts/examples' },
      { title: '1. Friendly Assistant', href: '/prompts/examples/friendly-assistant', icon: User, difficulty: 'Beginner' },
      { title: '2. Math Tutor', href: '/prompts/examples/math-tutor', icon: Code, difficulty: 'Beginner' },
      { title: '3. Customer Support', href: '/prompts/examples/customer-support', icon: User, difficulty: 'Intermediate' },
      { title: '4. Code Reviewer', href: '/prompts/examples/code-reviewer', icon: Code, difficulty: 'Advanced' },
      { title: '5. Data Analyst', href: '/prompts/examples/data-analyst', icon: Database, difficulty: 'Advanced' },
      { title: '6. Technical Writer', href: '/prompts/examples/technical-writer', icon: FileText, difficulty: 'Expert' },
      { title: '7. Security Analyst', href: '/prompts/examples/security-analyst', icon: Shield, difficulty: 'Expert' },
      { title: '8. Business Strategist', href: '/prompts/examples/business-strategist', icon: TrendingUp, difficulty: 'Expert' },
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
    title: 'Examples',
    items: [
      { title: 'Complete Examples', href: '/examples' },
    ]
  },
]

export function DocsSidebar() {
  const [searchQuery, setSearchQuery] = useState('')
  const [openSections, setOpenSections] = useState<string[]>(['Getting Started', 'System Prompts'])
  const pathname = usePathname()

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

  return (
    <div className="w-80 bg-gray-900 border-r border-gray-800 flex flex-col h-screen sticky top-0 z-40">
      {/* Header */}
      <div className="p-6 border-b border-gray-800">
        <Link href="/" className="flex items-center gap-3 group">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
            <BookOpen className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-lg font-bold text-white">ConnectOnion</div>
            <div className="text-xs text-gray-400">Documentation v0.0.1</div>
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
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium flex-shrink-0 ${
                              item.difficulty === 'Beginner' ? 'bg-green-900/50 text-green-400' :
                              item.difficulty === 'Intermediate' ? 'bg-yellow-900/50 text-yellow-400' :
                              item.difficulty === 'Advanced' ? 'bg-orange-900/50 text-orange-400' : 'bg-red-900/50 text-red-400'
                            }`}>
                              {item.difficulty.charAt(0)}
                            </span>
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
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-xs text-gray-400">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            <span>v0.0.1</span>
          </div>
        </div>
        
        {/* Quick Links */}
        <div className="flex gap-2">
          <a
            href="https://github.com/connectonion/connectonion"
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