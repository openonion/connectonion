'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Github, MessageCircle, Heart } from 'lucide-react'

export default function Footer() {
  const currentYear = new Date().getFullYear()
  const pathname = usePathname()
  
  // Only show CTA on landing page and getting started pages
  const showCTA = pathname === '/' || pathname === '/quickstart'
  
  return (
    <footer className="mt-auto">
      {/* Simple CTA - Only on specific pages */}
      {showCTA && (
        <div className="mt-32 mb-20 text-center px-4">
          <h3 className="text-2xl font-light text-gray-300 mb-6">
            Ready to build?
          </h3>
          <div className="flex flex-wrap gap-4 justify-center">
            <Link
              href="/quickstart"
              className="px-6 py-3 bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 rounded-lg transition-colors"
            >
              Get Started
            </Link>
            <a
              href="https://github.com/wu-changxing/connectonion"
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3 bg-gray-800/50 hover:bg-gray-800 text-gray-300 rounded-lg transition-colors"
            >
              View on GitHub
            </a>
          </div>
        </div>
      )}

      {/* Minimal Footer - Mobile Optimized */}
      <div className="border-t border-gray-800/50 mt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12">
          {/* Mobile: Stacked | Desktop: Side by side */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
            {/* Left: Brand & Copyright */}
            <div className="flex flex-col sm:flex-row items-center gap-4 text-sm text-gray-500">
              <div className="flex items-center gap-2">
                <img 
                  src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" 
                  alt="ConnectOnion" 
                  className="w-6 h-6 rounded"
                />
                <span className="font-medium text-gray-400">ConnectOnion</span>
              </div>
              <span className="hidden sm:inline text-gray-700">·</span>
              <span>© {currentYear}</span>
              <span className="hidden sm:inline text-gray-700">·</span>
              <span className="hidden sm:flex items-center gap-1">
                Built with <Heart className="w-3 h-3 text-red-500 fill-current" />
              </span>
            </div>
            
            {/* Right: Social Links */}
            <div className="flex items-center gap-4">
              <a
                href="https://github.com/wu-changxing/connectonion"
                target="_blank"
                rel="noopener noreferrer"
                className="text-gray-500 hover:text-gray-300 transition-colors"
                aria-label="GitHub"
              >
                <Github className="w-5 h-5" />
              </a>
              <a
                href="https://discord.gg/4xfD9k8AUF"
                target="_blank"
                rel="noopener noreferrer"
                className="text-gray-500 hover:text-gray-300 transition-colors"
                aria-label="Discord"
              >
                <MessageCircle className="w-5 h-5" />
              </a>
              <span className="text-xs text-gray-600 ml-2">v0.0.4</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}

/**
 * Design Principles Applied:
 * 
 * 1. Context-Aware Content
 *    - CTA only shows on landing and quickstart pages
 *    - Reduces repetition and clutter
 * 
 * 2. Minimal Footer
 *    - Just essentials: brand, copyright, social links
 *    - No overwhelming link lists
 *    - Clean single-line layout
 * 
 * 3. Mobile Optimization
 *    - Stacks vertically on mobile
 *    - Smaller elements for small screens
 *    - Reduced content density
 * 
 * 4. Clear Visual Hierarchy
 *    - Page content has space to breathe
 *    - Navigation is distinct from footer
 *    - Subtle borders and colors
 * 
 * 5. Performance
 *    - Smaller DOM size
 *    - Less CSS to process
 *    - Faster page loads
 */