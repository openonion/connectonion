/*
  @date: 2025-01-01
  @description: Examples Overview Page
  
  DESIGN ISSUES TO FIX:
  
  1. **Card Layout Problems** (Priority: HIGH)
     - Cards have inconsistent heights causing misalignment
     - Difficulty badges hard to scan - no visual hierarchy
     - Preview code snippets too small and cut off
     - Fix: Use CSS grid with equal heights, add difficulty color coding, expand preview area
  
  2. **Navigation Flow** (Priority: HIGH)
     - No clear learning path from beginner to advanced
     - Missing visual progression indicators
     - Cards don't show estimated completion time
     - Fix: Add numbered progression path, visual flow arrows, time estimates
  
  3. **Information Overload** (Priority: MEDIUM)
     - Too many concepts listed per card
     - Preview code distracts from card selection
     - No filtering or search functionality
     - Fix: Show max 3 concepts, move preview to hover/modal, add filter buttons
  
  4. **Responsive Issues** (Priority: MEDIUM)
     - Grid doesn't adapt well to tablet sizes
     - Code previews unreadable on mobile
     - Icon sizes too small on touch devices
     - Fix: Use responsive grid (1-2-3 columns), hide previews on mobile, increase touch targets
  
  5. **Visual Hierarchy** (Priority: LOW)
     - All cards have equal visual weight
     - No emphasis on recommended starting point
     - Color coding inconsistent with difficulty
     - Fix: Highlight "Start Here" card, use consistent color progression, add recommended badges
  
  NAVIGATION INCONSISTENCY FOUND (2025-01-02):
  - NO PageNavigation component - just lists examples
  - Has breadcrumb navigation at top
  - Has CopyMarkdownButton component
  - Links to example pages that use custom navigation
  - Acts as hub page but no prev/next navigation
  - Child pages have "Previous/Next in series" pattern
*/

'use client'

import React, { useState } from 'react'
import { Copy, Check, Play, Terminal, ArrowRight, Code, Database, User, FileText, Calculator, BookOpen, Shield, Globe, ShoppingCart, ChevronRight, ExternalLink, Chrome } from 'lucide-react'
import { ContentNavigation } from '../../components/ContentNavigation'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'

const examples = [
  {
    id: 'hello-world',
    title: '1. Hello World Agent',
    description: 'The simplest possible agent - just one greeting tool',
    icon: User,
    color: 'text-green-400',
    bgColor: 'bg-green-900/20',
    borderColor: 'border-green-500/30',
    difficulty: 'Beginner',
    concepts: ['Basic tool creation', 'Agent initialization', 'Simple interactions'],
    href: '/examples/hello-world',
    preview: `def greet(name: str) -> str:
    return f"Hello, {name}!"

agent = Agent(name="greeter", tools=[greet])`
  },
  {
    id: 'calculator',
    title: '2. Basic Calculator',
    description: 'Safe math operations with input validation and error handling',
    icon: Calculator,
    color: 'text-blue-400',
    bgColor: 'bg-blue-900/20',
    borderColor: 'border-blue-500/30',
    difficulty: 'Beginner',
    concepts: ['Input validation', 'Error handling', 'Safe expression evaluation'],
    href: '/examples/calculator',
    preview: `def calculate(expression: str) -> str:
    # Validate input safety
    allowed = set('0123456789+-*/()., ')
    if not all(c in allowed for c in expression):
        return "Error: Invalid characters"`
  },
  {
    id: 'weather-bot',
    title: '3. Weather Bot',
    description: 'Multi-city weather system with data processing and tool coordination',
    icon: Database,
    color: 'text-cyan-400',
    bgColor: 'bg-cyan-900/20',
    borderColor: 'border-cyan-500/30',
    difficulty: 'Beginner',
    concepts: ['Data lookup', 'Tool coordination', 'Structured output'],
    href: '/examples/weather-bot',
    preview: `def get_weather(city: str) -> dict:
    weather_db = {
        "new york": {"temp": 72, "condition": "sunny"},
        "london": {"temp": 65, "condition": "cloudy"}
    }`
  },
  {
    id: 'task-manager',
    title: '4. Task Manager',
    description: 'Full-featured task management with priorities, due dates, and analytics',
    icon: FileText,
    color: 'text-yellow-400',
    bgColor: 'bg-yellow-900/20',
    borderColor: 'border-yellow-500/30',
    difficulty: 'Intermediate',
    concepts: ['State management', 'CRUD operations', 'Data filtering'],
    href: '/examples/task-manager',
    preview: `def add_task(title: str, priority: str = "medium") -> str:
    task = {
        "id": task_counter,
        "title": title,
        "priority": priority
    }`
  },
  {
    id: 'math-tutor-agent',
    title: '5. Math Tutor Agent',
    description: 'Interactive learning system with step-by-step explanations and encouragement',
    icon: BookOpen,
    color: 'text-orange-400',
    bgColor: 'bg-orange-900/20',
    borderColor: 'border-orange-500/30',
    difficulty: 'Intermediate',
    concepts: ['Educational patterns', 'Step-by-step guidance', 'Answer validation'],
    href: '/examples/math-tutor-agent',
    preview: `def solve_equation(equation: str) -> str:
    return """Let's solve 2x + 5 = 15 step by step:
    Step 1: Subtract 5 from both sides
    2x = 10
    Step 2: Divide by 2
    x = 5"""`
  },
  {
    id: 'file-analyzer',
    title: '6. File Analyzer',
    description: 'System integration with file operations, security warnings, and directory traversal',
    icon: Shield,
    color: 'text-purple-400',
    bgColor: 'bg-purple-900/20',
    borderColor: 'border-purple-500/30',
    difficulty: 'Advanced',
    concepts: ['File system integration', 'Security considerations', 'Content analysis'],
    href: '/examples/file-analyzer',
    preview: `def analyze_file(filepath: str) -> str:
    path = Path(filepath)
    if not path.exists():
        return f"File not found: {filepath}"
    
    # Security checks for executable files`
  },
  {
    id: 'api-client',
    title: '7. API Client',
    description: 'HTTP requests, external API integration, and comprehensive error handling',
    icon: Globe,
    color: 'text-indigo-400',
    bgColor: 'bg-indigo-900/20',
    borderColor: 'border-indigo-500/30',
    difficulty: 'Advanced',
    concepts: ['HTTP methods', 'API integration', 'Network error handling'],
    href: '/examples/api-client',
    preview: `def make_api_request(url: str, method: str = "GET") -> str:
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return f"✅ Success: {response.text[:1000]}"`
  },
  {
    id: 'browser-automation',
    title: '8. Browser Automation',
    description: 'Web automation with Playwright - navigate, screenshot, and extract content',
    icon: Chrome,
    color: 'text-purple-400',
    bgColor: 'bg-purple-900/20',
    borderColor: 'border-purple-500/30',
    difficulty: 'Advanced',
    concepts: ['Stateful tools', 'Browser control', 'Content extraction'],
    href: '/examples/browser-automation',
    preview: `class BrowserAutomation:
    def navigate(self, url: str) -> str:
        self._page.goto(url)
        return f"Navigated to: {url}"

agent = Agent(tools=[browser])`
  },
  {
    id: 'ecommerce-manager',
    title: '9. E-commerce Manager',
    description: 'Enterprise-grade business logic with inventory, orders, customers, and analytics',
    icon: ShoppingCart,
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-900/20',
    borderColor: 'border-emerald-500/30',
    difficulty: 'Expert',
    concepts: ['Business logic', 'Multi-system coordination', 'Enterprise workflows'],
    href: '/examples/ecommerce-manager',
    preview: `def process_order(customer_name: str, product: str, quantity: int) -> str:
    # Calculate taxes, verify inventory, update customer records
    subtotal = unit_price * quantity
    tax = subtotal * 0.08
    total = subtotal + tax`
  }
]

export default function ExamplesPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# ConnectOnion Agent Building Examples

A comprehensive collection of 9 progressive examples, from simple "Hello World" to enterprise-grade business applications. Each example builds on previous concepts with complete working code, realistic outputs, and detailed explanations.

## 📚 Complete Learning Path

### 🟢 Beginner Level (Examples 1-3)
- **Hello World Agent**: Basic tool creation and agent initialization
- **Calculator Agent**: Input validation and error handling patterns
- **Weather Bot**: Multi-tool coordination and data processing

### 🟡 Intermediate Level (Examples 4-5)
- **Task Manager**: State management, CRUD operations, and data persistence
- **Math Tutor Agent**: Educational AI patterns and step-by-step explanations

### 🔴 Advanced Level (Examples 6-8)
- **File Analyzer**: System integration, security considerations, and file operations
- **API Client**: HTTP requests, external API integration, and network error handling
- **Browser Automation**: Web control with Playwright, screenshots, and content extraction

### 🏆 Expert Level (Example 9)
- **E-commerce Manager**: Enterprise business logic, multi-system coordination, and analytics

## 🎯 Key Learning Concepts

Each example progressively introduces new concepts:
- Tool function patterns and schemas
- Agent system prompts and personalities
- Error handling and input validation
- State management and data persistence
- Multi-tool coordination and workflows
- External API integration patterns
- Security considerations and best practices
- Business logic and enterprise workflows

## 🚀 Installation

\`\`\`bash
pip install connectonion
\`\`\`

## 📖 Usage Tips

1. **Follow the Order**: Examples build on each other - start with #1
2. **Complete Code**: Every example is fully functional and ready to run
3. **Modify & Experiment**: Use as starting points for your own agents
4. **Realistic Scenarios**: All examples use real-world data and use cases

## 🔗 Related Resources

- [System Prompts](/prompts) - Craft perfect agent personalities
- [Debugging with @xray](/xray) - Master agent development workflows
- [Quick Start Guide](/quickstart) - Hands-on ConnectOnion tutorial

---

*All examples use ConnectOnion v0.0.1b5 with complete working code and realistic outputs.*`

  return (
    <div className="max-w-7xl mx-auto px-4 md:px-8 py-8 md:py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Compact Header */}
      <div className="flex flex-col lg:flex-row lg:items-start gap-8 mb-12">
        <div className="flex-1">
          <nav className="flex items-center gap-2 text-sm text-gray-400 mb-3">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <ArrowRight className="w-4 h-4" />
            <span className="text-white">Agent Building</span>
          </nav>

          <h1 className="text-4xl font-bold text-white mb-3">Agent Building Examples</h1>
          <p className="text-lg text-gray-300 leading-relaxed">
            Master ConnectOnion through 8 progressive examples, from simple "Hello World" to enterprise-grade business applications. 
            Each example introduces new concepts with complete working code and realistic outputs.
          </p>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="connectonion-agent-examples.md"
          className="flex-shrink-0"
        />
      </div>

      {/* Compact Learning Path Overview */}
      <div className="mb-12 p-6 bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-500/30 rounded-lg">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          📚 <span>Progressive Learning Path</span>
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-2 bg-green-600 rounded-lg flex items-center justify-center">
              <span className="text-sm font-bold text-white">1-3</span>
            </div>
            <h3 className="text-sm font-semibold text-white mb-1">Beginner</h3>
            <p className="text-green-200 text-xs">Basic concepts, single tools</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-2 bg-yellow-600 rounded-lg flex items-center justify-center">
              <span className="text-sm font-bold text-white">4-5</span>
            </div>
            <h3 className="text-sm font-semibold text-white mb-1">Intermediate</h3>
            <p className="text-yellow-200 text-xs">State management, workflows</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-2 bg-orange-600 rounded-lg flex items-center justify-center">
              <span className="text-sm font-bold text-white">6-7</span>
            </div>
            <h3 className="text-sm font-semibold text-white mb-1">Advanced</h3>
            <p className="text-orange-200 text-xs">System integration, APIs</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-2 bg-red-600 rounded-lg flex items-center justify-center">
              <span className="text-sm font-bold text-white">8</span>
            </div>
            <h3 className="text-sm font-semibold text-white mb-1">Expert</h3>
            <p className="text-red-200 text-xs">Enterprise business logic</p>
          </div>
        </div>
      </div>

      {/* Examples - Improved Vertical Layout */}
      <div className="space-y-8 mb-16">
        {examples.map((example, index) => {
          const IconComponent = example.icon
          return (
            <section key={example.id} className={`${example.bgColor} ${example.borderColor} border rounded-lg p-6 hover:border-opacity-60 transition-all`}>
              {/* Compact Header */}
              <div className="flex flex-col lg:flex-row lg:items-start gap-6 mb-6">
                <div className="flex items-start gap-4 flex-1">
                  <div className={`w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 ${
                    example.difficulty === 'Beginner' ? 'bg-green-600' :
                    example.difficulty === 'Intermediate' ? 'bg-yellow-600' :
                    example.difficulty === 'Advanced' ? 'bg-orange-600' : 'bg-red-600'
                  }`}>
                    <span className="text-lg font-bold text-white">{index + 1}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <IconComponent className={`w-5 h-5 ${example.color} flex-shrink-0`} />
                      <h2 className="text-xl font-bold text-white">{example.title}</h2>
                      <span className={`px-2 py-1 rounded-md text-xs font-medium ${
                        example.difficulty === 'Beginner' ? 'bg-green-900/50 text-green-300' :
                        example.difficulty === 'Intermediate' ? 'bg-yellow-900/50 text-yellow-300' :
                        example.difficulty === 'Advanced' ? 'bg-orange-900/50 text-orange-300' : 'bg-red-900/50 text-red-300'
                      }`}>
                        {example.difficulty}
                      </span>
                    </div>
                    <p className="text-gray-300 mb-3 text-sm leading-relaxed">{example.description}</p>
                    
                    {/* Compact Key Concepts */}
                    <div className="flex flex-wrap gap-1">
                      {example.concepts.map((concept, idx) => (
                        <span key={idx} className="px-2 py-1 bg-gray-800/50 text-gray-400 text-xs rounded border border-gray-700/50">
                          {concept}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
                
                <Link 
                  href={example.href}
                  className="flex items-center justify-center gap-2 px-4 py-3 md:py-2 bg-gray-800/50 hover:bg-gray-800 border border-gray-600/50 hover:border-gray-500 rounded-md text-gray-300 hover:text-white transition-all text-sm font-medium min-w-[140px]"
                >
                  <span>View Tutorial</span>
                  <ExternalLink className="w-4 h-4" />
                </Link>
              </div>

              {/* Compact Code Preview - Hidden on mobile */}
              <div className="hidden md:block bg-gray-900/80 border border-gray-700/60 rounded-md overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 bg-gray-800/60 border-b border-gray-700/60">
                  <div className="flex items-center gap-2">
                    <Code className="w-4 h-4 text-gray-400" />
                    <span className="text-xs font-medium text-gray-400">Code Preview</span>
                  </div>
                  <button
                    onClick={() => copyToClipboard(example.preview, example.id)}
                    className="text-gray-400 hover:text-white transition-colors p-1.5 rounded hover:bg-gray-700/60 flex items-center gap-1.5"
                  >
                    {copiedId === example.id ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-green-400" />
                        <span className="text-green-400 text-xs">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span className="text-xs">Copy</span>
                      </>
                    )}
                  </button>
                </div>
                
                <div className="p-4">
                  <SyntaxHighlighter 
                    language="python" 
                    style={monokai}
                    customStyle={{
                      background: 'transparent',
                      padding: 0,
                      margin: 0,
                      fontSize: '0.8rem',
                      lineHeight: '1.5'
                    }}
                    showLineNumbers={true}
                    lineNumberStyle={{ 
                      color: '#6b7280', 
                      paddingRight: '0.8rem',
                      userSelect: 'none',
                      fontSize: '0.75rem'
                    }}
                  >
                    {example.preview}
                  </SyntaxHighlighter>
                </div>
              </div>

              {/* Simple Progress Indicator */}
              {index < examples.length - 1 && (
                <div className="flex justify-center mt-6">
                  <div className="w-8 h-0.5 bg-gray-600 rounded-full"></div>
                </div>
              )}
            </section>
          )
        })}
      </div>

      {/* Next Steps */}
      <div className="p-8 bg-gradient-to-r from-purple-900/20 to-pink-900/20 border border-purple-500/30 rounded-xl">
        <h2 className="text-2xl font-bold text-white mb-6">🎯 What's Next?</h2>
        <p className="text-gray-300 mb-6">
          Ready to take your ConnectOnion skills to the next level? Here are some great next steps:
        </p>
        <div className="grid md:grid-cols-2 gap-6">
          <Link 
            href="/prompts" 
            className="group bg-purple-900/20 border border-purple-500/30 rounded-lg p-6 hover:border-purple-400/50 transition-all"
          >
            <div className="flex items-center gap-3 mb-3">
              <FileText className="w-6 h-6 text-purple-400" />
              <h3 className="text-lg font-semibold text-white">System Prompts</h3>
              <ArrowRight className="w-4 h-4 text-purple-400 group-hover:translate-x-1 transition-transform" />
            </div>
            <p className="text-purple-100 text-sm">
              Learn to craft perfect agent personalities and behaviors with advanced prompting techniques.
            </p>
          </Link>

          <Link 
            href="/xray" 
            className="group bg-blue-900/20 border border-blue-500/30 rounded-lg p-6 hover:border-blue-400/50 transition-all"
          >
            <div className="flex items-center gap-3 mb-3">
              <Terminal className="w-6 h-6 text-blue-400" />
              <h3 className="text-lg font-semibold text-white">@xray Debugging</h3>
              <ArrowRight className="w-4 h-4 text-blue-400 group-hover:translate-x-1 transition-transform" />
            </div>
            <p className="text-blue-100 text-sm">
              Master debugging techniques and get complete visibility into your agent's decision-making process.
            </p>
          </Link>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-8 border-t border-gray-800 mt-16">
        <Link 
          href="/xray/trace" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <ArrowRight className="w-4 h-4 rotate-180" />
          trace() Visual Flow
        </Link>
        <Link 
          href="/quickstart" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          Quick Start Guide
          <ArrowRight className="w-4 h-4" />
        </Link>
      </nav>
      
      {/* Navigation */}
      <ContentNavigation />
    </div>
  )
}