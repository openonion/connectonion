'use client'

import Link from 'next/link'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { usePathname } from 'next/navigation'
import { getPageByHref, getExamplePages } from '../lib/navigation'

export function ContentNavigation() {
  const pathname = usePathname()
  const currentPage = getPageByHref(pathname)
  
  if (!currentPage) return null
  
  const { prev, next } = currentPage
  
  // Show example dots for example pages
  const isExample = currentPage.section === 'Examples' && currentPage.exampleIndex !== undefined
  const examplePages = isExample ? getExamplePages() : []
  
  return (
    <div className="mt-16 pt-8 border-t border-gray-700">
      {/* Example Series Dots */}
      {isExample && examplePages.length > 0 && (
        <div className="flex items-center justify-center gap-2 mb-8">
          {examplePages.map((example, idx) => (
            <Link
              key={example.href}
              href={example.href}
              className={`w-2 h-2 rounded-full transition-all ${
                idx === currentPage.exampleIndex
                  ? 'bg-purple-400 w-8' 
                  : 'bg-gray-600 hover:bg-gray-500'
              }`}
              title={example.title}
            />
          ))}
        </div>
      )}
      
      {/* Navigation Buttons */}
      <div className="flex items-center justify-between">
        {prev ? (
          <Link
            href={prev.href}
            className="group flex items-center gap-3 px-6 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg transition-all"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400 group-hover:text-white transition-colors" />
            <div className="text-left">
              <div className="text-xs text-gray-400 mb-1">Previous</div>
              <div className="text-sm font-medium text-white">{prev.title}</div>
            </div>
          </Link>
        ) : (
          <div />
        )}
        
        {next ? (
          <Link
            href={next.href}
            className="group flex items-center gap-3 px-6 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg transition-all"
          >
            <div className="text-right">
              <div className="text-xs text-gray-400 mb-1">Next</div>
              <div className="text-sm font-medium text-white">{next.title}</div>
            </div>
            <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-white transition-colors" />
          </Link>
        ) : (
          <div />
        )}
      </div>
    </div>
  )
}