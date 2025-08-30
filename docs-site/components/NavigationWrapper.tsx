'use client'

import Navigation from './Navigation'
import { useMarkdown } from '../contexts/MarkdownContext'

export default function NavigationWrapper() {
  const { markdownContent, markdownPath, filename } = useMarkdown()
  
  return (
    <Navigation 
      markdownContent={markdownContent}
      markdownPath={markdownPath || undefined}
      filename={filename}
    />
  )
}