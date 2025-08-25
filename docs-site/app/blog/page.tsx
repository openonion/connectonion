'use client'

import Link from 'next/link'
import { ArrowLeft, ArrowRight, BookOpen, Calendar, Clock, Users } from 'lucide-react'

const blogPosts = [
  {
    title: 'Why We Chose "Trust"',
    subtitle: 'The Story Behind ConnectOnion\'s Authentication Keyword',
    date: 'December 2024',
    readTime: '5 min read',
    href: '/blog/trust-keyword',
    icon: Users,
    tags: ['Design Decision', 'Authentication', 'Trust'],
    excerpt: 'After evaluating 15+ options, we settled on "trust" as our authentication keyword. Learn why this bidirectional term perfectly captures our behavioral verification approach.'
  }
]

export default function BlogPage() {
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
            <BookOpen className="w-8 h-8 text-purple-400" />
            <h1 className="text-3xl font-bold text-white">Blog</h1>
          </div>
          <p className="text-gray-400">
            Design decisions and insights from building ConnectOnion
          </p>
        </div>

        {/* Blog Posts */}
        <div className="space-y-6">
          {blogPosts.map((post) => {
            const Icon = post.icon
            return (
              <Link 
                key={post.href}
                href={post.href}
                className="block group"
              >
                <article className="p-6 bg-gray-800/50 rounded-xl border border-gray-700 hover:border-purple-500/50 transition-all">
                  <div className="flex items-start gap-4">
                    {/* Icon */}
                    <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-gradient-to-br from-purple-600 to-pink-600 p-[1px]">
                      <div className="w-full h-full bg-gray-900 rounded-lg flex items-center justify-center">
                        <Icon className="w-6 h-6 text-purple-400" />
                      </div>
                    </div>
                    
                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      {/* Meta */}
                      <div className="flex flex-wrap items-center gap-3 mb-2 text-sm text-gray-500">
                        <div className="flex items-center gap-1">
                          <Calendar className="w-3.5 h-3.5" />
                          <span>{post.date}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5" />
                          <span>{post.readTime}</span>
                        </div>
                      </div>
                      
                      {/* Title */}
                      <h2 className="text-xl font-semibold text-white mb-1 group-hover:text-purple-400 transition-colors">
                        {post.title}
                      </h2>
                      
                      {/* Subtitle */}
                      <p className="text-gray-300 mb-3">
                        {post.subtitle}
                      </p>
                      
                      {/* Excerpt */}
                      <p className="text-gray-400 text-sm mb-4 line-clamp-2">
                        {post.excerpt}
                      </p>
                      
                      {/* Tags and Read More */}
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex flex-wrap gap-2">
                          {post.tags.map((tag) => (
                            <span 
                              key={tag}
                              className="px-2 py-1 bg-gray-700/50 rounded-md text-xs text-gray-300"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                        
                        <span className="inline-flex items-center gap-1 text-sm text-purple-400 group-hover:text-purple-300">
                          Read more
                          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                        </span>
                      </div>
                    </div>
                  </div>
                </article>
              </Link>
            )
          })}
        </div>

        {/* Coming Soon */}
        <div className="mt-12 p-8 bg-gray-800/30 rounded-xl border border-gray-700 text-center">
          <h3 className="text-lg font-semibold text-white mb-2">More Posts Coming Soon</h3>
          <p className="text-gray-400 text-sm">
            We're documenting our journey. Stay tuned for more insights.
          </p>
        </div>
      </div>
    </div>
  )
}