// Utility to fetch and copy all documentation content for LLMs

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
    // Fetch the comprehensive LLM prompt markdown file
    const response = await fetch('/connectonion-llm-prompt.md');
    
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

/**
 * Copies a composed message that includes the user's question and the full
 * documentation, formatted for pasting into an LLM chat.
 */
export async function copyAllDocsWithQuestion(question: string): Promise<boolean> {
  try {
    const docs = await getAllDocsContent();
    const composed = `You are an expert assistant for the ConnectOnion framework.\n\nUser Question:\n${question || '(no question provided)'}\n\n---\nDocumentation (verbatim):\n${docs}`;
    await navigator.clipboard.writeText(composed);
    return true;
  } catch (error) {
    console.error('Failed to copy docs with question:', error);
    return false;
  }
}