'use client'

import Link from 'next/link'
import { ArrowRight, BookOpen, Calendar, Clock, TrendingUp, Users, Code } from 'lucide-react'

const blogPosts = [
  {
    title: 'Why We Chose "Trust"',
    subtitle: 'The Story Behind ConnectOnion\'s Authentication Keyword',
    date: 'December 2024',
    readTime: '5 min read',
    href: '/blog/trust-keyword',
    icon: Users,
    gradient: 'from-purple-600 to-pink-600',
    tags: ['Design Decision', 'Authentication', 'Trust'],
    excerpt: 'After evaluating 15+ options, we settled on "trust" as our authentication keyword. Learn why this bidirectional term perfectly captures our behavioral verification approach.'
  }
]

export default function BlogPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Hero Section */}
      <div className="relative overflow-hidden bg-gradient-to-b from-purple-900/20 to-gray-950 border-b border-gray-800">
        <div className="absolute inset-0 bg-grid-white/[0.02] bg-[size:32px_32px]" />
        <div className="relative max-w-6xl mx-auto px-8 py-16">
          <div className="flex items-center gap-3 mb-4">
            <BookOpen className="w-8 h-8 text-purple-400" />
            <div className="text-sm text-purple-400 font-medium">ConnectOnion Blog</div>
          </div>
          <h1 className="text-4xl lg:text-5xl font-bold mb-4 bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
            Design Decisions & Insights
          </h1>
          <p className="text-xl text-gray-300 max-w-3xl">
            Deep dives into the design philosophy and technical decisions behind ConnectOnion
          </p>
        </div>
      </div>

      {/* Blog Posts Grid */}
      <div className="max-w-6xl mx-auto px-8 py-12">
        <div className="grid gap-8">
          {blogPosts.map((post) => {
            const Icon = post.icon
            return (
              <Link 
                key={post.href}
                href={post.href}
                className="group relative bg-gray-900 border border-gray-800 rounded-xl overflow-hidden hover:border-gray-700 transition-all"
              >
                {/* Gradient accent bar */}
                <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${post.gradient}`} />
                
                <div className="p-8">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      {/* Meta info */}
                      <div className="flex items-center gap-4 mb-4 text-sm text-gray-400">
                        <div className="flex items-center gap-1.5">
                          <Calendar className="w-4 h-4" />
                          <span>{post.date}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Clock className="w-4 h-4" />
                          <span>{post.readTime}</span>
                        </div>
                      </div>

                      {/* Title & Subtitle */}
                      <h2 className="text-2xl font-bold text-white mb-2 group-hover:text-purple-400 transition-colors">
                        {post.title}
                      </h2>
                      <p className="text-lg text-gray-300 mb-4">
                        {post.subtitle}
                      </p>

                      {/* Excerpt */}
                      <p className="text-gray-400 mb-6 leading-relaxed">
                        {post.excerpt}
                      </p>

                      {/* Tags */}
                      <div className="flex items-center gap-2 mb-6">
                        {post.tags.map((tag) => (
                          <span 
                            key={tag}
                            className="px-3 py-1 bg-gray-800 border border-gray-700 rounded-full text-xs text-gray-300"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>

                      {/* Read more */}
                      <div className="flex items-center gap-2 text-purple-400 group-hover:text-purple-300 transition-colors">
                        <span className="font-medium">Read full article</span>
                        <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                      </div>
                    </div>

                    {/* Icon */}
                    <div className={`w-16 h-16 rounded-xl bg-gradient-to-br ${post.gradient} p-0.5 flex-shrink-0`}>
                      <div className="w-full h-full bg-gray-900 rounded-xl flex items-center justify-center">
                        <Icon className="w-8 h-8 text-purple-400" />
                      </div>
                    </div>
                  </div>
                </div>
              </Link>
            )
          })}
        </div>

        {/* Coming Soon Section */}
        <div className="mt-16 p-8 bg-gray-900/50 border border-gray-800 rounded-xl text-center">
          <TrendingUp className="w-12 h-12 text-purple-400 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-white mb-2">More Insights Coming Soon</h3>
          <p className="text-gray-400 max-w-2xl mx-auto">
            We're documenting our journey building the simplest agent framework. 
            Stay tuned for more deep dives into our design decisions and technical architecture.
          </p>
        </div>
      </div>
    </div>
  )
}