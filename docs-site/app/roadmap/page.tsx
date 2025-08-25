'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Rocket, Package, Network, Shield, Brain, CheckCircle2, Clock, AlertCircle } from 'lucide-react'

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
        title: 'Share & Find Functions',
        status: 'in-progress',
        description: 'One-line sharing, natural language discovery',
        targetDate: 'Q1 2025',
        progress: 65,
      },
      {
        title: 'Agent-to-Agent Protocol',
        status: 'planned',
        description: 'Seamless agent communication and collaboration',
        targetDate: 'Q2 2025',
        progress: 10,
      },
      {
        title: 'Visual Agent Builder',
        status: 'planned',
        description: 'Drag-and-drop workflow creation',
        targetDate: 'Q3 2025',
        progress: 0,
      }
    ],
    trust: [
      {
        title: 'Test Before Trust',
        status: 'in-progress',
        description: 'Sandbox testing with automatic rollback',
        targetDate: 'Q1 2025',
        progress: 40,
      },
      {
        title: 'Agent Authentication',
        status: 'planned',
        description: 'Cryptographic identity verification',
        targetDate: 'Q2 2025',
        progress: 5,
      },
      {
        title: 'End-to-End Encryption',
        status: 'planned',
        description: 'Secure agent communications',
        targetDate: 'Q3 2025',
        progress: 0,
      }
    ],
    intelligence: [
      {
        title: 'Memory System',
        status: 'in-progress',
        description: 'Learn from past interactions',
        targetDate: 'Q1 2025',
        progress: 30,
      },
      {
        title: 'Multi-Model Support',
        status: 'planned',
        description: 'Claude, Gemini, and local models',
        targetDate: 'Q2 2025',
        progress: 15,
      },
      {
        title: 'Smart Routing',
        status: 'planned',
        description: 'Optimize for cost and latency',
        targetDate: 'Q3 2025',
        progress: 0,
      }
    ],
    platform: [
      {
        title: 'Cloud Hosting',
        status: 'planned',
        description: 'One-click agent deployment',
        targetDate: 'Q2 2025',
        progress: 20,
      },
      {
        title: 'Agent Marketplace',
        status: 'planned',
        description: 'Share and monetize components',
        targetDate: 'Q3 2025',
        progress: 0,
      },
      {
        title: 'Enterprise Features',
        status: 'planned',
        description: 'SSO, RBAC, and compliance',
        targetDate: 'Q4 2025',
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
            <span className="px-2 py-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white text-xs font-semibold rounded-full">
              PREVIEW
            </span>
          </div>
          <p className="text-gray-400">
            Our vision for the future of ConnectOnion
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
                      className="p-5 bg-gray-800/50 rounded-xl border border-gray-700 hover:border-purple-500/30 transition-all"
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-start gap-3">
                          {getStatusIcon(feature.status)}
                          <div className="flex-1">
                            <h3 className="text-white font-medium mb-1">{feature.title}</h3>
                            <p className="text-gray-400 text-sm">{feature.description}</p>
                          </div>
                        </div>
                        <span className="text-xs text-purple-400 font-medium">{feature.targetDate}</span>
                      </div>

                      {/* Progress Bar */}
                      <div className="mt-3">
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-gray-500">Progress</span>
                          <span className="text-gray-400">{feature.progress}%</span>
                        </div>
                        <div className="w-full bg-gray-700 rounded-full h-1.5">
                          <div
                            className={`h-1.5 rounded-full transition-all ${getStatusColor(feature.status)}`}
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

        {/* Call to Action */}
        <div className="mt-16 p-8 bg-gray-800/30 rounded-xl border border-gray-700 text-center">
          <h2 className="text-lg font-semibold text-white mb-3">Want to Shape Our Roadmap?</h2>
          <p className="text-gray-400 text-sm mb-6 max-w-xl mx-auto">
            We're building ConnectOnion with our community. Your feedback helps prioritize features.
          </p>
          <div className="flex flex-col sm:flex-row justify-center gap-3">
            <a
              href="https://github.com/wu-changxing/connectonion/issues"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors"
            >
              Request Feature
            </a>
            <a
              href="https://github.com/wu-changxing/connectonion/discussions"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-600 transition-colors"
            >
              Join Discussion
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}