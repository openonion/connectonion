import { 
  Home, Rocket, Terminal, MessageSquare, Code, Gauge, Zap, Shield, Bug, 
  GitBranch, FileText, FolderOpen, Sparkles, Calculator, Cloud, BookOpen,
  Users, Settings, Layers, Brain, MessageCircle, Database, Package, Cpu, Chrome, Camera, Link, Mail, FileCode2
} from 'lucide-react'

// Simple, flat navigation structure with all metadata in one place
export const navigation = [
  // Getting Started
  {
    title: 'Introduction',
    href: '/',
    icon: Home,
    section: 'Getting Started',
    keywords: ['intro', 'overview', 'start', 'begin'],
    prev: null,
    next: { href: '/quickstart', title: 'Quick Start' }
  },
  {
    title: 'Quick Start',
    href: '/quickstart',
    icon: Rocket,
    section: 'Getting Started',
    keywords: ['setup', 'install', 'begin', 'tutorial'],
    prev: { href: '/', title: 'Introduction' },
    next: { href: '/vibe-coding', title: 'Vibe Coding Guide' }
  },
  {
    title: 'Vibe Coding Guide',
    href: '/vibe-coding',
    icon: FileCode2,
    section: 'Getting Started',
    keywords: ['cursor', 'ai', 'vibe', 'coding', 'drag', 'drop', 'docs'],
    prev: { href: '/quickstart', title: 'Quick Start' },
    next: { href: '/cli', title: 'CLI Reference' }
  },
  {
    title: 'CLI Reference',
    href: '/cli',
    icon: Terminal,
    section: 'Getting Started',
    keywords: ['command', 'terminal', 'co', 'commands'],
    prev: { href: '/vibe-coding', title: 'Vibe Coding Guide' },
    next: { href: '/prompts', title: 'System Prompts' }
  },

  // Core Concepts
  {
    title: 'System Prompts',
    href: '/prompts',
    icon: MessageSquare,
    section: 'Core Concepts',
    difficulty: 'Start Here',
    keywords: ['template', 'prompt', 'system', 'message', 'personality', 'behavior'],
    prev: { href: '/cli', title: 'CLI Reference' },
    next: { href: '/tools', title: 'Tools' }
  },
  {
    title: 'Tools',
    href: '/tools',
    icon: Code,
    section: 'Core Concepts',
    keywords: ['function', 'utility', 'actions', 'capabilities', 'tools'],
    prev: { href: '/prompts', title: 'System Prompts' },
    next: { href: '/send-email', title: 'Send Email' }
  },
  
  // Useful Tools
  {
    title: 'Send Email',
    href: '/send-email',
    icon: Mail,
    section: 'Useful Tools',
    keywords: ['email', 'send', 'mail', 'notification', 'alert', 'message', 'smtp'],
    prev: { href: '/tools', title: 'Tools' },
    next: { href: '/tools/browser', title: 'Browser Screenshots' }
  },
  
  // Debugging Tools
  {
    title: 'Browser Screenshots',
    href: '/tools/browser',
    icon: Camera,
    section: 'Debugging',
    keywords: ['browser', 'screenshot', 'debug', 'capture', 'viewport', 'playwright', 'test', 'responsive'],
    prev: { href: '/send-email', title: 'Send Email' },
    next: { href: '/models', title: 'Models' }
  },
  
  {
    title: 'Models',
    href: '/models',
    icon: Cpu,
    section: 'Core Concepts',
    keywords: ['model', 'gpt', 'gemini', 'claude', 'anthropic', 'openai', 'google', 'llm', 'ai'],
    prev: { href: '/tools/browser', title: 'Browser Screenshots' },
    next: { href: '/max-iterations', title: 'max_iterations' }
  },
  {
    title: 'max_iterations',
    href: '/max-iterations',
    icon: Gauge,
    section: 'Core Concepts',
    keywords: ['loop', 'limit', 'iteration', 'control', 'safety'],
    prev: { href: '/models', title: 'Models' },
    next: { href: '/llm_do', title: 'LLM Function' }
  },
  {
    title: 'LLM Function',
    href: '/llm_do',
    icon: Zap,
    section: 'Core Concepts',
    keywords: ['ai', 'model', 'openai', 'language', 'llm_do', 'direct', 'gemini', 'anthropic', 'claude'],
    prev: { href: '/max-iterations', title: 'max_iterations' },
    next: { href: '/trust', title: 'Trust Parameter' }
  },
  {
    title: 'Trust Parameter',
    href: '/trust',
    icon: Shield,
    section: 'Core Concepts',
    keywords: ['security', 'safety', 'trust', 'permission', 'multi-agent'],
    prev: { href: '/llm_do', title: 'LLM Function' },
    next: { href: '/xray', title: '@xray Decorator' }
  },
  {
    title: '@xray Decorator',
    href: '/xray',
    icon: Bug,
    section: 'Core Concepts',
    keywords: ['debug', 'xray', 'decorator', 'trace', 'monitor', 'visibility'],
    prev: { href: '/trust', title: 'Trust Parameter' },
    next: { href: '/tutorials/001-ai-agent-is-just-prompt-plus-function', title: 'Tutorial: AI Agent = Prompt + Function' }
  },

  // Tutorials
  {
    title: '001: AI Agent = Prompt + Function',
    href: '/tutorials/001-ai-agent-is-just-prompt-plus-function',
    icon: BookOpen,
    section: 'Tutorials',
    keywords: ['tutorial', 'beginner', 'first', 'prompt', 'function', 'langchain', 'simple'],
    prev: { href: '/xray', title: '@xray Decorator' },
    next: { href: '/xray/trace', title: 'trace() Visual Flow' }
  },

  // Advanced Features
  {
    title: 'trace() Visual Flow',
    href: '/xray/trace',
    icon: GitBranch,
    section: 'Advanced Features',
    keywords: ['trace', 'flow', 'visual', 'debug', 'execution'],
    prev: { href: '/xray', title: '@xray Decorator' },
    next: { href: '/prompts/formats', title: 'Prompt Formats' }
  },
  {
    title: 'Prompt Formats',
    href: '/prompts/formats',
    icon: FileText,
    section: 'Advanced Features',
    difficulty: 'Interactive Demo',
    keywords: ['format', 'prompt', 'template', 'syntax'],
    prev: { href: '/xray/trace', title: 'trace() Visual Flow' },
    next: { href: '/threat-model', title: 'Threat Model' }
  },

  // Security
  {
    title: 'Threat Model',
    href: '/threat-model',
    icon: Shield,
    section: 'Security',
    keywords: ['security', 'threat', 'risk', 'safety', 'vulnerability'],
    prev: { href: '/prompts/formats', title: 'Prompt Formats' },
    next: { href: '/examples', title: 'All Examples' }
  },

  // Examples
  {
    title: 'All Examples',
    href: '/examples',
    icon: FolderOpen,
    section: 'Examples',
    difficulty: 'Browse',
    keywords: ['examples', 'samples', 'demos', 'tutorials'],
    prev: { href: '/threat-model', title: 'Threat Model' },
    next: { href: '/examples/calculator', title: 'Calculator' }
  },
  {
    title: 'Calculator',
    href: '/examples/calculator',
    icon: Calculator,
    section: 'Examples',
    difficulty: 'Beginner',
    keywords: ['calculator', 'math', 'compute', 'arithmetic', 'tools', 'functions'],
    prev: { href: '/examples', title: 'All Examples' },
    next: { href: '/examples/browser', title: 'Browser Automation' },
    exampleIndex: 0,
    totalExamples: 2
  },
  {
    title: 'Browser Automation',
    href: '/examples/browser',
    icon: Chrome,
    section: 'Examples',
    difficulty: 'Intermediate',
    keywords: ['browser', 'automation', 'screenshot', 'playwright', 'web', 'scraping'],
    prev: { href: '/examples/calculator', title: 'Calculator' },
    next: { href: '/blog', title: 'All Posts' },
    exampleIndex: 1,
    totalExamples: 2
  },

  // Blog - Design Decisions in chronological order
  {
    title: 'All Posts',
    href: '/blog',
    icon: BookOpen,
    section: 'Blog',
    keywords: ['blog', 'posts', 'articles', 'news'],
    prev: { href: '/examples/ecommerce-manager', title: 'E-commerce Manager' },
    next: { href: '/blog/input-method', title: 'Why `input()` Over `run()`' }
  },
  {
    title: 'Why `input()` Over `run()`',
    href: '/blog/input-method',
    icon: Terminal,
    section: 'Blog',
    difficulty: 'Design Decision',
    keywords: ['input', 'run', 'api', 'mental', 'model', 'ux'],
    prev: { href: '/blog', title: 'All Posts' },
    next: { href: '/blog/llm-do', title: 'Why `llm_do()` Over `llm()`' }
  },
  {
    title: 'Why `llm_do()` Over `llm()`',
    href: '/blog/llm-do',
    icon: Code,
    section: 'Blog',
    difficulty: 'Design Decision',
    keywords: ['llm', 'function', 'naming', 'api', 'design'],
    prev: { href: '/blog/input-method', title: 'Why `input()` Over `run()`' },
    next: { href: '/blog/trust-keyword', title: 'Why We Chose "Trust"' }
  },
  {
    title: 'Why We Chose "Trust"',
    href: '/blog/trust-keyword',
    icon: Users,
    section: 'Blog',
    difficulty: 'Design Decision',
    keywords: ['trust', 'design', 'decision', 'authentication'],
    prev: { href: '/blog/llm-do', title: 'Why `llm_do()` Over `llm()`' },
    next: { href: '/blog/network-protocol-design', title: 'Network Protocol Design' }
  },
  {
    title: 'Network Protocol Design',
    href: '/blog/network-protocol-design',
    icon: GitBranch,
    section: 'Blog',
    difficulty: 'Architecture',
    keywords: ['network', 'protocol', 'architecture', 'design'],
    prev: { href: '/blog/trust-keyword', title: 'Why We Chose "Trust"' },
    next: { href: '/blog/agent-address-format', title: 'Agent Address Format' }
  },
  {
    title: 'Agent Address Format',
    href: '/blog/agent-address-format',
    icon: Shield,
    section: 'Blog',
    difficulty: 'Design Decision',
    keywords: ['address', 'public', 'key', 'ed25519', 'identity', 'hex'],
    prev: { href: '/blog/network-protocol-design', title: 'Network Protocol Design' },
    next: { href: '/blog/naming-is-hard', title: 'Why "Address" Over "Identity"' }
  },
  {
    title: 'Why "Address" Over "Identity"',
    href: '/blog/naming-is-hard',
    icon: MessageCircle,
    section: 'Blog',
    difficulty: 'Design Decision',
    keywords: ['naming', 'identity', 'address', 'terminology', 'ux'],
    prev: { href: '/blog/agent-address-format', title: 'Agent Address Format' },
    next: { href: '/blog/cli-ux-progressive-disclosure', title: 'Progressive Disclosure CLI' }
  },
  {
    title: 'Progressive Disclosure CLI',
    href: '/blog/cli-ux-progressive-disclosure',
    icon: Terminal,
    section: 'Blog',
    difficulty: 'Design Decision',
    keywords: ['cli', 'ux', 'progressive', 'disclosure', 'initialization'],
    prev: { href: '/blog/naming-is-hard', title: 'Why "Address" Over "Identity"' },
    next: { href: '/roadmap', title: 'Coming Soon Features' }
  },

  // Roadmap
  {
    title: 'Coming Soon Features',
    href: '/roadmap',
    icon: Rocket,
    section: 'Roadmap',
    difficulty: 'Preview',
    keywords: ['roadmap', 'future', 'upcoming', 'features', 'soon'],
    prev: { href: '/blog/input-method', title: 'Why `input()` Over `run()`' },
    next: { href: '/links', title: 'All Links' }
  },
  
  // Links
  {
    title: 'All Links',
    href: '/links',
    icon: Link,
    section: 'Connect',
    keywords: ['links', 'social', 'media', 'discord', 'github', 'twitter', 'instagram', 'tiktok', 'youtube', 'contact'],
    prev: { href: '/roadmap', title: 'Coming Soon Features' },
    next: null
  },

  // Other pages not in main nav flow
  {
    title: 'Website Maintenance',
    href: '/website-maintenance',
    icon: Settings,
    section: 'Admin',
    keywords: ['website', 'maintenance', 'admin'],
    prev: null,
    next: null
  }
]

// Helper to get page by href
export function getPageByHref(href: string) {
  return navigation.find(page => page.href === href)
}

// Helper to get all pages in a section
export function getPagesBySection(section: string) {
  return navigation.filter(page => page.section === section)
}

// Helper to get example pages
export function getExamplePages() {
  return navigation.filter(page => page.section === 'Examples' && page.exampleIndex !== undefined)
}