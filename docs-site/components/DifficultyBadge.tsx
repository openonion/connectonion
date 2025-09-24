import { FaCircle, FaStar, FaExclamation, FaLightbulb, FaEye, FaBook } from 'react-icons/fa'
import { ReactElement } from 'react'

interface DifficultyBadgeProps {
  level: 'Beginner' | 'Intermediate' | 'Advanced' | 'Expert' | 'Start Here' | 'Important' | 'Design Decision' | 'Preview' | 'Browse'
  size?: 'sm' | 'md' | 'lg'
  showIcon?: boolean
  className?: string
}

const difficultyConfig: Record<string, { bg: string; text: string; border: string; icon: ReactElement; description: string }> = {
  'Beginner': {
    bg: 'bg-green-900/50',
    text: 'text-green-400',
    border: 'border-green-500/30',
    icon: <FaCircle />,
    description: 'Basic concepts, single tools, simple interactions'
  },
  'Intermediate': {
    bg: 'bg-yellow-900/50',
    text: 'text-yellow-400',
    border: 'border-yellow-500/30',
    icon: <FaCircle />,
    description: 'Multiple tools, state management, workflows'
  },
  'Advanced': {
    bg: 'bg-orange-900/50',
    text: 'text-orange-400',
    border: 'border-orange-500/30',
    icon: <FaCircle />,
    description: 'System integration, security, API handling'
  },
  'Expert': {
    bg: 'bg-red-900/50',
    text: 'text-red-400',
    border: 'border-red-500/30',
    icon: <FaCircle />,
    description: 'Enterprise business logic, multi-system coordination'
  },
  'Start Here': {
    bg: 'bg-purple-900/50',
    text: 'text-purple-400',
    border: 'border-purple-500/30',
    icon: <FaStar />,
    description: 'Recommended starting point'
  },
  'Important': {
    bg: 'bg-blue-900/50',
    text: 'text-blue-400',
    border: 'border-blue-500/30',
    icon: <FaExclamation />,
    description: 'Critical information'
  },
  'Design Decision': {
    bg: 'bg-indigo-900/50',
    text: 'text-indigo-400',
    border: 'border-indigo-500/30',
    icon: <FaLightbulb />,
    description: 'Architectural and design insights'
  },
  'Preview': {
    bg: 'bg-pink-900/50',
    text: 'text-pink-400',
    border: 'border-pink-500/30',
    icon: <FaEye />,
    description: 'Preview of upcoming features'
  },
  'Browse': {
    bg: 'bg-gray-800/50',
    text: 'text-gray-400',
    border: 'border-gray-600/30',
    icon: <FaBook />,
    description: 'Browse all examples'
  }
}

const sizeConfig = {
  'sm': {
    padding: 'px-2 py-0.5',
    text: 'text-xs',
    icon: 'text-xs'
  },
  'md': {
    padding: 'px-3 py-1',
    text: 'text-sm',
    icon: 'text-sm'
  },
  'lg': {
    padding: 'px-4 py-2',
    text: 'text-base',
    icon: 'text-base'
  }
}

export function DifficultyBadge({ 
  level, 
  size = 'md', 
  showIcon = true, 
  className = '' 
}: DifficultyBadgeProps) {
  // Guard against invalid level values
  if (!level || !(level in difficultyConfig)) {
    console.warn(`Invalid difficulty level: ${level}`)
    return null
  }
  
  const { bg, text, border, icon, description } = difficultyConfig[level]
  const { padding, text: textSize, icon: iconSize } = sizeConfig[size]
  
  return (
    <span 
      className={`${bg} ${text} ${border} ${padding} ${textSize} border rounded-md font-medium inline-flex items-center gap-1.5 ${className}`}
      title={`${level} level - ${description}`}
    >
      {showIcon && (
        <span className={`${iconSize} ${text} leading-none inline-flex`} aria-hidden="true">
          {icon}
        </span>
      )}
      <span>{level}</span>
    </span>
  )
}

// Utility function to get difficulty from page path or metadata
export function getDifficultyFromPath(path: string): 'Beginner' | 'Intermediate' | 'Advanced' | 'Expert' {
  // Example paths like /examples/hello-world -> Beginner
  if (path.includes('hello-world') || path.includes('calculator') || path.includes('weather-bot')) {
    return 'Beginner'
  }
  if (path.includes('task-manager') || path.includes('math-tutor-agent')) {
    return 'Intermediate'
  }
  if (path.includes('file-analyzer') || path.includes('api-client')) {
    return 'Advanced'
  }
  if (path.includes('ecommerce-manager')) {
    return 'Expert'
  }
  return 'Beginner'
}