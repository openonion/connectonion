/*
  @date: 2025-01-01
  @description: Roadmap Page
  
  DESIGN ISSUES TO FIX:
  
  1. **Timeline Visualization** (Priority: HIGH)
     - No visual timeline or gantt chart view
     - Quarters shown as text instead of visual timeline
     - Progress bars disconnected from time context
     - Fix: Add horizontal timeline view, show dependencies, visualize time progression
  
  2. **Feature Status Clarity** (Priority: HIGH)
     - Status icons too small and similar colors
     - Progress percentages arbitrary without context
     - No indication of blockers or dependencies
     - Fix: Larger status badges, explain progress metrics, show dependencies
  
  3. **Filtering UX** (Priority: MEDIUM)
     - Category filters reset scroll position
     - No indication of how many items in each filter
     - Selected filter state not persistent
     - Fix: Maintain scroll, show counts, remember filter selection
  
  4. **Mobile Experience** (Priority: MEDIUM)
     - Feature cards too dense on mobile
     - Progress bars too thin for touch
     - CTA buttons stack poorly
     - Fix: Simplify mobile cards, increase touch targets, responsive CTA layout
  
  5. **User Engagement** (Priority: LOW)
     - No voting or feedback mechanism
     - Missing "notify me" for features
     - Static content without updates indicator
     - Fix: Add voting buttons, email notifications, "last updated" timestamp
*/

'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Rocket, Package, Network, Shield, Brain, CheckCircle2, Clock, AlertCircle } from 'lucide-react'
import { ContentNavigation } from '../../components/ContentNavigation'

export default function RoadmapPage() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  const categories = [
    { id: 'core', name: 'Core', icon: Package },
    { id: 'trust', name: 'Trust', icon: Shield },
    { id: 'intelligence', name: 'AI', icon: Brain },
    { id: 'platform', name: 'Platform', icon: Network },
  ]

  const features = {
    core: [
      {
        title: 'Basic Agent Framework',
        status: 'completed',
        description: 'Simple Python framework with tool system',
        targetDate: 'Jan 2025',
        progress: 100,
      },
      {
        title: 'CLI Tool (co)',
        status: 'completed',
        description: 'Initialize and manage agent projects',
        targetDate: 'Feb 2025',
        progress: 100,
      },
      {
        title: 'Browser Agent',
        status: 'completed',
        description: 'Stateful web navigation and scraping',
        targetDate: 'Aug 2025',
        progress: 100,
      },
      {
        title: 'Advanced Tool System',
        status: 'in-progress',
        description: 'Enhanced tool composition and chaining',
        targetDate: 'Oct 2025',
        progress: 35,
      },
      {
        title: 'Agent-to-Agent Protocol',
        status: 'planned',
        description: 'Enable agents to collaborate seamlessly',
        targetDate: 'Dec 2025',
        progress: 0,
      }
    ],
    trust: [
      {
        title: 'Behavior Tracking',
        status: 'completed',
        description: 'Automatic recording of all agent actions',
        targetDate: 'Mar 2025',
        progress: 100,
      },
      {
        title: 'Function Validation',
        status: 'in-progress',
        description: 'Type checking and parameter validation',
        targetDate: 'Sep 2025',
        progress: 70,
      },
      {
        title: 'Sandbox Mode',
        status: 'planned',
        description: 'Test agents safely before deployment',
        targetDate: 'Nov 2025',
        progress: 15,
      },
      {
        title: 'Audit Logs',
        status: 'planned',
        description: 'Comprehensive action history and rollback',
        targetDate: 'Jan 2026',
        progress: 0,
      }
    ],
    intelligence: [
      {
        title: 'OpenAI Integration',
        status: 'completed',
        description: 'Full GPT-4 function calling support',
        targetDate: 'Jan 2025',
        progress: 100,
      },
      {
        title: 'Multi-Model Support',
        status: 'in-progress',
        description: 'Claude, Gemini, and Mistral integration',
        targetDate: 'Oct 2025',
        progress: 25,
      },
      {
        title: 'Context Management',
        status: 'planned',
        description: 'Smart conversation memory and retrieval',
        targetDate: 'Nov 2025',
        progress: 10,
      },
      {
        title: 'Local Model Support',
        status: 'planned',
        description: 'Run Llama, Mistral locally via Ollama',
        targetDate: 'Feb 2026',
        progress: 0,
      }
    ],
    platform: [
      {
        title: 'PyPI Package',
        status: 'completed',
        description: 'pip install connectonion',
        targetDate: 'Feb 2025',
        progress: 100,
      },
      {
        title: 'Documentation Site',
        status: 'completed',
        description: 'Comprehensive docs at docs.connectonion.com',
        targetDate: 'Jul 2025',
        progress: 100,
      },
      {
        title: 'Example Library',
        status: 'in-progress',
        description: 'Real-world agent examples and templates',
        targetDate: 'Sep 2025',
        progress: 60,
      },
      {
        title: 'VS Code Extension',
        status: 'planned',
        description: 'Agent development and debugging tools',
        targetDate: 'Dec 2025',
        progress: 5,
      },
      {
        title: 'Agent Registry',
        status: 'planned',
        description: 'Share and discover community agents',
        targetDate: 'Mar 2026',
        progress: 0,
      }
    ]
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-green-400" />
      case 'in-progress':
        return <Clock className="w-4 h-4 text-yellow-400" />
      case 'planned':
        return <AlertCircle className="w-4 h-4 text-gray-400" />
      default:
        return null
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-500'
      case 'in-progress':
        return 'bg-yellow-500'
      case 'planned':
        return 'bg-gray-600'
      default:
        return 'bg-gray-700'
    }
  }

  const displayedFeatures = selectedCategory 
    ? { [selectedCategory]: features[selectedCategory as keyof typeof features] }
    : features

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 via-purple-900/10 to-gray-900">
      <div className="max-w-4xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-12">
          <Link 
            href="/" 
            className="inline-flex items-center gap-2 text-gray-400 hover:text-white transition-colors mb-8"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Docs
          </Link>
          
          <div className="flex items-center gap-3 mb-4">
            <Rocket className="w-8 h-8 text-purple-400" />
            <h1 className="text-3xl font-bold text-white">
              Roadmap
            </h1>
            <span className="px-2 py-1 bg-gradient-to-r from-green-600 to-emerald-600 text-white text-xs font-semibold rounded-full">
              v0.0.5
            </span>
          </div>
          <p className="text-gray-400">
            Track our progress from v0.0.1 to v1.0 and beyond
          </p>
        </div>

        {/* Category Filters */}
        <div className="flex flex-wrap gap-2 mb-8">
          <button
            onClick={() => setSelectedCategory(null)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
              !selectedCategory 
                ? 'bg-purple-600 text-white' 
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            All
          </button>
          {categories.map((category) => {
            const Icon = category.icon
            return (
              <button
                key={category.id}
                onClick={() => setSelectedCategory(category.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  selectedCategory === category.id
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                <Icon className="w-4 h-4" />
                {category.name}
              </button>
            )
          })}
        </div>

        {/* Features List */}
        <div className="space-y-8">
          {Object.entries(displayedFeatures).map(([categoryId, categoryFeatures]) => {
            const category = categories.find(c => c.id === categoryId)
            if (!category) return null
            
            return (
              <div key={categoryId}>
                {/* Category Header */}
                {!selectedCategory && (
                  <div className="flex items-center gap-2 mb-4">
                    <category.icon className="w-5 h-5 text-purple-400" />
                    <h2 className="text-lg font-semibold text-white">{category.name} Features</h2>
                  </div>
                )}
                
                {/* Features */}
                <div className="space-y-4">
                  {categoryFeatures.map((feature, index) => (
                    <div
                      key={index}
                      className="p-4 md:p-5 bg-gray-800/50 rounded-xl border border-gray-700 hover:border-purple-500/30 transition-all"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 mb-3">
                        <div className="flex items-start gap-3">
                          {getStatusIcon(feature.status)}
                          <div className="flex-1 min-w-0">
                            <h3 className="text-white font-medium mb-1 break-words">{feature.title}</h3>
                            <p className="text-gray-400 text-sm break-words">{feature.description}</p>
                          </div>
                        </div>
                        <span className="text-xs text-purple-400 font-medium whitespace-nowrap ml-7 sm:ml-0">{feature.targetDate}</span>
                      </div>

                      {/* Progress Bar - Larger touch target on mobile */}
                      <div className="mt-3">
                        <div className="flex justify-between text-xs mb-2">
                          <span className="text-gray-500">Progress</span>
                          <span className="text-gray-400">{feature.progress}%</span>
                        </div>
                        <div className="w-full bg-gray-700 rounded-full h-2 md:h-1.5">
                          <div
                            className={`h-2 md:h-1.5 rounded-full transition-all ${getStatusColor(feature.status)}`}
                            style={{ width: `${feature.progress}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        {/* Progress Summary */}
        <div className="mt-12 p-4 bg-gray-800/50 rounded-xl border border-gray-700">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-green-400">8</div>
              <div className="text-xs text-gray-400">Completed</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-yellow-400">5</div>
              <div className="text-xs text-gray-400">In Progress</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-gray-400">7</div>
              <div className="text-xs text-gray-400">Planned</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-purple-400">Sep 2025</div>
              <div className="text-xs text-gray-400">Current Month</div>
            </div>
          </div>
        </div>

        {/* Call to Action */}
        <div className="mt-8 p-6 md:p-8 bg-gray-800/30 rounded-xl border border-gray-700 text-center">
          <h2 className="text-lg font-semibold text-white mb-3">Want to Shape Our Roadmap?</h2>
          <p className="text-gray-400 text-sm mb-6 max-w-xl mx-auto">
            We're building ConnectOnion with our community. Your feedback helps prioritize features.
          </p>
          <div className="flex flex-col sm:flex-row justify-center gap-3 max-w-md mx-auto">
            <a
              href="https://github.com/wu-changxing/connectonion/issues"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors"
            >
              Request Feature
            </a>
            <a
              href="https://discord.gg/4xfD9k8AUF"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-600 transition-colors"
            >
              Join Discord
            </a>
          </div>
        </div>
        
        {/* Navigation */}
        <ContentNavigation />
      </div>
    </div>
  )
}