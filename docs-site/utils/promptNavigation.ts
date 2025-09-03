// Prompt examples series navigation configuration
export const promptPages = [
  {
    href: '/prompts/examples/friendly-assistant',
    title: 'Friendly Assistant',
    shortTitle: 'Friendly Assistant',
    category: 'General'
  },
  {
    href: '/prompts/examples/technical-writer',
    title: 'Technical Writer',
    shortTitle: 'Technical Writer',
    category: 'Professional'
  },
  {
    href: '/prompts/examples/customer-support',
    title: 'Customer Support',
    shortTitle: 'Customer Support',
    category: 'Business'
  },
  {
    href: '/prompts/examples/code-reviewer',
    title: 'Code Reviewer',
    shortTitle: 'Code Reviewer',
    category: 'Technical'
  },
  {
    href: '/prompts/examples/data-analyst',
    title: 'Data Analyst',
    shortTitle: 'Data Analyst',
    category: 'Analytics'
  },
  {
    href: '/prompts/examples/math-tutor',
    title: 'Math Tutor',
    shortTitle: 'Math Tutor',
    category: 'Education'
  },
  {
    href: '/prompts/examples/security-analyst',
    title: 'Security Analyst',
    shortTitle: 'Security Analyst',
    category: 'Security'
  },
  {
    href: '/prompts/examples/business-strategist',
    title: 'Business Strategist',
    shortTitle: 'Business Strategist',
    category: 'Strategy'
  }
]

export function getPromptNavigation(currentPath: string) {
  const currentIndex = promptPages.findIndex(page => page.href === currentPath)
  
  if (currentIndex === -1) return { previous: null, next: null, current: null }
  
  const previous = currentIndex > 0 ? {
    ...promptPages[currentIndex - 1],
    label: `Prompt ${currentIndex}`
  } : null
  
  const next = currentIndex < promptPages.length - 1 ? {
    ...promptPages[currentIndex + 1],
    label: `Prompt ${currentIndex + 2}`
  } : null
  
  return {
    previous,
    next,
    current: {
      ...promptPages[currentIndex],
      index: currentIndex + 1,
      total: promptPages.length
    }
  }
}