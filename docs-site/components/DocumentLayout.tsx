'use client'

import { PageCopyButton } from './PageCopyButton'
import { ReactNode } from 'react'

interface DocumentLayoutProps {
  children: ReactNode
  markdownPath?: string
  content?: string
  filename?: string
  title?: string
  description?: string
}

export function DocumentLayout({
  children,
  markdownPath,
  content,
  filename,
  title,
  description
}: DocumentLayoutProps) {
  return (
    <>
      {/* Mobile floating copy button */}
      <PageCopyButton
        markdownPath={markdownPath}
        content={content}
        filename={filename}
        variant="floating"
      />

      {/* Desktop header with copy buttons */}
      <div className="hidden lg:block">
        {title && (
          <div className="flex items-start justify-between mb-8">
            <div className="flex-1">
              <h1 className="text-4xl font-bold text-white mb-2">{title}</h1>
              {description && (
                <p className="text-xl text-gray-300">{description}</p>
              )}
            </div>
            <PageCopyButton
              markdownPath={markdownPath}
              content={content}
              filename={filename}
              variant="default"
            />
          </div>
        )}
      </div>

      {/* Mobile header without buttons (they're in nav or floating) */}
      <div className="lg:hidden">
        {title && (
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">{title}</h1>
            {description && (
              <p className="text-lg text-gray-300">{description}</p>
            )}
          </div>
        )}
      </div>

      {/* Page content */}
      {children}
    </>
  )
}