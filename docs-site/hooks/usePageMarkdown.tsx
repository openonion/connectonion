'use client'

import { useEffect } from 'react'
import { useMarkdown } from '../contexts/MarkdownContext'

export function usePageMarkdown(content: string, path?: string, filename?: string) {
  const { setMarkdownContent, clearMarkdownContent } = useMarkdown()
  
  useEffect(() => {
    // Set the markdown content when component mounts
    setMarkdownContent(content, path, filename)
    
    // Clear when component unmounts
    return () => {
      clearMarkdownContent()
    }
  }, [content, path, filename, setMarkdownContent, clearMarkdownContent])
}