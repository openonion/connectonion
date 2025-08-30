'use client'

import React from 'react'
import { ArrowRight, User, Code, Database, FileText, Shield, TrendingUp } from 'lucide-react'
import Link from 'next/link'

const examples = [
  {
    id: 'friendly-assistant',
    title: '1. Friendly Assistant',
    description: 'Basic conversational agent with helpful personality',
    icon: User,
    color: 'text-green-400',
    bg: 'bg-green-900/20 border-green-500/30',
    difficulty: 'Beginner',
    concepts: ['Basic personality', 'Conversational tone', 'Helpful behavior'],
    href: '/prompts/examples/friendly-assistant'
  },
  {
    id: 'math-tutor',
    title: '2. Math Tutor',
    description: 'Patient teacher focused on step-by-step explanations',
    icon: Code,
    color: 'text-blue-400', 
    bg: 'bg-blue-900/20 border-blue-500/30',
    difficulty: 'Beginner',
    concepts: ['Educational approach', 'Structured teaching', 'Encouraging feedback'],
    href: '/prompts/examples/math-tutor'
  },
  {
    id: 'customer-support',
    title: '3. Customer Support Agent',
    description: 'Empathetic support specialist with structured problem-solving',
    icon: User,
    color: 'text-orange-400',
    bg: 'bg-orange-900/20 border-orange-500/30',
    difficulty: 'Intermediate',
    concepts: ['Empathy framework', 'Solution-oriented', 'Escalation triggers'],
    href: '/prompts/examples/customer-support'
  },
  {
    id: 'code-reviewer',
    title: '4. Senior Code Reviewer',
    description: 'Expert engineer with systematic review methodology',
    icon: Code,
    color: 'text-purple-400',
    bg: 'bg-purple-900/20 border-purple-500/30',
    difficulty: 'Advanced',
    concepts: ['Review frameworks', 'Technical expertise', 'Constructive feedback'],
    href: '/prompts/examples/code-reviewer'
  },
  {
    id: 'data-analyst',
    title: '5. Data Analysis Expert',
    description: 'Expert transforming data into actionable insights',
    icon: Database,
    color: 'text-cyan-400',
    bg: 'bg-cyan-900/20 border-cyan-500/30',
    difficulty: 'Advanced',
    concepts: ['Statistical rigor', 'Business context', 'Visual clarity'],
    href: '/prompts/examples/data-analyst'
  },
  {
    id: 'technical-writer',
    title: '6. Technical Documentation Specialist',
    description: 'Creating clear, comprehensive technical documentation',
    icon: FileText,
    color: 'text-indigo-400',
    bg: 'bg-indigo-900/20 border-indigo-500/30',
    difficulty: 'Expert',
    concepts: ['Progressive disclosure', 'User-centered writing', 'Documentation types'],
    href: '/prompts/examples/technical-writer'
  },
  {
    id: 'security-analyst',
    title: '7. Security Analyst',
    description: 'Cybersecurity expert conducting threat analysis and risk assessment',
    icon: Shield,
    color: 'text-red-400',
    bg: 'bg-red-900/20 border-red-500/30',
    difficulty: 'Expert',
    concepts: ['Threat intelligence', 'Risk frameworks', 'Compliance protocols'],
    href: '/prompts/examples/security-analyst'
  },
  {
    id: 'business-strategist',
    title: '8. Business Strategist',
    description: 'Strategic business advisor for complex decision-making and planning',
    icon: TrendingUp,
    color: 'text-pink-400',
    bg: 'bg-pink-900/20 border-pink-500/30',
    difficulty: 'Expert',
    concepts: ['Market analysis', 'Strategic frameworks', 'Financial modeling'],
    href: '/prompts/examples/business-strategist'
  }
]

export default function PromptsExamplesPage() {
  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/prompts" className="hover:text-white transition-colors">System Prompts</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">Examples</span>
      </nav>

      {/* Header */}
      <div className="mb-16">
        <h1 className="text-4xl font-bold text-white mb-4">Progressive Prompt Examples</h1>
        <p className="text-xl text-gray-300 max-w-3xl">
          Master system prompt design through 8 carefully crafted examples, progressing from simple conversational agents 
          to complex professional roles. Each example demonstrates advanced techniques and real-world applications.
        </p>
      </div>

      {/* Learning Path Overview */}
      <div className="mb-16 p-8 bg-gradient-to-r from-green-900/20 to-red-900/20 border border-green-500/30 rounded-xl">
        <h2 className="text-2xl font-bold text-white mb-6">🎯 Prompt Design Learning Path</h2>
        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-4 bg-green-600 rounded-full flex items-center justify-center">
              <span className="text-2xl font-bold text-white">🟢</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Beginner</h3>
            <p className="text-green-200 text-sm">Basic personality and conversation patterns</p>
            <p className="text-green-300 text-xs mt-2">Examples 1-2</p>
          </div>
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-4 bg-yellow-600 rounded-full flex items-center justify-center">
              <span className="text-2xl font-bold text-white">🟡</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Intermediate</h3>
            <p className="text-yellow-200 text-sm">Structured responses and domain knowledge</p>
            <p className="text-yellow-300 text-xs mt-2">Example 3</p>
          </div>
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-4 bg-orange-600 rounded-full flex items-center justify-center">
              <span className="text-2xl font-bold text-white">🟠</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Advanced</h3>
            <p className="text-orange-200 text-sm">Professional frameworks and methodologies</p>
            <p className="text-orange-300 text-xs mt-2">Examples 4-5</p>
          </div>
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-4 bg-red-600 rounded-full flex items-center justify-center">
              <span className="text-2xl font-bold text-white">🔴</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Expert</h3>
            <p className="text-red-200 text-sm">Complex decision frameworks and strategic thinking</p>
            <p className="text-red-300 text-xs mt-2">Examples 6-8</p>
          </div>
        </div>
      </div>

      {/* Examples Grid */}
      <div className="grid md:grid-cols-2 gap-8">
        {examples.map((example, index) => {
          const IconComponent = example.icon
          return (
            <Link 
              key={example.id}
              href={example.href}
              className={`group ${example.bg} border rounded-xl p-8 hover:border-opacity-100 transition-all duration-300 hover:scale-[1.02] hover:shadow-lg`}
            >
              <div className="flex items-start gap-6">
                {/* Number Badge */}
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold text-lg flex-shrink-0 ${
                  example.difficulty === 'Beginner' ? 'bg-green-600' : 
                  example.difficulty === 'Intermediate' ? 'bg-yellow-600' : 
                  example.difficulty === 'Advanced' ? 'bg-orange-600' : 'bg-red-600'
                }`}>
                  {index + 1}
                </div>

                <div className="flex-1 min-w-0">
                  {/* Header */}
                  <div className="flex items-center gap-3 mb-3">
                    <IconComponent className={`w-6 h-6 ${example.color}`} />
                    <h3 className="text-xl font-bold text-white group-hover:text-white/90">
                      {example.title}
                    </h3>
                    <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                      example.difficulty === 'Beginner' ? 'bg-green-900/50 text-green-300' :
                      example.difficulty === 'Intermediate' ? 'bg-yellow-900/50 text-yellow-300' :
                      example.difficulty === 'Advanced' ? 'bg-orange-900/50 text-orange-300' : 'bg-red-900/50 text-red-300'
                    }`}>
                      {example.difficulty}
                    </span>
                  </div>

                  {/* Description */}
                  <p className="text-gray-300 mb-4 text-sm leading-relaxed">
                    {example.description}
                  </p>

                  {/* Key Concepts */}
                  <div className="space-y-2">
                    <p className="text-gray-400 text-xs font-medium uppercase tracking-wide">Key Concepts</p>
                    <div className="flex flex-wrap gap-2">
                      {example.concepts.map((concept) => (
                        <span 
                          key={concept}
                          className="px-2 py-1 bg-gray-800 text-gray-300 rounded text-xs"
                        >
                          {concept}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Arrow */}
                  <div className="flex items-center justify-end mt-4">
                    <ArrowRight className={`w-5 h-5 ${example.color} group-hover:translate-x-1 transition-transform`} />
                  </div>
                </div>
              </div>
            </Link>
          )
        })}
      </div>

      {/* Why Progressive Learning */}
      <div className="mt-16 p-8 bg-gradient-to-r from-purple-900/20 to-blue-900/20 border border-purple-500/30 rounded-xl">
        <h2 className="text-2xl font-bold text-white mb-6">💡 Why Progressive Learning?</h2>
        <div className="grid md:grid-cols-2 gap-8">
          <div>
            <h3 className="text-lg font-semibold text-white mb-3">Building Complexity</h3>
            <p className="text-gray-300 text-sm leading-relaxed">
              Each example introduces new prompt engineering concepts while building on previous knowledge. 
              Start with basic personality definition, then add structured responses, professional frameworks, and finally complex decision-making processes.
            </p>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white mb-3">Real-World Applications</h3>
            <p className="text-gray-300 text-sm leading-relaxed">
              Every prompt is designed for actual business use cases. From customer support to security analysis, 
              these examples solve real problems and can be immediately deployed in production environments.
            </p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <Link 
          href="/prompts" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <ArrowRight className="w-4 h-4 rotate-180" />
          System Prompts
        </Link>
        <Link 
          href="/prompts/formats" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          Prompt Formats
          <ArrowRight className="w-4 h-4" />
        </Link>
      </nav>
    </div>
  )
}