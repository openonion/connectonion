/**
 * @purpose Fetches and copies comprehensive ConnectOnion documentation to clipboard for AI assistants
 * @context Used by HomePage vibe coding section to provide one-click documentation copying
 * @llm-note Fetches co-vibecoding-principles-docs-contexts-all-in-one.md from public folder,
 *           falls back to DEFAULT_CONTENT if fetch fails, enables AI-assisted development workflow
 */

// Default content in case fetch fails
const DEFAULT_CONTENT = `# ConnectOnion Framework - Quick Reference

A simple Python framework for creating AI agents with behavior tracking.

## Quick Start
\`\`\`python
from connectonion import Agent

def search(query: str) -> str:
    return f"Found information about {query}"

agent = Agent("my_assistant", tools=[search])
result = agent.input("Search for Python tutorials")
\`\`\`

## Installation
\`\`\`bash
pip install connectonion
\`\`\`

For complete documentation, visit: https://connectonion.com
`;

export async function getAllDocsContent(): Promise<string> {
  try {
    // Fetch the comprehensive VibeCoding principles, docs and contexts all-in-one markdown file
    const response = await fetch('/co-vibecoding-principles-docs-contexts-all-in-one.md');
    
    if (!response.ok) {
      console.warn('Failed to fetch documentation file, using default content');
      return DEFAULT_CONTENT;
    }
    
    const content = await response.text();
    return content;
  } catch (error) {
    console.error('Error fetching documentation:', error);
    return DEFAULT_CONTENT;
  }
}

export async function copyAllDocsToClipboard(): Promise<boolean> {
  try {
    const content = await getAllDocsContent();
    await navigator.clipboard.writeText(content);
    return true;
  } catch (error) {
    console.error('Failed to copy docs to clipboard:', error);
    return false;
  }
}