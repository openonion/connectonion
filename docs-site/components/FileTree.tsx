'use client'

import { 
  Folder, 
  FolderOpen, 
  FileText, 
  FileCode, 
  File, 
  Settings,
  GitBranch,
  Lock,
  FileJson
} from 'lucide-react'

interface FileTreeItem {
  name: string
  type: 'folder' | 'file'
  comment?: string
  children?: FileTreeItem[]
  icon?: 'python' | 'markdown' | 'config' | 'env' | 'git' | 'toml'
}

interface FileTreeProps {
  structure: FileTreeItem[]
  className?: string
}

export function FileTree({ structure, className = '' }: FileTreeProps) {
  const getFileIcon = (item: FileTreeItem) => {
    if (item.type === 'folder') {
      return <FolderOpen className="w-4 h-4 text-blue-400" />
    }

    // Check file extension or icon type
    const fileName = item.name.toLowerCase()
    const iconType = item.icon

    if (iconType === 'python' || fileName.endsWith('.py')) {
      return <span className="text-yellow-400 font-bold text-sm">🐍</span>
    }
    if (iconType === 'markdown' || fileName.endsWith('.md')) {
      return <FileText className="w-4 h-4 text-blue-300" />
    }
    if (iconType === 'config' || fileName.endsWith('.toml')) {
      return <Settings className="w-4 h-4 text-gray-400" />
    }
    if (iconType === 'env' || fileName.includes('.env')) {
      return <Lock className="w-4 h-4 text-green-400" />
    }
    if (iconType === 'git' || fileName.includes('gitignore')) {
      return <GitBranch className="w-4 h-4 text-orange-400" />
    }
    if (fileName.endsWith('.json')) {
      return <FileJson className="w-4 h-4 text-yellow-400" />
    }

    return <File className="w-4 h-4 text-gray-400" />
  }

  const renderTree = (items: FileTreeItem[], level: number = 0) => {
    return items.map((item, index) => {
      const isLast = index === items.length - 1
      const indent = level * 20

      return (
        <div key={`${item.name}-${index}`}>
          <div 
            className="flex items-center gap-2 py-0.5 hover:bg-gray-800/50 rounded px-2 group"
            style={{ marginLeft: `${indent}px` }}
          >
            {/* Tree line characters */}
            {level > 0 && (
              <span className="text-gray-600 select-none font-mono">
                {isLast ? '└──' : '├──'}
              </span>
            )}
            
            {/* Icon */}
            <span className="flex-shrink-0">
              {getFileIcon(item)}
            </span>
            
            {/* Name */}
            <span className={`font-mono text-sm ${
              item.type === 'folder' 
                ? 'text-blue-300 font-semibold' 
                : 'text-gray-200'
            }`}>
              {item.name}
              {item.type === 'folder' && '/'}
            </span>
            
            {/* Comment */}
            {item.comment && (
              <span className="text-gray-500 text-sm font-mono ml-2">
                # {item.comment}
              </span>
            )}
          </div>
          
          {/* Render children */}
          {item.children && item.children.length > 0 && (
            <div className="relative">
              {/* Vertical line for non-last items */}
              {level > 0 && !isLast && (
                <div 
                  className="absolute left-2 top-0 bottom-0 w-px bg-gray-700"
                  style={{ marginLeft: `${indent}px` }}
                />
              )}
              {renderTree(item.children, level + 1)}
            </div>
          )}
        </div>
      )
    })
  }

  return (
    <div className={`bg-gray-900 border border-gray-700 rounded-lg p-6 ${className}`}>
      <h3 className="text-lg font-semibold text-gray-200 mb-4 flex items-center gap-2">
        <Folder className="w-5 h-5 text-blue-400" />
        Files created:
      </h3>
      <div className="font-mono text-sm">
        {renderTree(structure)}
      </div>
    </div>
  )
}