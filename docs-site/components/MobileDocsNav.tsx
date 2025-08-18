'use client'

import { useState } from 'react'
import { Menu, X, BookOpen } from 'lucide-react'
import { DocsSidebar } from './DocsSidebar'
import { motion, AnimatePresence } from 'framer-motion'
import Link from 'next/link'

export function MobileDocsNav() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      {/* Mobile Header Bar */}
      <div className="lg:hidden sticky top-0 z-50 bg-gray-900/95 backdrop-blur-sm border-b border-gray-800">
        <div className="flex items-center justify-between px-4 py-3">
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="p-2 rounded-md bg-gray-800/60 text-white border border-gray-700/60 hover:bg-gray-700/60 transition-colors"
            aria-label="Toggle documentation menu"
          >
            {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          
          <Link href="/" className="flex items-center gap-2">
            <img src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" alt="ConnectOnion" className="w-6 h-6 rounded-md object-cover" />
            <span className="font-semibold text-white">ConnectOnion</span>
          </Link>
          
          <div className="w-10" /> {/* Balance spacing */}
        </div>
      </div>

      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="lg:hidden fixed inset-0 bg-black/50 z-40"
              onClick={() => setIsOpen(false)}
            />
            
            {/* Mobile Sidebar */}
            <motion.div
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'tween', duration: 0.3 }}
              className="lg:hidden fixed left-0 top-16 h-[calc(100vh-4rem)] z-50"
            >
              <DocsSidebar />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  )
}