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
  
  // Don't show sidebar on blog, examples, roadmap, or threat-model pages
  const showSidebar = !pathname.startsWith('/blog') && 
                      !pathname.startsWith('/examples') && 
                      !pathname.startsWith('/roadmap') &&
                      !pathname.startsWith('/threat-model')
  
  return (
    <>
      {/* Mobile Documentation Navigation */}
      <MobileDocsNav />
      
      <div className="flex min-h-screen">
        {/* Desktop Sidebar - only show on documentation pages */}
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