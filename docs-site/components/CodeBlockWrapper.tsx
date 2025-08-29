import React from 'react'

interface CodeBlockWrapperProps {
  children: React.ReactNode
  className?: string
}

export function CodeBlockWrapper({ children, className = '' }: CodeBlockWrapperProps) {
  return (
    <div className={`relative ${className}`}>
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
        <div className="min-w-0">
          {children}
        </div>
      </div>
    </div>
  )
}