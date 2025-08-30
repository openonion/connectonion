'use client'

import Link from 'next/link'
import { Github, MessageCircle, Mail, Heart, Sparkles, Code2, Terminal, Zap, FileText, Rocket, ExternalLink, ChevronRight } from 'lucide-react'

export default function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="mt-32">
      {/* Call to Action Section - IMPROVED CONTRAST & SPACING */}
      <div className="relative overflow-hidden bg-gradient-to-br from-purple-900/20 via-gray-900 to-blue-900/20 border-y border-gray-800">
        <div className="absolute inset-0 bg-gradient-to-r from-purple-600/5 via-transparent to-blue-600/5" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
          <div className="text-center">
            <h3 className="text-3xl font-bold text-white mb-4">
              Ready to Build Your First AI Agent?
            </h3>
            <p className="text-gray-300 text-lg mb-10 max-w-2xl mx-auto">
              Join thousands of developers using ConnectOnion to build production-ready AI agents in minutes, not hours.
            </p>
            <div className="flex flex-wrap gap-4 justify-center">
              <Link
                href="/quickstart"
                className="inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white font-semibold rounded-xl transition-all hover:scale-105 shadow-lg hover:shadow-purple-500/25"
              >
                <Rocket className="w-5 h-5" />
                Get Started
              </Link>
              <a
                href="https://github.com/wu-changxing/connectonion"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-8 py-4 bg-gray-800/80 hover:bg-gray-700 text-white font-semibold rounded-xl border border-gray-600 transition-all hover:scale-105 hover:border-gray-500"
              >
                <Github className="w-5 h-5" />
                Star on GitHub
                <span className="ml-2 px-2 py-0.5 text-xs bg-gray-700 rounded-full border border-gray-600">⭐ 1.2k</span>
              </a>
              <a
                href="https://discord.gg/4xfD9k8AUF"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-8 py-4 bg-gray-800/80 hover:bg-gray-700 text-white font-semibold rounded-xl border border-gray-600 transition-all hover:scale-105 hover:border-gray-500"
              >
                <MessageCircle className="w-5 h-5" />
                Join Discord
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Main Footer Content - IMPROVED HIERARCHY & SPACING */}
      <div className="bg-gray-900 border-b border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-x-8 gap-y-12">
            
            {/* Brand Column - ENHANCED VISIBILITY */}
            <div className="col-span-2 md:col-span-4 lg:col-span-1 space-y-6 lg:pr-8">
              <div>
                <div className="flex items-center gap-3 mb-5">
                  <img 
                    src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" 
                    alt="ConnectOnion" 
                    className="w-12 h-12 rounded-xl shadow-lg"
                  />
                  <div>
                    <h3 className="text-2xl font-bold text-white">ConnectOnion</h3>
                    <p className="text-xs text-purple-400 font-medium">v0.0.1b6</p>
                  </div>
                </div>
                <p className="text-gray-300 text-sm leading-relaxed">
                  The simplest way to build AI agents with Python. Keep simple things simple, make complicated things possible.
                </p>
              </div>
              
              {/* Social Links - BETTER CONTRAST */}
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wider font-semibold mb-4">CONNECT</p>
                <div className="flex items-center gap-3">
                  <a
                    href="https://github.com/wu-changxing/connectonion"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-3 bg-gray-800 hover:bg-gray-700 rounded-xl text-gray-300 hover:text-white transition-all hover:scale-110 hover:shadow-lg"
                    aria-label="GitHub"
                  >
                    <Github className="w-5 h-5" />
                  </a>
                  <a
                    href="https://discord.gg/4xfD9k8AUF"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-3 bg-gray-800 hover:bg-gray-700 rounded-xl text-gray-300 hover:text-white transition-all hover:scale-110 hover:shadow-lg"
                    aria-label="Discord"
                  >
                    <MessageCircle className="w-5 h-5" />
                  </a>
                  <a
                    href="https://pypi.org/project/connectonion/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-3 bg-gray-800 hover:bg-gray-700 rounded-xl text-gray-300 hover:text-white transition-all hover:scale-110 hover:shadow-lg"
                    aria-label="PyPI"
                  >
                    <Code2 className="w-5 h-5" />
                  </a>
                  <a
                    href="mailto:hello@connectonion.com"
                    className="p-3 bg-gray-800 hover:bg-gray-700 rounded-xl text-gray-300 hover:text-white transition-all hover:scale-110 hover:shadow-lg"
                    aria-label="Email"
                  >
                    <Mail className="w-5 h-5" />
                  </a>
                </div>
              </div>
            </div>

            {/* DOCS - IMPROVED READABILITY */}
            <div className="space-y-5">
              <h4 className="text-sm font-bold text-white uppercase tracking-wider">DOCS</h4>
              <ul className="space-y-3">
                {[
                  { name: 'Quick Start', href: '/quickstart', icon: Rocket },
                  { name: 'Tools', href: '/tools', icon: Code2 },
                  { name: 'System Prompts', href: '/prompts', icon: FileText },
                  { name: '@xray Debug', href: '/xray', icon: Zap },
                  { name: 'CLI Reference', href: '/cli', icon: Terminal }
                ].map((item) => (
                  <li key={item.name}>
                    <Link 
                      href={item.href}
                      className="text-gray-300 hover:text-white transition-colors text-sm flex items-center gap-2 group"
                    >
                      <item.icon className="w-4 h-4 text-gray-500 group-hover:text-purple-400 transition-colors" />
                      <span className="group-hover:translate-x-0.5 transition-transform">{item.name}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>

            {/* LEARN - IMPROVED READABILITY */}
            <div className="space-y-5">
              <h4 className="text-sm font-bold text-white uppercase tracking-wider">LEARN</h4>
              <ul className="space-y-3">
                {[
                  { name: 'max_iterations', href: '/max-iterations' },
                  { name: 'LLM Function', href: '/llm_do' },
                  { name: 'Trust Parameter', href: '/trust' },
                  { name: 'Examples', href: '/examples' },
                  { name: 'Blog', href: '/blog' }
                ].map((item) => (
                  <li key={item.name}>
                    <Link 
                      href={item.href}
                      className="text-gray-300 hover:text-white transition-colors text-sm group inline-flex items-center gap-1"
                    >
                      <ChevronRight className="w-3 h-3 text-gray-600 group-hover:text-purple-400 transition-colors" />
                      <span className="group-hover:translate-x-0.5 transition-transform">{item.name}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>

            {/* RESOURCES - IMPROVED VISIBILITY */}
            <div className="space-y-5">
              <h4 className="text-sm font-bold text-white uppercase tracking-wider">RESOURCES</h4>
              <ul className="space-y-3">
                {[
                  { name: 'GitHub', href: 'https://github.com/wu-changxing/connectonion', external: true },
                  { name: 'PyPI Package', href: 'https://pypi.org/project/connectonion/', external: true },
                  { name: 'Discord', href: 'https://discord.gg/4xfD9k8AUF', external: true },
                  { name: 'Roadmap', href: '/roadmap' },
                  { name: 'Threat Model', href: '/threat-model' }
                ].map((item) => (
                  <li key={item.name}>
                    {item.external ? (
                      <a 
                        href={item.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-gray-300 hover:text-white transition-colors text-sm inline-flex items-center gap-1.5 group"
                      >
                        <span className="group-hover:translate-x-0.5 transition-transform">{item.name}</span>
                        <ExternalLink className="w-3 h-3 text-gray-600 group-hover:text-purple-400 transition-all" />
                      </a>
                    ) : (
                      <Link 
                        href={item.href}
                        className="text-gray-300 hover:text-white transition-colors text-sm group inline-flex items-center gap-1"
                      >
                        <ChevronRight className="w-3 h-3 text-gray-600 group-hover:text-purple-400 transition-colors" />
                        <span className="group-hover:translate-x-0.5 transition-transform">{item.name}</span>
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            {/* COMPANY - IMPROVED VISIBILITY */}
            <div className="space-y-5">
              <h4 className="text-sm font-bold text-white uppercase tracking-wider">COMPANY</h4>
              <ul className="space-y-3">
                {[
                  { name: 'GitHub', href: 'https://github.com/wu-changxing/connectonion', external: true },
                  { name: 'Discord', href: 'https://discord.gg/4xfD9k8AUF', external: true },
                  { name: 'Contact', href: 'mailto:hello@connectonion.com' }
                ].map((item) => (
                  <li key={item.name}>
                    {item.external ? (
                      <a 
                        href={item.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-gray-300 hover:text-white transition-colors text-sm inline-flex items-center gap-1.5 group"
                      >
                        <span className="group-hover:translate-x-0.5 transition-transform">{item.name}</span>
                        <ExternalLink className="w-3 h-3 text-gray-600 group-hover:text-purple-400 transition-all" />
                      </a>
                    ) : (
                      <a 
                        href={item.href}
                        className="text-gray-300 hover:text-white transition-colors text-sm group inline-flex items-center gap-1"
                      >
                        <ChevronRight className="w-3 h-3 text-gray-600 group-hover:text-purple-400 transition-colors" />
                        <span className="group-hover:translate-x-0.5 transition-transform">{item.name}</span>
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>


      {/* Bottom Bar - CLEAN & MINIMAL */}
      <div className="bg-gray-950">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <span>© {currentYear} ConnectOnion</span>
              <span className="text-gray-600">·</span>
              <span className="flex items-center gap-1">
                Built with <Heart className="w-3.5 h-3.5 text-red-500 fill-current" /> for developers
              </span>
            </div>
            
            <div className="flex items-center gap-4 text-xs">
              <span className="text-gray-500">MIT License</span>
              <span className="text-gray-600">·</span>
              <a 
                href="https://github.com/wu-changxing/connectonion/releases" 
                className="text-gray-500 hover:text-purple-400 transition-colors"
              >
                v0.0.1b6
              </a>
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}