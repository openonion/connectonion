'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { getPageNavigation } from '../utils/pageNavigation'

export function PageNavigation() {
  const pathname = usePathname()
  const navigation = getPageNavigation(pathname)
  
  // Don't render if no navigation available
  if (!navigation.previous && !navigation.next) {
    return null
  }
  
  return (
    <div className="mt-16 pt-8 border-t border-gray-800">
      <div className="flex flex-col sm:flex-row justify-between items-center gap-4">
        {navigation.previous ? (
          <Link 
            href={navigation.previous.href} 
            className="flex items-center gap-2 text-purple-400 hover:text-purple-300 font-medium transition-colors group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
            <span className="text-center sm:text-left">
              <span className="text-gray-500 text-sm block">Previous</span>
              {navigation.previous.title}
            </span>
          </Link>
        ) : (
          <div className="flex-1" />
        )}
        
        {navigation.next ? (
          <Link 
            href={navigation.next.href} 
            className="flex items-center gap-2 text-purple-400 hover:text-purple-300 font-medium transition-colors group"
          >
            <span className="text-center sm:text-right">
              <span className="text-gray-500 text-sm block">Next</span>
              {navigation.next.title}
            </span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </Link>
        ) : (
          <div className="flex-1" />
        )}
      </div>
    </div>
  )
}