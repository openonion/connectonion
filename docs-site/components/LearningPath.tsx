'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight, User, Zap, Bug, BookOpen } from 'lucide-react'

interface LearningPathProps {
  onPathSelect?: (path: 'beginner' | 'experienced' | 'debugging') => void
}

export default function LearningPath({ onPathSelect }: LearningPathProps) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  const paths = [
    {
      id: 'beginner',
      title: 'New to AI Agents',
      description: 'Start with the basics and build your first agent',
      icon: User,
      color: 'from-green-500 to-emerald-500',
      features: ['Simple examples', 'Step-by-step guide', 'No prior experience needed']
    },
    {
      id: 'experienced',
      title: 'Ready to Build',
      description: 'Jump to advanced features and real examples',
      icon: Zap,
      color: 'from-purple-500 to-pink-500',
      features: ['Advanced patterns', 'Best practices', 'Production ready']
    },
    {
      id: 'debugging',
      title: 'Debug Existing Code',
      description: 'Learn to debug and optimize your agents',
      icon: Bug,
      color: 'from-blue-500 to-cyan-500',
      features: ['@xray debugging', 'Performance tips', 'Troubleshooting']
    }
  ]

  const handlePathSelect = (pathId: 'beginner' | 'experienced' | 'debugging') => {
    setSelectedPath(pathId)
    onPathSelect?.(pathId)
    
    // Scroll to appropriate section after selection
    setTimeout(() => {
      const targetId = pathId === 'debugging' ? 'xray-section' : 
                      pathId === 'experienced' ? 'advanced-section' : 
                      'basic-section'
      const element = document.getElementById(targetId)
      element?.scrollIntoView({ behavior: 'smooth' })
    }, 300)
  }

  return (
    <section className="container mx-auto px-6 py-16">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-4xl mx-auto text-center"
      >
        <h2 className="text-heading-1 font-bold mb-4">Choose Your Learning Path</h2>
        <p className="text-body-large mb-12 max-w-2xl mx-auto">
          Get a personalized experience based on your current knowledge and goals
        </p>

        <div className="grid md:grid-cols-3 gap-6">
          {paths.map((path) => {
            const Icon = path.icon
            const isSelected = selectedPath === path.id
            
            return (
              <motion.button
                key={path.id}
                onClick={() => handlePathSelect(path.id as any)}
                className={`glass-subtle rounded-xl p-6 text-left transition-all duration-300 border ${
                  isSelected 
                    ? 'border-purple-500 bg-purple-500/10' 
                    : 'border-gray-700 hover:border-gray-600'
                }`}
                whileHover={{ y: -4 }}
                whileTap={{ scale: 0.98 }}
              >
                <div className={`w-12 h-12 rounded-lg bg-gradient-to-br ${path.color} flex items-center justify-center mb-4`}>
                  <Icon className="w-6 h-6 text-white" />
                </div>
                
                <h3 className="font-bold text-lg mb-2 text-white">{path.title}</h3>
                <p className="text-body text-gray-300 mb-4">{path.description}</p>
                
                <ul className="space-y-2">
                  {path.features.map((feature, i) => (
                    <li key={i} className="flex items-center gap-2 text-caption text-gray-400">
                      <div className="w-1.5 h-1.5 rounded-full bg-purple-400" />
                      {feature}
                    </li>
                  ))}
                </ul>
                
                <div className="flex items-center gap-2 mt-6 text-purple-400 font-medium">
                  Start here
                  <ChevronRight className="w-4 h-4" />
                </div>
              </motion.button>
            )
          })}
        </div>

        <AnimatePresence>
          {selectedPath && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="mt-8 p-4 glass-subtle rounded-lg border border-purple-500/30"
            >
              <div className="flex items-center gap-2 text-purple-400">
                <BookOpen className="w-5 h-5" />
                <span className="font-medium">
                  Great choice! Scroll down to see your personalized content.
                </span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </section>
  )
}