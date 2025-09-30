/**
 * @purpose Loads and searches markdown documentation files for the site's search functionality
 * @context Maps markdown files to their page routes, enables full-text search across docs
 * @llm-note Caches markdown content from /tutorials/, provides search with relevance scoring,
 *           extracts plain text from markdown for searching, generates match snippets
 */
interface MarkdownDocument {
  filename: string
  content: string
  title: string
  href: string
  section: string
}

// Mapping between markdown files and their corresponding pages
const MARKDOWN_TO_PAGE_MAP: Record<string, { href: string; section: string; title: string }> = {
  'cli.md': { href: '/cli', section: 'Getting Started', title: 'CLI Reference' },
  'quickstart.md': { href: '/quickstart', section: 'Getting Started', title: 'Quick Start' },
  'getting-started.md': { href: '/', section: 'Getting Started', title: 'Getting Started' },
  'tools.md': { href: '/tools', section: 'Core Concepts', title: 'Tools' },
  'models.md': { href: '/models', section: 'Core Concepts', title: 'Models' },
  'max_iterations.md': { href: '/max-iterations', section: 'Core Concepts', title: 'Max Iterations' },
  'max_iterations_guide.md': { href: '/max-iterations', section: 'Core Concepts', title: 'Max Iterations Guide' },
  'llm_do.md': { href: '/llm_do', section: 'Core Concepts', title: 'llm_do()' },
  'trust.md': { href: '/trust', section: 'Core Concepts', title: 'Trust' },
  'xray.md': { href: '/xray', section: 'Advanced', title: 'X-Ray Debugging' },
  'prompts.md': { href: '/prompts', section: 'Core Concepts', title: 'Prompts' },
  'examples.md': { href: '/examples', section: 'Examples', title: 'Examples' },
  'templates.md': { href: '/examples', section: 'Examples', title: 'Templates' },
  'api.md': { href: '/tools', section: 'Core Concepts', title: 'API Reference' },
  'principles.md': { href: '/roadmap', section: 'About', title: 'Design Principles' },
  'choosing-input-method.md': { href: '/blog/input-method', section: 'Blog', title: 'Why We Chose input()' },
  'choosing-llm-function-name.md': { href: '/blog/llm-do', section: 'Blog', title: 'Why We Chose llm_do()' },
  'choosing-trust-keyword.md': { href: '/blog/trust-keyword', section: 'Blog', title: 'Why We Chose trust()' },
  'threat-model.md': { href: '/threat-model', section: 'Advanced', title: 'Threat Model' },
  'network-protocol.md': { href: '/blog/network-protocol-design', section: 'Blog', title: 'Network Protocol Design' },
  'website-maintenance.md': { href: '/website-maintenance', section: 'Contributing', title: 'Website Maintenance Guide' }
}

// Cache for loaded markdown documents
let markdownCache: MarkdownDocument[] | null = null

export async function loadMarkdownDocuments(): Promise<MarkdownDocument[]> {
  // Return cached documents if already loaded
  if (markdownCache) {
    return markdownCache
  }

  const documents: MarkdownDocument[] = []
  
  // Get list of markdown files
  const markdownFiles = Object.keys(MARKDOWN_TO_PAGE_MAP)
  
  // Load each markdown file
  for (const filename of markdownFiles) {
    try {
      const response = await fetch(`/tutorials/${filename}`)
      if (response.ok) {
        const content = await response.text()
        const mapping = MARKDOWN_TO_PAGE_MAP[filename]
        
        documents.push({
          filename,
          content,
          title: mapping.title,
          href: mapping.href,
          section: mapping.section
        })
      }
    } catch (error) {
      console.warn(`Failed to load markdown file: ${filename}`, error)
    }
  }
  
  // Cache the loaded documents
  markdownCache = documents
  
  return documents
}

// Extract plain text from markdown content for searching
export function extractTextFromMarkdown(markdown: string): string {
  // Remove code blocks
  let text = markdown.replace(/```[\s\S]*?```/g, ' ')
  
  // Remove inline code
  text = text.replace(/`[^`]+`/g, ' ')
  
  // Remove markdown links but keep text
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
  
  // Remove markdown formatting
  text = text.replace(/[#*_~]/g, ' ')
  
  // Remove HTML tags
  text = text.replace(/<[^>]+>/g, ' ')
  
  // Normalize whitespace
  text = text.replace(/\s+/g, ' ').trim()
  
  return text
}

// Search through markdown documents
export async function searchMarkdownDocuments(query: string): Promise<MarkdownDocument[]> {
  const documents = await loadMarkdownDocuments()
  const normalizedQuery = query.toLowerCase()
  
  const results: Array<MarkdownDocument & { score: number }> = []
  
  for (const doc of documents) {
    const searchableText = extractTextFromMarkdown(doc.content).toLowerCase()
    const titleMatch = doc.title.toLowerCase().includes(normalizedQuery)
    
    // Calculate relevance score
    let score = 0
    
    // Title match is highest priority
    if (titleMatch) {
      score += 100
    }
    
    // Count occurrences in content
    const contentMatches = (searchableText.match(new RegExp(normalizedQuery, 'g')) || []).length
    score += contentMatches * 10
    
    // Check if query words appear in content
    const queryWords = normalizedQuery.split(/\s+/)
    for (const word of queryWords) {
      if (searchableText.includes(word)) {
        score += 5
      }
    }
    
    if (score > 0) {
      results.push({ ...doc, score })
    }
  }
  
  // Sort by score and return top results
  return results
    .sort((a, b) => b.score - a.score)
    .slice(0, 10)
}

// Get a snippet of text around a match
export function getMatchSnippet(content: string, query: string, maxLength: number = 150): string {
  const text = extractTextFromMarkdown(content)
  const lowerText = text.toLowerCase()
  const lowerQuery = query.toLowerCase()
  
  const matchIndex = lowerText.indexOf(lowerQuery)
  if (matchIndex === -1) {
    // If exact match not found, return beginning of content
    return text.slice(0, maxLength) + (text.length > maxLength ? '...' : '')
  }
  
  // Get context around the match
  const start = Math.max(0, matchIndex - 50)
  const end = Math.min(text.length, matchIndex + query.length + 100)
  
  let snippet = text.slice(start, end)
  
  // Add ellipsis if truncated
  if (start > 0) snippet = '...' + snippet
  if (end < text.length) snippet = snippet + '...'
  
  return snippet
}