// Search index for all documentation pages
// This provides full-text search across all content

export interface PageContent {
  title: string
  href: string
  content: string
  keywords: string[]
  section: string
}

// Page content database - comprehensive full-text search index
export const pageContentIndex: PageContent[] = [
  // Getting Started
  {
    title: 'Introduction',
    href: '/',
    section: 'Getting Started',
    keywords: ['intro', 'overview', 'start', 'begin', 'framework', 'agent', 'python', 'connectonion', 'connect', 'onion'],
    content: 'ConnectOnion is a Python framework for building AI agents. Create powerful agents with simple functions. No complex classes, just Python functions that work. The simplest way to build AI agents. Build agents in 60 seconds. No complex abstractions. Just write Python functions and let ConnectOnion handle the rest. Simple things simple, complex things possible. Best agent framework for Python developers. Alternative to LangChain, AutoGen, CrewAI.'
  },
  {
    title: 'Quick Start',
    href: '/quickstart',
    section: 'Getting Started',
    keywords: ['setup', 'install', 'begin', 'tutorial', 'pip', 'installation', 'getting started', 'first agent'],
    content: 'Get started with ConnectOnion in 60 seconds. Install with pip install connectonion. Create agents with simple Python functions. Build your first AI agent today. Write a function, create an agent, run it. No configuration files. No complex setup. From zero to working agent in under a minute. OpenAI API key required. Simple examples included. Step by step tutorial.'
  },
  {
    title: 'CLI Reference',
    href: '/cli',
    section: 'Getting Started',
    keywords: ['command', 'terminal', 'co', 'commands', 'init', 'scaffold', 'cli', 'co init', 'co run', 'co test'],
    content: 'ConnectOnion CLI commands. Use co init to scaffold new projects. Templates for meta-agent, playwright, and basic agents. Quick project setup with co command. Initialize projects, run agents, test tools, debug with xray. Command line interface for agent management. Terminal commands for ConnectOnion. co init creates new project. co run executes agent. co test validates tools. co xray enables debugging.'
  },
  {
    title: 'LLM Function',
    href: '/llm_do',
    section: 'Core Concepts',
    keywords: ['llm', 'llm_do', 'ai', 'model', 'openai', 'gpt', 'language model', 'direct llm'],
    content: 'Direct LLM interaction with llm_do function. Use LLMs without agents. Simple function for AI calls. Automatic retry logic. Streaming support. Error handling built-in. Perfect for simple AI tasks. No agent overhead. Direct OpenAI integration. Temperature and model control. System and user prompts. Response parsing. Token management.'
  },
  {
    title: 'Tools',
    href: '/tools',
    section: 'Core Concepts',
    keywords: ['tools', 'function', 'utility', 'actions', 'capabilities', 'tool creation', 'custom tools'],
    content: 'Convert Python functions to agent tools. Any function can be a tool. Automatic type inference. Parameter validation. Error handling. No classes needed. Tools from existing code. Function decorators. Tool schemas. OpenAI function calling. Tool results and errors. Async tool support. Tool composition.'
  },
  {
    title: 'System Prompts',
    href: '/prompts',
    section: 'Core Concepts',
    keywords: ['prompts', 'system prompt', 'template', 'personality', 'behavior', 'instructions', 'agent prompts'],
    content: 'Customize agent behavior with system prompts. Define agent personality. Set constraints and goals. Guide decision making. Markdown formatting. Dynamic prompts. Template variables. Conditional logic. Best practices. Prompt engineering. Agent instructions. Behavioral guidelines. Context injection.'
  },
  {
    title: 'Trust Parameter',
    href: '/trust',
    section: 'Core Concepts',
    keywords: ['trust', 'security', 'safety', 'permission', 'authentication', 'trust parameter', 'agent trust'],
    content: 'Control agent trust levels. Three trust modes: none, prompt, always. Security for multi-agent systems. Authentication between agents. Trust boundaries. Permission management. User confirmation. Automatic trust. Zero trust mode. Security best practices. Agent communication safety. Network security.'
  },

  // Core Concepts (continued)
  {
    title: 'max_iterations',
    href: '/max-iterations',
    section: 'Core Concepts',
    keywords: ['loop', 'limit', 'iteration', 'control', 'maximum', 'cycles', 'max_iterations', 'infinite loop', 'safety'],
    content: 'Control agent execution with max_iterations. Prevent infinite loops. Set iteration limits for different task complexity. Override per-request for flexibility. Essential safety parameter. Default is 10 iterations. Control costs and execution time. Prevent runaway agents. Set higher for complex tasks. Lower for simple queries. Dynamic adjustment possible. Best practice for production.'
  },
  {
    title: '@xray Decorator',
    href: '/xray',
    section: 'Core Concepts',
    keywords: ['debug', 'xray', 'decorator', 'trace', 'monitor', 'visibility', 'debugging', '@xray', 'visual debug'],
    content: 'Debug agents with @xray decorator. See inside agent execution. Trace tool calls and iterations. Visual execution flow with xray.trace(). Debug complex agent behaviors. Add @xray to any function for tracing. See every decision and tool call. Understand agent reasoning. Visual flow diagrams. Step-by-step execution tracking. Essential for debugging production agents. Real-time monitoring. Execution history.'
  },

  // Advanced Features
  {
    title: 'trace() Visual Flow',
    href: '/xray/trace',
    section: 'Advanced Features',
    keywords: ['trace', 'flow', 'visual', 'debug', 'execution', 'timeline', 'xray.trace', 'visual trace'],
    content: 'Visual execution timeline with trace(). See tool calls, timing, and results. Debug complex multi-step workflows. Performance profiling built-in. Real-time execution visualization. Step-by-step agent reasoning. Tool call timeline. Iteration tracking. Error visualization. Execution graphs. Performance metrics.'
  },
  {
    title: 'Prompt Formats',
    href: '/prompts/formats',
    section: 'Advanced Features',
    keywords: ['format', 'prompt', 'template', 'syntax', 'markdown', 'yaml', 'jinja', 'formatting'],
    content: 'Different prompt formats supported. Markdown for readability. YAML for structure. Plain text for simplicity. Jinja2 templates for dynamic content. Choose the right format for your needs. Interactive demo available. Template variables. Conditional logic. Loop constructs. Best practices for prompt engineering.'
  },

  // Security
  {
    title: 'Threat Model',
    href: '/threat-model',
    section: 'Security',
    keywords: ['threat', 'security', 'model', 'safety', 'protection', 'vulnerability', 'risk'],
    content: 'Understanding ConnectOnion security model. Tool execution safety. Prompt injection prevention. Trust boundaries. Security considerations for production. Best practices for secure agents. Threat analysis. Risk mitigation. Security patterns. Defense in depth. Agent sandboxing.'
  },

  // Examples
  {
    title: 'All Examples',
    href: '/examples',
    section: 'Examples',
    keywords: ['examples', 'samples', 'code', 'demo', 'browse', 'gallery'],
    content: 'Browse all ConnectOnion examples. Hello World, Calculator, Weather Bot, and more. Complete working examples with explanations. Copy and modify for your needs. Learn by example. Best practices demonstrated. Production patterns. Common use cases.'
  },
  {
    title: 'Hello World',
    href: '/examples/hello-world',
    section: 'Examples',
    keywords: ['hello', 'world', 'basic', 'simple', 'beginner', 'first', 'starter'],
    content: 'Simplest ConnectOnion agent example. Create an agent that responds to greetings. Perfect starting point for beginners. Learn the basics in 5 lines of code. Minimal agent setup. Basic tool creation. Simple interactions.'
  },
  {
    title: 'Calculator',
    href: '/examples/calculator',
    section: 'Examples',
    keywords: ['calculator', 'math', 'compute', 'calculation', 'beginner', 'arithmetic'],
    content: 'Build a calculator agent with mathematical tools. Addition, subtraction, multiplication, division. Shows tool creation and integration. Great for learning tool patterns. Multiple tools working together. Error handling. Type validation.'
  },
  {
    title: 'Weather Bot',
    href: '/examples/weather-bot',
    section: 'Examples',
    keywords: ['weather', 'bot', 'api', 'intermediate', 'forecast', 'temperature'],
    content: 'Weather information agent with API integration. Handle location queries. Provide forecasts. Intermediate example showing external API usage. HTTP requests. Data parsing. Error handling. User interaction patterns.'
  },
  {
    title: 'More Examples',
    href: '/examples/more',
    section: 'Examples',
    keywords: ['more', 'advanced', 'examples', 'complex', 'production'],
    content: 'Advanced ConnectOnion examples. Multi-agent systems. Browser automation. Data processing. Production patterns. Complex workflows. Real-world applications.'
  },

  // Blog
  {
    title: 'All Posts',
    href: '/blog',
    section: 'Blog',
    keywords: ['blog', 'posts', 'articles', 'updates', 'news'],
    content: 'ConnectOnion blog posts. Design decisions, architecture insights, best practices. Learn about our development process. Technical deep dives. Community updates.'
  },
  {
    title: 'Network Protocol Design',
    href: '/blog/network-protocol-design',
    section: 'Blog',
    keywords: ['network', 'protocol', 'design', 'architecture', 'p2p', 'distributed'],
    content: 'Designing the ConnectOnion network protocol. From complex P2P to simple HTTP. Design journey and lessons learned. Protocol evolution. Simplicity wins. Agent communication architecture. Distributed systems challenges.'
  },
  {
    title: 'Why We Chose "Trust"',
    href: '/blog/trust-keyword',
    section: 'Blog',
    keywords: ['trust', 'design', 'decision', 'naming', 'api', 'keyword'],
    content: 'The story behind choosing trust as our authentication keyword. Evaluating 15+ alternatives. Finding bidirectional meaning. API design philosophy. User-centric naming. Making intuitive APIs.'
  },
  {
    title: 'Why llm_do() Over run()',
    href: '/blog/llm-do',
    section: 'Blog',
    keywords: ['llm_do', 'run', 'api', 'design', 'naming', 'clarity'],
    content: 'Why we renamed run() to llm_do(). User research showing confusion. Clarity over convention. Making APIs that users understand. Descriptive function names. Breaking from tradition for usability.'
  },
  {
    title: 'Why input() Over run()',
    href: '/blog/input-method',
    section: 'Blog',
    keywords: ['input', 'run', 'api', 'design', 'user research', 'mental model'],
    content: 'User research revealing 40% try agent.input() first. Designing from user perspective. Natural language thinking in APIs. Matching user mental models. Data-driven API design.'
  },

  // Roadmap
  {
    title: 'Roadmap',
    href: '/roadmap',
    section: 'Roadmap',
    keywords: ['security', 'threat', 'risk', 'safety', 'vulnerability', 'attack'],
    content: 'Security considerations for AI agents. Threat modeling for agent systems. Mitigation strategies. Best practices for secure agent deployment.'
  },

  // Roadmap
  {
    title: 'Coming Soon Features',
    href: '/roadmap',
    section: 'Roadmap',
    keywords: ['roadmap', 'future', 'upcoming', 'features', 'soon', 'planned'],
    content: 'Upcoming ConnectOnion features. Multi-agent coordination. Network protocol implementation. Enhanced debugging tools. Community requested features.'
  }
]

// Enhanced search function that searches across all content
export function performFullTextSearch(query: string): PageContent[] {
  if (!query.trim()) return []

  const q = query.toLowerCase()
  const words = q.split(/\s+/).filter(w => w.length > 0)
  
  const results = pageContentIndex.map(page => {
    let score = 0
    const matches: string[] = []

    // Title match (highest priority)
    const titleLower = page.title.toLowerCase()
    if (titleLower === q) {
      score += 100 // Exact match
      matches.push('exact-title')
    } else if (titleLower.includes(q)) {
      score += 50 // Contains full query
      matches.push('title')
    } else {
      // Check each word
      words.forEach(word => {
        if (titleLower.includes(word)) {
          score += 20
          matches.push('title-word')
        }
      })
    }

    // URL/href match
    const hrefLower = page.href.toLowerCase()
    if (hrefLower.includes(q)) {
      score += 30
      matches.push('url')
    }

    // Keywords match
    page.keywords.forEach(keyword => {
      if (keyword.includes(q)) {
        score += 25
        matches.push('keyword')
      } else {
        words.forEach(word => {
          if (keyword.includes(word)) {
            score += 10
            matches.push('keyword-word')
          }
        })
      }
    })

    // Content match (full text search)
    const contentLower = page.content.toLowerCase()
    if (contentLower.includes(q)) {
      score += 15
      matches.push('content')
    } else {
      // Check each word in content
      words.forEach(word => {
        if (contentLower.includes(word)) {
          score += 5
          matches.push('content-word')
        }
      })
    }

    // Section match
    if (page.section.toLowerCase().includes(q)) {
      score += 8
      matches.push('section')
    }

    return {
      page,
      score,
      matches: [...new Set(matches)] // Remove duplicates
    }
  })
    .filter(result => result.score > 0)
    .sort((a, b) => b.score - a.score)
    .map(result => result.page)

  return results
}