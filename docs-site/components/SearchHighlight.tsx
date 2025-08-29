import React from 'react'

interface SearchHighlightProps {
  text: string
  query: string
  className?: string
}

export function SearchHighlight({ text, query, className = '' }: SearchHighlightProps) {
  if (!query.trim()) {
    return <span className={className}>{text}</span>
  }

  const parts = text.split(new RegExp(`(${query})`, 'gi'))
  
  return (
    <span className={className}>
      {parts.map((part, index) => 
        part.toLowerCase() === query.toLowerCase() ? (
          <mark key={index} className="bg-yellow-500/30 text-yellow-200 px-0.5 rounded">
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        )
      )}
    </span>
  )
}