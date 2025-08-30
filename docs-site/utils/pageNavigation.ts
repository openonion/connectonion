// Page navigation utility based on sidebar order
// This ensures consistent previous/next navigation across all pages

interface PageNavigation {
  previous?: {
    href: string
    title: string
  }
  next?: {
    href: string
    title: string
  }
}

// Define the complete navigation order based on sidebar structure
const navigationOrder = [
  // Getting Started
  { href: '/', title: 'Introduction' },
  { href: '/quickstart', title: 'Quick Start' },
  { href: '/cli', title: 'CLI Reference' },
  
  // Core Concepts
  { href: '/prompts', title: 'System Prompts' },
  { href: '/tools', title: 'Tools' },
  { href: '/max-iterations', title: 'max_iterations' },
  { href: '/llm_do', title: 'LLM Function' },
  { href: '/trust', title: 'Trust Parameter' },
  { href: '/xray', title: '@xray Decorator' },
  
  // Advanced Features
  { href: '/xray/trace', title: 'trace() Visual Flow' },
  { href: '/prompts/formats', title: 'Prompt Formats' },
  
  // Security
  { href: '/threat-model', title: 'Threat Model' },
  
  // Examples
  { href: '/examples', title: 'All Examples' },
  { href: '/examples/hello-world', title: 'Hello World Example' },
  { href: '/examples/calculator', title: 'Calculator Example' },
  { href: '/examples/weather-bot', title: 'Weather Bot Example' },
  
  // Blog
  { href: '/blog', title: 'Blog' },
  { href: '/blog/network-protocol-design', title: 'Network Protocol Design' },
  { href: '/blog/trust-keyword', title: 'Why We Chose "Trust"' },
  { href: '/blog/llm-do', title: 'Why llm_do() Over llm()' },
  { href: '/blog/input-method', title: 'Why input() Over run()' },
  
  // Roadmap
  { href: '/roadmap', title: 'Roadmap' },
  
  // Contributing
  { href: '/website-maintenance', title: 'Website Maintenance' },
]

/**
 * Get the previous and next pages for a given pathname
 * @param pathname - The current page pathname
 * @returns Object with previous and next page info
 */
export function getPageNavigation(pathname: string): PageNavigation {
  const currentIndex = navigationOrder.findIndex(page => page.href === pathname)
  
  if (currentIndex === -1) {
    return {}
  }
  
  const navigation: PageNavigation = {}
  
  // Get previous page
  if (currentIndex > 0) {
    navigation.previous = navigationOrder[currentIndex - 1]
  }
  
  // Get next page
  if (currentIndex < navigationOrder.length - 1) {
    navigation.next = navigationOrder[currentIndex + 1]
  }
  
  return navigation
}

/**
 * Check if a page should show navigation
 * @param pathname - The current page pathname
 * @returns True if the page should show navigation
 */
export function shouldShowNavigation(pathname: string): boolean {
  return navigationOrder.some(page => page.href === pathname)
}