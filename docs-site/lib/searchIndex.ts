// Search index with page content for full-text search
export interface SearchableItem {
  title: string
  href: string
  section: string
  keywords?: string[]
  content: string // Full text content for searching
  contentPreview?: string // Short preview to show in results
}

export const searchIndex: SearchableItem[] = [
  // Getting Started
  {
    title: 'Introduction',
    href: '/',
    section: 'Getting Started',
    keywords: ['intro', 'overview', 'start', 'connectonion', 'connect onion'],
    content: `ConnectOnion is the simplest way to build AI agents in Python. No complex class hierarchies, no confusing abstractions. Just write Python functions and let ConnectOnion handle the rest. Build powerful AI agents with just functions. Create agent with one line of code. Start building in under 60 seconds. The best agent framework for Python developers.`,
    contentPreview: 'The simplest way to build AI agents in Python...'
  },
  {
    title: 'Quick Start',
    href: '/quickstart',
    section: 'Getting Started',
    keywords: ['setup', 'install', 'begin', 'pip', 'getting started'],
    content: `Install ConnectOnion with pip install connectonion. Create your first agent in 60 seconds. Write a simple Python function, create an agent with Agent(), and call agent.run(). No complex setup, no configuration files, just Python. Quick installation guide, first agent tutorial, basic examples.`,
    contentPreview: 'Install and create your first agent in 60 seconds...'
  },
  {
    title: 'CLI Reference',
    href: '/cli',
    section: 'Getting Started',
    keywords: ['command', 'terminal', 'co', 'cli'],
    content: `ConnectOnion CLI commands: co init to initialize a new project, co run to run your agent, co test to test tools, co xray to debug with visual tracing. Command line interface for managing agents, running scripts, and debugging.`,
    contentPreview: 'CLI commands for managing ConnectOnion agents...'
  },

  // Core Concepts
  {
    title: 'max_iterations',
    href: '/max-iterations',
    section: 'Core Concepts',
    keywords: ['loop', 'limit', 'iterations', 'control', 'max_iterations'],
    content: `Control how many times your agent can use tools with max_iterations parameter. Prevent infinite loops, control costs, ensure termination. Set iteration limits for safety and efficiency. Default is 10 iterations. Essential for production agents.`,
    contentPreview: 'Control agent tool usage with iteration limits...'
  },
  {
    title: '@xray Decorator',
    href: '/xray',
    section: 'Core Concepts',
    keywords: ['debug', 'trace', 'xray', 'decorator', 'visual', 'debugging'],
    content: `Debug your agents visually with @xray decorator. See every decision, tool call, and thought process. Visual flow tracing, step-by-step debugging, understand agent behavior. Add @xray to any function to enable tracing. Essential debugging tool for complex agents.`,
    contentPreview: 'Visual debugging for AI agents...'
  },
  {
    title: 'LLM Function',
    href: '/llm_do',
    section: 'Core Concepts',
    keywords: ['ai', 'model', 'llm_do', 'llm', 'function'],
    content: `The llm_do function is ConnectOnion's core AI interaction primitive. Simple function for LLM calls, automatic retry logic, streaming support. Use llm_do() for direct LLM interaction without agents. Perfect for simple AI tasks.`,
    contentPreview: 'Direct LLM interaction without agents...'
  },
  {
    title: 'Tools',
    href: '/tools',
    section: 'Core Concepts',
    keywords: ['function', 'utility', 'tools', 'tool'],
    content: `Convert any Python function into an agent tool. Automatic type inference, parameter validation, error handling. Tools are just functions - no classes needed. Create tools from existing code easily.`,
    contentPreview: 'Convert Python functions into agent tools...'
  },
  {
    title: 'System Prompts',
    href: '/prompts',
    section: 'Core Concepts',
    keywords: ['template', 'prompt', 'system', 'prompts'],
    content: `Customize agent behavior with system prompts. Define personality, constraints, goals. System prompts guide agent decision-making. Use markdown for clear formatting. Examples and best practices included.`,
    contentPreview: 'Customize agent behavior with system prompts...'
  },
  {
    title: 'Trust Parameter',
    href: '/trust',
    section: 'Core Concepts',
    keywords: ['security', 'safety', 'trust', 'parameter', 'authentication'],
    content: `Control agent trust levels with the trust parameter. Three levels: none (no verification), prompt (user confirms), always (automatic trust). Essential for multi-agent systems. Security best practices for agent communication.`,
    contentPreview: 'Security and trust in agent systems...'
  },

  // Advanced Features
  {
    title: 'trace() Visual Flow',
    href: '/trace',
    section: 'Advanced Features',
    keywords: ['trace', 'visual', 'flow', 'debug', 'visualization'],
    content: `Visualize agent execution flow with trace(). See tool calls, decisions, and results in real-time. Generate flow diagrams, understand agent logic, debug complex behaviors. Advanced debugging for production systems.`,
    contentPreview: 'Visualize agent execution in real-time...'
  },
  {
    title: 'Prompt Formats',
    href: '/prompt-formats',
    section: 'Advanced Features',
    keywords: ['format', 'markdown', 'jinja', 'template', 'prompts'],
    content: `Support for multiple prompt formats: plain text, markdown, Jinja2 templates. Dynamic prompts with variables, conditional logic, loops. Advanced prompt engineering techniques.`,
    contentPreview: 'Multiple prompt formats and templating...'
  },

  // Security
  {
    title: 'Threat Model',
    href: '/threat-model',
    section: 'Security',
    keywords: ['threat', 'security', 'model', 'safety', 'protection'],
    content: `Understanding ConnectOnion's security model. Tool execution safety, prompt injection prevention, trust boundaries. Security considerations for production deployment. Best practices for secure agent systems.`,
    contentPreview: 'Security considerations for agent systems...'
  },

  // Examples
  {
    title: 'All Examples',
    href: '/examples',
    section: 'Examples',
    keywords: ['examples', 'samples', 'code', 'demo'],
    content: `Browse all ConnectOnion examples. Hello World, Calculator, Weather Bot, and more. Complete working examples with explanations. Copy and modify for your needs.`,
    contentPreview: 'Complete working agent examples...'
  },
  {
    title: 'Hello World',
    href: '/examples/hello-world',
    section: 'Examples',
    keywords: ['hello', 'world', 'basic', 'simple', 'beginner'],
    content: `Simplest ConnectOnion agent example. Create an agent that responds to greetings. Perfect starting point for beginners. Learn the basics in 5 lines of code.`,
    contentPreview: 'Your first ConnectOnion agent...'
  },
  {
    title: 'Calculator',
    href: '/examples/calculator',
    section: 'Examples',
    keywords: ['calculator', 'math', 'compute', 'calculation', 'beginner'],
    content: `Build a calculator agent with mathematical tools. Addition, subtraction, multiplication, division. Shows tool creation and integration. Great for learning tool patterns.`,
    contentPreview: 'Mathematical agent with calculation tools...'
  },
  {
    title: 'Weather Bot',
    href: '/examples/weather-bot',
    section: 'Examples',
    keywords: ['weather', 'bot', 'api', 'intermediate'],
    content: `Create a weather information agent. Integrate with weather APIs, handle location queries, provide forecasts. Intermediate example showing API integration.`,
    contentPreview: 'Weather information agent with API integration...'
  },

  // Blog Posts
  {
    title: 'Network Protocol Design',
    href: '/blog/network-protocol-design',
    section: 'Blog',
    keywords: ['network', 'protocol', 'design', 'architecture', 'p2p'],
    content: `Designing ConnectOnion's network protocol for agent-to-agent communication. From complex P2P systems to simple HTTP. Design decisions, trade-offs, lessons learned. The journey to simplicity in distributed agent systems.`,
    contentPreview: 'The design journey of our agent network protocol...'
  },
  {
    title: 'Why We Chose "Trust"',
    href: '/blog/trust-keyword',
    section: 'Blog',
    keywords: ['trust', 'design', 'decision', 'naming', 'api'],
    content: `The story behind choosing "trust" as our authentication keyword. Evaluating 15+ alternatives, finding bidirectional meaning. API design philosophy, user-centric naming. How we pick names that make sense.`,
    contentPreview: 'The philosophy behind our API naming choices...'
  },
  {
    title: 'Why llm_do() Over run()',
    href: '/blog/llm-do',
    section: 'Blog',
    keywords: ['llm_do', 'run', 'api', 'design', 'naming'],
    content: `Why we renamed run() to llm_do(). User research showing confusion, clarity over convention. Making APIs that users understand intuitively. The importance of descriptive function names.`,
    contentPreview: 'Making API names that users understand...'
  },
  {
    title: 'Why input() Over run()',
    href: '/blog/input-method',
    section: 'Blog',
    keywords: ['input', 'run', 'api', 'design', 'user research'],
    content: `User research revealing 40% of users try agent.input() first. Designing APIs from user perspective, not system perspective. Natural language thinking in API design. How we discovered what users actually expect.`,
    contentPreview: 'Designing APIs that match user mental models...'
  },

  // Roadmap
  {
    title: 'Roadmap',
    href: '/roadmap',
    section: 'Roadmap',
    keywords: ['roadmap', 'future', 'plans', 'features'],
    content: `ConnectOnion development roadmap. Upcoming features: agent-to-agent protocol, distributed execution, advanced debugging tools. Community-driven development, open source contributions welcome.`,
    contentPreview: 'Future development plans for ConnectOnion...'
  }
]

// Helper function to search through content
export function searchContent(query: string): SearchableItem[] {
  if (!query.trim()) return []
  
  const q = query.toLowerCase()
  const results: Array<SearchableItem & { score: number }> = []
  
  searchIndex.forEach(item => {
    let score = 0
    
    // Title match (highest score)
    if (item.title.toLowerCase().includes(q)) {
      score += 20
    }
    
    // Exact keyword match (high score)
    if (item.keywords?.some(k => k.toLowerCase() === q)) {
      score += 15
    }
    
    // Partial keyword match (medium-high score)
    if (item.keywords?.some(k => k.toLowerCase().includes(q))) {
      score += 10
    }
    
    // Content match (medium score)
    const contentLower = item.content.toLowerCase()
    if (contentLower.includes(q)) {
      // Boost score based on frequency
      const matches = (contentLower.match(new RegExp(q, 'g')) || []).length
      score += Math.min(matches * 2, 8)
    }
    
    // Section match (low score)
    if (item.section.toLowerCase().includes(q)) {
      score += 2
    }
    
    if (score > 0) {
      results.push({ ...item, score })
    }
  })
  
  // Sort by score (highest first) and return without score
  return results
    .sort((a, b) => b.score - a.score)
    .map(({ score, ...item }) => item)
}

// Helper to get content preview with query highlighted
export function getHighlightedPreview(content: string, query: string, maxLength: number = 150): string {
  const q = query.toLowerCase()
  const contentLower = content.toLowerCase()
  const index = contentLower.indexOf(q)
  
  if (index === -1) {
    return content.slice(0, maxLength) + (content.length > maxLength ? '...' : '')
  }
  
  // Get text around the match
  const start = Math.max(0, index - 40)
  const end = Math.min(content.length, index + q.length + 110)
  
  let preview = content.slice(start, end)
  if (start > 0) preview = '...' + preview
  if (end < content.length) preview = preview + '...'
  
  return preview
}