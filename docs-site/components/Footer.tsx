'use client'

import Link from 'next/link'
import { Github, Twitter, Mail, Heart, ArrowUpRight, Zap, MessageCircle } from 'lucide-react'
import { motion } from 'framer-motion'

export default function Footer() {
  return (
    <footer className="bg-gray-950 border-t border-gray-800/50">
      {/* Main Footer */}
      <div className="container mx-auto px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 lg:gap-12">
          
          {/* Brand Section */}
          <div className="lg:col-span-1 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <h3 className="text-2xl font-bold text-white">ConnectOnion</h3>
            </div>
            <p className="text-gray-300 leading-relaxed text-sm">
              Build AI agents with Python functions. No classes, no complexity.
            </p>
            
            {/* Social Links */}
            <div className="flex items-center gap-3">
              {[
                { icon: Github, href: 'https://github.com/connectonion', label: 'GitHub' },
                { icon: MessageCircle, href: 'https://discord.gg/4xfD9k8AUF', label: 'Discord' },
                { icon: Twitter, href: 'https://twitter.com/connectonion', label: 'Twitter' },
                { icon: Mail, href: 'mailto:hello@connectonion.com', label: 'Email' }
              ].map(({ icon: Icon, href, label }) => (
                <motion.a
                  key={label}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  whileHover={{ scale: 1.1, y: -2 }}
                  whileTap={{ scale: 0.95 }}
                  className="p-2 rounded-lg bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
                  aria-label={label}
                >
                  <Icon className="w-5 h-5" />
                </motion.a>
              ))}
            </div>
          </div>

          {/* Product Links */}
          <div className="space-y-4">
            <h4 className="text-white font-bold text-lg">Product</h4>
            <ul className="space-y-3">
              {[
                { name: 'Getting Started', href: '/' },
                { name: 'System Prompts', href: '/prompts' },
                { name: '@xray Debugging', href: '/xray' },
                { name: 'GitHub', href: 'https://github.com/connectonion/connectonion' },
                { name: 'Discord Community', href: 'https://discord.gg/4xfD9k8AUF' }
              ].map((item) => (
                <li key={item.name}>
                  <Link 
                    href={item.href}
                    className="text-gray-400 hover:text-white transition-colors text-sm inline-flex items-center gap-1 group"
                  >
                    {item.name}
                    {item.href.startsWith('http') && (
                      <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Resources */}
          <div className="space-y-4">
            <h4 className="text-white font-bold text-lg">Resources</h4>
            <ul className="space-y-3">
              {[
                { name: 'GitHub Repository', href: 'https://github.com/connectonion/connectonion' },
                { name: 'PyPI Package', href: 'https://pypi.org/project/connectonion/' },
                { name: 'Python Documentation', href: 'https://docs.python.org/' },
                { name: 'OpenAI API', href: 'https://openai.com/api/' }
              ].map((item) => (
                <li key={item.name}>
                  <a 
                    href={item.href}
                    target={item.href.startsWith('http') ? '_blank' : undefined}
                    rel={item.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                    className="text-gray-400 hover:text-white transition-colors text-sm inline-flex items-center gap-1 group"
                  >
                    {item.name}
                    {item.href.startsWith('http') && (
                      <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                    )}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* Newsletter */}
          <div className="space-y-4">
            <h4 className="text-white font-bold text-lg">Stay Updated</h4>
            <p className="text-gray-400 text-sm">
              Get notified about new features and updates.
            </p>
            <form className="space-y-3" onSubmit={(e) => e.preventDefault()}>
              <input
                type="email"
                placeholder="your@email.com"
                className="w-full px-4 py-3 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:border-purple-500 focus:ring-2 focus:ring-purple-500/30 transition-all focus:outline-none text-sm"
              />
              <button
                type="submit"
                className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold py-3 px-4 rounded-lg transition-all duration-300 hover:shadow-lg hover:shadow-purple-500/30 text-sm"
              >
                Subscribe
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="border-t border-gray-800/50 bg-gray-950/50">
        <div className="container mx-auto px-6 lg:px-8 py-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-1 text-gray-400 text-sm">
              <span>© 2024 ConnectOnion. Made with</span>
              <Heart className="w-4 h-4 text-red-500 fill-current animate-pulse" />
              <span>for AI builders.</span>
            </div>
            <div className="flex items-center gap-6 text-sm">
              <Link href="/" className="text-gray-400 hover:text-white transition-colors">
                Privacy Policy
              </Link>
              <Link href="/" className="text-gray-400 hover:text-white transition-colors">
                Terms of Service
              </Link>
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}