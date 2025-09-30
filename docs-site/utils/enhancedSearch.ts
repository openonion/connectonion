/**
 * @purpose Advanced search engine with fuzzy matching, typo tolerance, and synonym support
 * @context Powers site-wide search functionality with intelligent matching algorithms
 * @llm-note Uses pageContentIndex from searchIndex.ts, implements Levenshtein distance for typos,
 *           provides synonym expansion, stem matching, and relevance scoring for search results
 */

import { pageContentIndex, PageContent } from './searchIndex'

interface SearchMatch {
  page: PageContent
  score: number
  matches: MatchDetail[]
  snippet?: string
}

interface MatchDetail {
  type: 'exact' | 'fuzzy' | 'partial' | 'typo' | 'stem' | 'synonym'
  field: 'title' | 'content' | 'keywords' | 'url' | 'section'
  term: string
  position?: number
}

// Common synonyms and related terms for better search
const SYNONYMS: Record<string, string[]> = {
  'start': ['begin', 'init', 'setup', 'install', 'quickstart'],
  'begin': ['start', 'init', 'setup', 'install', 'quickstart'],
  'debug': ['trace', 'xray', 'monitor', 'inspect', 'troubleshoot'],
  'trace': ['debug', 'xray', 'monitor', 'track', 'follow'],
  'tool': ['function', 'utility', 'action', 'capability', 'method'],
  'function': ['tool', 'method', 'action', 'capability'],
  'agent': ['bot', 'assistant', 'ai', 'model'],
  'bot': ['agent', 'assistant', 'ai'],
  'run': ['execute', 'start', 'launch', 'begin', 'input'],
  'execute': ['run', 'start', 'launch', 'perform'],
  'config': ['configuration', 'setup', 'settings', 'options'],
  'configuration': ['config', 'setup', 'settings', 'options'],
  'auth': ['authentication', 'trust', 'security', 'permission'],
  'authentication': ['auth', 'trust', 'security', 'permission'],
  'doc': ['documentation', 'docs', 'guide', 'tutorial'],
  'documentation': ['doc', 'docs', 'guide', 'tutorial'],
  'example': ['sample', 'demo', 'tutorial', 'guide'],
  'sample': ['example', 'demo', 'tutorial'],
  'error': ['bug', 'issue', 'problem', 'exception', 'failure'],
  'bug': ['error', 'issue', 'problem', 'defect'],
  'api': ['interface', 'endpoint', 'function', 'method'],
  'interface': ['api', 'ui', 'frontend'],
  'llm': ['ai', 'gpt', 'model', 'language model', 'openai'],
  'ai': ['llm', 'ml', 'machine learning', 'artificial intelligence'],
  'test': ['testing', 'unit test', 'integration test', 'verify'],
  'testing': ['test', 'qa', 'quality', 'verification'],
}

// Common typos and variations
const TYPO_MAP: Record<string, string[]> = {
  'iteration': ['iterration', 'itteration', 'iteraton'],
  'xray': ['x-ray', 'xrey', 'x ray'],
  'debug': ['debag', 'debugg', 'debig'],
  'agent': ['agnet', 'agant', 'aget'],
  'function': ['funtion', 'functoin', 'fucntion'],
  'connect': ['conect', 'connct', 'connnect'],
  'onion': ['onoin', 'oinon', 'union'],
  'playwright': ['playwrite', 'playwrght', 'play wright'],
  'trust': ['turst', 'trsut', 'truts'],
  'prompt': ['promt', 'propt', 'promtp'],
  'tool': ['tol', 'toool', 'toop'],
  'config': ['confg', 'cofig', 'conifg'],
  'install': ['instal', 'intall', 'installl'],
  'python': ['pyton', 'pythoon', 'pythn'],
}

// Levenshtein distance for fuzzy matching
function levenshteinDistance(str1: string, str2: string): number {
  const m = str1.length
  const n = str2.length
  const dp: number[][] = Array(m + 1).fill(null).map(() => Array(n + 1).fill(0))

  for (let i = 0; i <= m; i++) dp[i][0] = i
  for (let j = 0; j <= n; j++) dp[0][j] = j

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (str1[i - 1] === str2[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1]
      } else {
        dp[i][j] = Math.min(
          dp[i - 1][j] + 1,    // deletion
          dp[i][j - 1] + 1,    // insertion
          dp[i - 1][j - 1] + 1 // substitution
        )
      }
    }
  }

  return dp[m][n]
}

// Check if word is a fuzzy match (allows 1-2 character differences based on length)
function isFuzzyMatch(word1: string, word2: string, threshold: number = 0.8): boolean {
  if (Math.abs(word1.length - word2.length) > 3) return false
  
  const distance = levenshteinDistance(word1.toLowerCase(), word2.toLowerCase())
  const maxLength = Math.max(word1.length, word2.length)
  const similarity = 1 - (distance / maxLength)
  
  return similarity >= threshold
}

// Extract keywords from text using simple NLP
function extractKeywords(text: string): string[] {
  // Remove common stop words
  const stopWords = new Set([
    'the', 'is', 'at', 'which', 'on', 'a', 'an', 'as', 'are', 'was',
    'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
    'would', 'could', 'should', 'may', 'might', 'must', 'can', 'could',
    'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
    'we', 'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
    'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
    'some', 'such', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
    'just', 'in', 'of', 'to', 'for', 'with', 'about', 'into', 'through',
    'during', 'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off',
    'over', 'under', 'and', 'or', 'but', 'nor', 'not', 'no', 'yes'
  ])

  const words = text.toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .split(/\s+/)
    .filter(word => word.length > 2 && !stopWords.has(word))

  return [...new Set(words)]
}

// Generate n-grams for partial matching
function generateNGrams(text: string, n: number = 3): string[] {
  const ngrams: string[] = []
  const cleaned = text.toLowerCase().replace(/[^\w]/g, '')
  
  for (let i = 0; i <= cleaned.length - n; i++) {
    ngrams.push(cleaned.substr(i, n))
  }
  
  return ngrams
}

// Check for synonym matches
function findSynonyms(term: string): string[] {
  const synonyms: string[] = []
  const termLower = term.toLowerCase()
  
  // Direct synonym lookup
  if (SYNONYMS[termLower]) {
    synonyms.push(...SYNONYMS[termLower])
  }
  
  // Reverse lookup
  for (const [key, values] of Object.entries(SYNONYMS)) {
    if (values.includes(termLower) && !synonyms.includes(key)) {
      synonyms.push(key)
    }
  }
  
  return synonyms
}

// Check for typo corrections
function findTypoCorrections(term: string): string[] {
  const corrections: string[] = []
  const termLower = term.toLowerCase()
  
  // Direct typo lookup
  for (const [correct, typos] of Object.entries(TYPO_MAP)) {
    if (typos.includes(termLower)) {
      corrections.push(correct)
    }
  }
  
  // Check if term is the correct form
  if (TYPO_MAP[termLower]) {
    corrections.push(termLower)
  }
  
  return corrections
}

// Generate snippet with highlighted matches
function generateSnippet(content: string, query: string, maxLength: number = 150): string {
  const queryLower = query.toLowerCase()
  const contentLower = content.toLowerCase()
  
  const index = contentLower.indexOf(queryLower)
  if (index === -1) {
    // If exact match not found, look for any query word
    const words = queryLower.split(/\s+/)
    for (const word of words) {
      const wordIndex = contentLower.indexOf(word)
      if (wordIndex !== -1) {
        const start = Math.max(0, wordIndex - 50)
        const end = Math.min(content.length, wordIndex + word.length + 100)
        return '...' + content.substring(start, end) + '...'
      }
    }
    return content.substring(0, maxLength) + '...'
  }
  
  const start = Math.max(0, index - 50)
  const end = Math.min(content.length, index + query.length + 100)
  
  let snippet = content.substring(start, end)
  if (start > 0) snippet = '...' + snippet
  if (end < content.length) snippet = snippet + '...'
  
  return snippet
}

// Enhanced search function with multiple strategies
export function performEnhancedSearch(query: string): SearchMatch[] {
  if (!query.trim()) return []

  const queryLower = query.toLowerCase()
  const queryWords = queryLower.split(/\s+/).filter(w => w.length > 0)
  const queryNGrams = generateNGrams(queryLower, 3)
  
  // Find synonyms and typo corrections for each query word
  const expandedTerms = new Set<string>(queryWords)
  queryWords.forEach(word => {
    findSynonyms(word).forEach(syn => expandedTerms.add(syn))
    findTypoCorrections(word).forEach(correction => expandedTerms.add(correction))
  })

  const results: SearchMatch[] = []

  // Score each page
  pageContentIndex.forEach(page => {
    let score = 0
    const matches: MatchDetail[] = []
    
    const titleLower = page.title.toLowerCase()
    const contentLower = page.content.toLowerCase()
    const urlLower = page.href.toLowerCase()
    const sectionLower = page.section.toLowerCase()
    const keywordsLower = page.keywords.map(k => k.toLowerCase())
    
    // 1. Exact query match in title (highest score)
    if (titleLower === queryLower) {
      score += 200
      matches.push({ type: 'exact', field: 'title', term: query })
    } else if (titleLower.includes(queryLower)) {
      score += 100
      matches.push({ type: 'partial', field: 'title', term: query })
    }

    // 2. Exact query match in URL
    if (urlLower.includes(queryLower.replace(/\s+/g, '-'))) {
      score += 80
      matches.push({ type: 'exact', field: 'url', term: query })
    }

    // 3. Check each query word
    queryWords.forEach(word => {
      // Title matches
      if (titleLower.includes(word)) {
        score += 40
        matches.push({ type: 'partial', field: 'title', term: word })
      }
      
      // URL matches
      if (urlLower.includes(word)) {
        score += 30
        matches.push({ type: 'partial', field: 'url', term: word })
      }
      
      // Keyword matches
      keywordsLower.forEach(keyword => {
        if (keyword === word) {
          score += 35
          matches.push({ type: 'exact', field: 'keywords', term: word })
        } else if (keyword.includes(word)) {
          score += 20
          matches.push({ type: 'partial', field: 'keywords', term: word })
        }
      })
      
      // Content matches
      const contentWords = extractKeywords(contentLower)
      if (contentWords.includes(word)) {
        score += 15
        matches.push({ type: 'partial', field: 'content', term: word })
      }
      
      // Section matches
      if (sectionLower.includes(word)) {
        score += 10
        matches.push({ type: 'partial', field: 'section', term: word })
      }
    })

    // 4. Fuzzy matching for typos
    queryWords.forEach(queryWord => {
      // Fuzzy match in title
      const titleWords = titleLower.split(/\s+/)
      titleWords.forEach(titleWord => {
        if (isFuzzyMatch(queryWord, titleWord, 0.75)) {
          score += 25
          matches.push({ type: 'fuzzy', field: 'title', term: queryWord })
        }
      })
      
      // Fuzzy match in keywords
      keywordsLower.forEach(keyword => {
        if (isFuzzyMatch(queryWord, keyword, 0.75)) {
          score += 15
          matches.push({ type: 'fuzzy', field: 'keywords', term: queryWord })
        }
      })
    })

    // 5. Synonym matching
    expandedTerms.forEach(term => {
      if (queryWords.includes(term)) return // Skip original terms
      
      if (titleLower.includes(term)) {
        score += 20
        matches.push({ type: 'synonym', field: 'title', term })
      }
      
      if (keywordsLower.some(k => k.includes(term))) {
        score += 12
        matches.push({ type: 'synonym', field: 'keywords', term })
      }
      
      if (contentLower.includes(term)) {
        score += 8
        matches.push({ type: 'synonym', field: 'content', term })
      }
    })

    // 6. N-gram matching for partial words
    let ngramMatches = 0
    queryNGrams.forEach(ngram => {
      if (titleLower.includes(ngram)) ngramMatches++
      if (contentLower.includes(ngram)) ngramMatches += 0.5
    })
    if (ngramMatches > 0) {
      score += Math.min(ngramMatches * 3, 30)
    }

    // 7. Boost for multiple word matches
    const uniqueMatches = new Set(matches.map(m => m.term)).size
    if (uniqueMatches > 1) {
      score *= (1 + uniqueMatches * 0.1) // 10% boost per unique match
    }

    // 8. Recency/importance boost for certain pages
    if (page.href === '/quickstart' || page.href === '/') {
      score *= 1.2 // Boost important pages
    }

    if (score > 0) {
      results.push({
        page,
        score: Math.round(score),
        matches,
        snippet: generateSnippet(page.content, query)
      })
    }
  })

  // Sort by score and return
  return results.sort((a, b) => b.score - a.score)
}

// Export a simplified version for the sidebar
export function searchPages(query: string): PageContent[] {
  const results = performEnhancedSearch(query)
  return results.map(r => r.page)
}