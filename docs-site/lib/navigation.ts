import { 
  Home, Rocket, Terminal, MessageSquare, Code, Gauge, Zap, Shield, Bug, 
  GitBranch, FileText, FolderOpen, Sparkles, Calculator, Cloud, BookOpen,
  Users, Settings, Layers, Brain, MessageCircle, Database, Package, Cpu, Chrome, Camera, Link
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
    next: { href: '/cli', title: 'CLI Reference' }
  },
  {
    title: 'CLI Reference',
    href: '/cli',
    icon: Terminal,
    section: 'Getting Started',
    keywords: ['command', 'terminal', 'co', 'commands'],
    prev: { href: '/quickstart', title: 'Quick Start' },
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
    next: { href: '/tools/browser', title: 'Browser Screenshots' }
  },
  
  // Debugging Tools
  {
    title: 'Browser Screenshots',
    href: '/tools/browser',
    icon: Camera,
    section: 'Debugging',
    keywords: ['browser', 'screenshot', 'debug', 'capture', 'viewport', 'playwright', 'test', 'responsive'],
    prev: { href: '/tools', title: 'Tools' },
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
    next: { href: '/examples/hello-world', title: 'Hello World' }
  },
  {
    title: 'Hello World',
    href: '/examples/hello-world',
    icon: Sparkles,
    section: 'Examples',
    difficulty: 'Beginner',
    keywords: ['hello', 'basic', 'simple', 'first'],
    prev: { href: '/examples', title: 'All Examples' },
    next: { href: '/examples/calculator', title: 'Calculator' },
    exampleIndex: 0,
    totalExamples: 8
  },
  {
    title: 'Calculator',
    href: '/examples/calculator',
    icon: Calculator,
    section: 'Examples',
    difficulty: 'Beginner',
    keywords: ['calculator', 'math', 'compute', 'arithmetic'],
    prev: { href: '/examples/hello-world', title: 'Hello World' },
    next: { href: '/examples/weather-bot', title: 'Weather Bot' },
    exampleIndex: 1,
    totalExamples: 8
  },
  {
    title: 'Weather Bot',
    href: '/examples/weather-bot',
    icon: Cloud,
    section: 'Examples',
    difficulty: 'Intermediate',
    keywords: ['weather', 'bot', 'api', 'forecast'],
    prev: { href: '/examples/calculator', title: 'Calculator' },
    next: { href: '/examples/task-manager', title: 'Task Manager' },
    exampleIndex: 2,
    totalExamples: 8
  },
  {
    title: 'Task Manager',
    href: '/examples/task-manager',
    icon: Code,
    section: 'Examples',
    keywords: ['task', 'manager', 'todo', 'list'],
    prev: { href: '/examples/weather-bot', title: 'Weather Bot' },
    next: { href: '/examples/file-analyzer', title: 'File Analyzer' },
    exampleIndex: 3,
    totalExamples: 8
  },
  {
    title: 'File Analyzer',
    href: '/examples/file-analyzer',
    icon: FileText,
    section: 'Examples',
    keywords: ['file', 'analyzer', 'document', 'parse'],
    prev: { href: '/examples/task-manager', title: 'Task Manager' },
    next: { href: '/examples/api-client', title: 'API Client' },
    exampleIndex: 4,
    totalExamples: 8
  },
  {
    title: 'API Client',
    href: '/examples/api-client',
    icon: Code,
    section: 'Examples',
    keywords: ['api', 'client', 'rest', 'http'],
    prev: { href: '/examples/file-analyzer', title: 'File Analyzer' },
    next: { href: '/examples/math-tutor-agent', title: 'Math Tutor Agent' },
    exampleIndex: 5,
    totalExamples: 8
  },
  {
    title: 'Math Tutor Agent',
    href: '/examples/math-tutor-agent',
    icon: Brain,
    section: 'Examples',
    keywords: ['math', 'tutor', 'education', 'agent'],
    prev: { href: '/examples/api-client', title: 'API Client' },
    next: { href: '/examples/ecommerce-manager', title: 'E-commerce Manager' },
    exampleIndex: 6,
    totalExamples: 8
  },
  {
    title: 'E-commerce Manager',
    href: '/examples/ecommerce-manager',
    icon: Package,
    section: 'Examples',
    keywords: ['ecommerce', 'shop', 'store', 'manager'],
    prev: { href: '/examples/math-tutor-agent', title: 'Math Tutor Agent' },
    next: { href: '/blog', title: 'All Posts' },
    exampleIndex: 7,
    totalExamples: 8
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
    next: { href: '/blog/message-based-architecture', title: 'Message-Based Architecture' }
  },
  {
    title: 'Message-Based Architecture',
    href: '/blog/message-based-architecture',
    icon: Layers,
    section: 'Blog',
    difficulty: 'Architecture',
    keywords: ['message', 'protocol', 'async', 'stateless', 'network'],
    prev: { href: '/blog/cli-ux-progressive-disclosure', title: 'Progressive Disclosure CLI' },
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