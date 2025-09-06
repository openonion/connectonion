'use client'

import { usePathname } from 'next/navigation'
import { DocsSidebar } from './DocsSidebar'
import { MobileDocsNav } from './MobileDocsNav'
import Footer from './Footer'

export default function ClientLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  
  // Always show sidebar for better navigation
  const showSidebar = true
  
  return (
    <>
      {/* Mobile Documentation Navigation */}
      <MobileDocsNav />
      
      <div className="flex min-h-screen">
        {/* Desktop Sidebar - always visible for navigation */}
        {showSidebar && (
          <div className="hidden lg:block">
            <DocsSidebar />
          </div>
        )}
        
        {/* Main Content */}
        <main className="flex-1 min-w-0 flex flex-col">
          <div className="flex-1">
            {children}
          </div>
          <Footer />
        </main>
      </div>
    </>
  )
}