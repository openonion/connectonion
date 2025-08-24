'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Rocket, Package, Network, Shield, Brain, Zap, Cloud, Lock, AlertCircle, CheckCircle2, Clock, Star, TrendingUp } from 'lucide-react'

export default function RoadmapPage() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  const categories = [
    { id: 'core', name: 'Core Features', icon: Package, color: 'from-purple-600 to-pink-600' },
    { id: 'trust', name: 'Trust & Security', icon: Shield, color: 'from-blue-600 to-cyan-600' },
    { id: 'intelligence', name: 'Intelligence', icon: Brain, color: 'from-green-600 to-emerald-600' },
    { id: 'platform', name: 'Platform', icon: Network, color: 'from-orange-600 to-red-600' },
  ]

  const features = {
    core: [
      {
        title: 'Share & Find Functions',
        status: 'in-progress',
        description: 'Share functions with one line of code, find them with natural language',
        targetDate: 'Q1 2025',
        progress: 65,
        details: [
          'One-line function sharing',
          'Natural language discovery',
          'Automatic documentation',
          'Type inference and validation'
        ]
      },
      {
        title: 'Agent-to-Agent Protocol',
        status: 'planned',
        description: 'Enable agents to communicate and collaborate seamlessly',
        targetDate: 'Q2 2025',
        progress: 10,
        details: [
          'Standardized communication protocol',
          'Message routing and discovery',
          'Capability negotiation',
          'Result aggregation'
        ]
      },
      {
        title: 'Visual Agent Builder',
        status: 'planned',
        description: 'Drag-and-drop interface for creating complex agent workflows',
        targetDate: 'Q3 2025',
        progress: 0,
        details: [
          'Visual workflow editor',
          'Pre-built component library',
          'Real-time debugging',
          'Export to code'
        ]
      }
    ],
    trust: [
      {
        title: 'Test Before Trust',
        status: 'in-progress',
        description: 'Sandbox environment for safely testing functions before deployment',
        targetDate: 'Q1 2025',
        progress: 40,
        details: [
          'Isolated execution environment',
          'Resource monitoring',
          'Automatic rollback on failure',
          'Trust scoring system'
        ]
      },
      {
        title: 'Agent Authentication',
        status: 'planned',
        description: 'Cryptographic identity and verification for agents',
        targetDate: 'Q2 2025',
        progress: 5,
        details: [
          'Public key infrastructure',
          'Capability-based access control',
          'Audit logging',
          'Reputation system'
        ]
      },
      {
        title: 'End-to-End Encryption',
        status: 'planned',
        description: 'Secure communication between agents and functions',
        targetDate: 'Q3 2025',
        progress: 0,
        details: [
          'TLS for all communications',
          'Key management service',
          'Secret rotation',
          'Compliance certifications'
        ]
      }
    ],
    intelligence: [
      {
        title: 'Memory & Experience System',
        status: 'in-progress',
        description: 'Agents learn from past interactions and improve over time',
        targetDate: 'Q1 2025',
        progress: 30,
        details: [
          'Long-term memory storage',
          'Experience replay',
          'Pattern recognition',
          'Performance optimization'
        ]
      },
      {
        title: 'Multi-Model Support',
        status: 'planned',
        description: 'Support for various LLM providers beyond OpenAI',
        targetDate: 'Q2 2025',
        progress: 15,
        details: [
          'Anthropic Claude integration',
          'Google Gemini support',
          'Local model hosting',
          'Custom model adapters'
        ]
      },
      {
        title: 'Intelligent Routing',
        status: 'planned',
        description: 'Smart routing of requests to optimal models and functions',
        targetDate: 'Q3 2025',
        progress: 0,
        details: [
          'Cost optimization',
          'Latency-based routing',
          'Load balancing',
          'Fallback strategies'
        ]
      }
    ],
    platform: [
      {
        title: 'Cloud Agent Hosting',
        status: 'planned',
        description: 'Deploy and manage agents in the cloud with one command',
        targetDate: 'Q2 2025',
        progress: 20,
        details: [
          'One-click deployment',
          'Auto-scaling',
          'Monitoring dashboard',
          'Cost analytics'
        ]
      },
      {
        title: 'Agent Marketplace',
        status: 'planned',
        description: 'Discover, share, and monetize agent components',
        targetDate: 'Q3 2025',
        progress: 0,
        details: [
          'Component registry',
          'Version management',
          'License management',
          'Revenue sharing'
        ]
      },
      {
        title: 'Enterprise Features',
        status: 'planned',
        description: 'Advanced features for large-scale deployments',
        targetDate: 'Q4 2025',
        progress: 0,
        details: [
          'SSO integration',
          'Role-based access control',
          'Compliance reporting',
          'SLA guarantees'
        ]
      }
    ]
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-green-400" />
      case 'in-progress':
        return <Clock className="w-5 h-5 text-yellow-400 animate-pulse" />
      case 'planned':
        return <AlertCircle className="w-5 h-5 text-gray-400" />
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

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 via-purple-900/20 to-gray-900">
      <div className="max-w-6xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-12">
          <Link 
            href="/" 
            className="inline-flex items-center gap-2 text-gray-400 hover:text-white transition-colors mb-8"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Docs
          </Link>
          
          <div className="flex items-center gap-4 mb-6">
            <Rocket className="w-10 h-10 text-purple-400" />
            <div>
              <h1 className="text-4xl font-bold text-white flex items-center gap-3">
                Roadmap
                <span className="px-3 py-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm font-semibold rounded-full">
                  COMING SOON
                </span>
              </h1>
              <p className="text-gray-400 mt-2">Our vision for the future of ConnectOnion</p>
            </div>
          </div>
        </div>

        {/* Timeline Overview */}
        <div className="mb-12 p-6 bg-gray-800/50 rounded-xl border border-gray-700">
          <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-purple-400" />
            Release Timeline
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-400">Q1 2025</div>
              <div className="text-sm text-gray-400 mt-1">Core Features</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-400">Q2 2025</div>
              <div className="text-sm text-gray-400 mt-1">Trust & Protocol</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-400">Q3 2025</div>
              <div className="text-sm text-gray-400 mt-1">Platform Launch</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-orange-400">Q4 2025</div>
              <div className="text-sm text-gray-400 mt-1">Enterprise</div>
            </div>
          </div>
        </div>

        {/* Category Tabs */}
        <div className="flex flex-wrap gap-4 mb-8">
          {categories.map((category) => {
            const Icon = category.icon
            return (
              <button
                key={category.id}
                onClick={() => setSelectedCategory(selectedCategory === category.id ? null : category.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                  selectedCategory === category.id
                    ? `bg-gradient-to-r ${category.color} text-white`
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                <Icon className="w-5 h-5" />
                {category.name}
              </button>
            )
          })}
        </div>

        {/* Features Grid */}
        <div className="space-y-6">
          {(selectedCategory ? [selectedCategory] : Object.keys(features)).map((categoryId) => (
            <div key={categoryId} className="space-y-4">
              <h3 className="text-2xl font-semibold text-white capitalize flex items-center gap-2">
                {categories.find(c => c.id === categoryId)?.icon && (
                  <span className={`p-2 rounded-lg bg-gradient-to-r ${categories.find(c => c.id === categoryId)?.color}`}>
                    {(() => {
                      const Icon = categories.find(c => c.id === categoryId)?.icon
                      return Icon ? <Icon className="w-5 h-5" /> : null
                    })()}
                  </span>
                )}
                {categories.find(c => c.id === categoryId)?.name}
              </h3>
              
              <div className="grid gap-4">
                {features[categoryId as keyof typeof features].map((feature, index) => (
                  <div
                    key={index}
                    className="bg-gray-800/50 rounded-xl border border-gray-700 p-6 hover:border-purple-500/50 transition-all"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex items-start gap-3">
                        {getStatusIcon(feature.status)}
                        <div>
                          <h4 className="text-xl font-semibold text-white">{feature.title}</h4>
                          <p className="text-gray-400 mt-1">{feature.description}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm text-gray-500">Target</div>
                        <div className="text-sm font-semibold text-purple-400">{feature.targetDate}</div>
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="mb-4">
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-400">Progress</span>
                        <span className="text-white font-semibold">{feature.progress}%</span>
                      </div>
                      <div className="w-full bg-gray-700 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full transition-all ${getStatusColor(feature.status)}`}
                          style={{ width: `${feature.progress}%` }}
                        />
                      </div>
                    </div>

                    {/* Feature Details */}
                    <div className="grid grid-cols-2 gap-2">
                      {feature.details.map((detail, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-sm text-gray-400">
                          <Star className="w-3 h-3 text-purple-400" />
                          {detail}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Call to Action */}
        <div className="mt-16 text-center p-8 bg-gradient-to-r from-purple-900/50 to-pink-900/50 rounded-xl border border-purple-500/30">
          <h2 className="text-2xl font-bold text-white mb-4">Want to Shape Our Roadmap?</h2>
          <p className="text-gray-300 mb-6 max-w-2xl mx-auto">
            We're building ConnectOnion with our community. Your feedback and contributions help prioritize features and shape the future of AI agent development.
          </p>
          <div className="flex justify-center gap-4">
            <a
              href="https://github.com/wu-changxing/connectonion/issues"
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3 bg-purple-600 text-white rounded-lg font-semibold hover:bg-purple-700 transition-colors"
            >
              Submit Feature Request
            </a>
            <a
              href="https://github.com/wu-changxing/connectonion/discussions"
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3 bg-gray-700 text-white rounded-lg font-semibold hover:bg-gray-600 transition-colors"
            >
              Join Discussion
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}