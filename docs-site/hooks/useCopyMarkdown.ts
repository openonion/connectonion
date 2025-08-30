'use client'

import { useState, useCallback } from 'react'
import { getMarkdownPath } from '../utils/markdownMapping'

export type CopyStatus = 'idle' | 'loading' | 'success' | 'error'

interface UseCopyMarkdownReturn {
  copyMarkdown: (pathname?: string) => Promise<boolean>
  status: CopyStatus
  copiedPath: string | null
}

/**
 * Hook for copying markdown content from public/tutorials folder
 * @param defaultPathname - Default pathname to use if not provided to copyMarkdown
 * @returns Object with copyMarkdown function, status, and copiedPath
 */
export function useCopyMarkdown(defaultPathname?: string): UseCopyMarkdownReturn {
  const [status, setStatus] = useState<CopyStatus>('idle')
  const [copiedPath, setCopiedPath] = useState<string | null>(null)
  
  const copyMarkdown = useCallback(async (pathname?: string): Promise<boolean> => {
    const targetPath = pathname || defaultPathname
    
    if (!targetPath) {
      console.error('No pathname provided for copying markdown')
      setStatus('error')
      return false
    }
    
    const markdownPath = getMarkdownPath(targetPath)
    
    if (!markdownPath) {
      console.warn(`No markdown file found for path: ${targetPath}`)
      setStatus('error')
      return false
    }
    
    setStatus('loading')
    
    try {
      // Fetch the markdown content
      const response = await fetch(markdownPath)
      
      if (!response.ok) {
        throw new Error(`Failed to fetch markdown: ${response.statusText}`)
      }
      
      const text = await response.text()
      
      // Copy to clipboard
      await navigator.clipboard.writeText(text)
      
      // Haptic feedback for mobile devices
      if ('vibrate' in navigator && window.innerWidth < 1024) {
        navigator.vibrate(50)
      }
      
      setStatus('success')
      setCopiedPath(targetPath)
      
      // Reset status after 2 seconds
      setTimeout(() => {
        setStatus('idle')
        setCopiedPath(null)
      }, 2000)
      
      return true
    } catch (error) {
      console.error('Failed to copy markdown:', error)
      setStatus('error')
      
      // Reset error status after 3 seconds
      setTimeout(() => {
        setStatus('idle')
      }, 3000)
      
      return false
    }
  }, [defaultPathname])
  
  return { copyMarkdown, status, copiedPath }
}