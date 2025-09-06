'use client'

import React from 'react'
import { Calculator, Chrome, ArrowRight, Code, Play } from 'lucide-react'
import { ContentNavigation } from '../../components/ContentNavigation'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'

const examples = [
  {
    id: 'calculator',
    title: 'Calculator Agent',
    description: 'Learn the fundamentals with a simple math calculator that demonstrates tool creation, input validation, and error handling',
    icon: Calculator,
    color: 'text-blue-400',
    bgColor: 'bg-blue-900/20',
    borderColor: 'border-blue-500/30',
    difficulty: 'Beginner',
    concepts: ['Function tools', 'Input validation', 'Error handling', 'Safe evaluation'],
    href: '/examples/calculator',
    preview: `def calculate(expression: str) -> str:
    # Validate input safety
    allowed = set('0123456789+-*/()., ')
    if not all(c in allowed for c in expression):
        return "Error: Invalid characters"
    
    try:
        result = eval(expression)
        return str(result)
    except:
        return "Error: Invalid expression"`
  },
  {
    id: 'browser',
    title: 'Browser Automation',
    description: 'Control web browsers with natural language using Playwright integration for screenshots, scraping, and automation',
    icon: Chrome,
    color: 'text-purple-400',
    bgColor: 'bg-purple-900/20',
    borderColor: 'border-purple-500/30',
    difficulty: 'Intermediate',
    concepts: ['Browser control', 'Screenshots', 'Web scraping', 'Natural language commands'],
    href: '/examples/browser',
    preview: `# Control browser with natural language
agent.input("Navigate to example.com")
agent.input("Take a screenshot")
agent.input("Extract all links from the page")
agent.input("Fill search box with 'AI' and submit")`
  }
]

export default function ExamplesPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 to-black text-white">
      <div className="max-w-7xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-12">
          <nav className="flex items-center gap-2 text-sm text-gray-400 mb-6">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <ArrowRight className="w-4 h-4" />
            <span className="text-white">Examples</span>
          </nav>
          
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-4xl font-bold">Agent Building Examples</h1>
            <CopyMarkdownButton />
          </div>
          
          <p className="text-xl text-gray-300">
            Master ConnectOnion through practical examples, from simple fundamentals to advanced automation
          </p>
        </div>

        {/* Progressive Learning Path */}
        <div className="mb-12 p-6 bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-lg border border-blue-500/20">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Code className="w-5 h-5 text-blue-400" />
            Progressive Learning Path
          </h2>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center text-white font-bold">1</div>
              <div>
                <div className="font-semibold">Calculator</div>
                <div className="text-sm text-gray-400">Learn the basics</div>
              </div>
            </div>
            <ArrowRight className="w-5 h-5 text-gray-500" />
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 bg-purple-500 rounded-full flex items-center justify-center text-white font-bold">2</div>
              <div>
                <div className="font-semibold">Browser</div>
                <div className="text-sm text-gray-400">Advanced automation</div>
              </div>
            </div>
          </div>
        </div>

        {/* Example Cards */}
        <div className="grid md:grid-cols-2 gap-6 mb-12">
          {examples.map((example, index) => (
            <Link
              key={example.id}
              href={example.href}
              className={`group block p-6 rounded-lg border ${example.borderColor} ${example.bgColor} hover:scale-[1.02] transition-all duration-200`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg bg-gray-800 ${example.color}`}>
                    <example.icon className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold text-white flex items-center gap-2">
                      {example.title}
                      {index === 0 && (
                        <span className="text-xs px-2 py-1 bg-green-500/20 text-green-400 rounded-full">
                          Start Here
                        </span>
                      )}
                    </h3>
                    <span className={`text-sm ${example.difficulty === 'Beginner' ? 'text-green-400' : 'text-purple-400'}`}>
                      {example.difficulty}
                    </span>
                  </div>
                </div>
                <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-white transition-colors" />
              </div>
              
              <p className="text-gray-300 mb-4">
                {example.description}
              </p>
              
              <div className="mb-4">
                <div className="text-sm font-semibold text-gray-400 mb-2">What you'll learn:</div>
                <div className="flex flex-wrap gap-2">
                  {example.concepts.map((concept, i) => (
                    <span
                      key={i}
                      className="text-xs px-2 py-1 bg-gray-800 text-gray-300 rounded"
                    >
                      {concept}
                    </span>
                  ))}
                </div>
              </div>
              
              {/* Code Preview */}
              <div className="bg-gray-900 rounded p-3 overflow-hidden">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-gray-500">Code Preview</span>
                  <Play className="w-3 h-3 text-gray-500" />
                </div>
                <pre className="text-xs text-gray-400 overflow-x-auto">
                  <code>{example.preview}</code>
                </pre>
              </div>
            </Link>
          ))}
        </div>

        {/* Call to Action */}
        <div className="text-center py-8 px-6 bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-lg border border-blue-500/20">
          <h2 className="text-2xl font-bold mb-4">Ready to Build Your First Agent?</h2>
          <p className="text-gray-300 mb-6">
            Start with the Calculator example to learn the fundamentals, then advance to Browser automation
          </p>
          <Link
            href="/examples/calculator"
            className="inline-flex items-center gap-2 bg-blue-500 hover:bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold transition-colors"
          >
            Start with Calculator
            <ArrowRight className="w-5 h-5" />
          </Link>
        </div>

        {/* Navigation */}
        <ContentNavigation />
      </div>
    </div>
  )
}