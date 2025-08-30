'use client'

import { createContext, useContext, useState, ReactNode } from 'react'

interface MarkdownContextType {
  markdownContent: string
  markdownPath: string | null
  filename: string
  setMarkdownContent: (content: string, path?: string | null, filename?: string) => void
  clearMarkdownContent: () => void
}

const MarkdownContext = createContext<MarkdownContextType | undefined>(undefined)

export function MarkdownProvider({ children }: { children: ReactNode }) {
  const [markdownContent, setContent] = useState('')
  const [markdownPath, setPath] = useState<string | null>(null)
  const [filename, setFilename] = useState('content.md')

  const setMarkdownContent = (content: string, path?: string | null, file?: string) => {
    setContent(content)
    if (path !== undefined) setPath(path)
    if (file) setFilename(file)
  }

  const clearMarkdownContent = () => {
    setContent('')
    setPath(null)
    setFilename('content.md')
  }

  return (
    <MarkdownContext.Provider 
      value={{ 
        markdownContent, 
        markdownPath, 
        filename,
        setMarkdownContent,
        clearMarkdownContent
      }}
    >
      {children}
    </MarkdownContext.Provider>
  )
}

export function useMarkdown() {
  const context = useContext(MarkdownContext)
  if (context === undefined) {
    throw new Error('useMarkdown must be used within a MarkdownProvider')
  }
  return context
}