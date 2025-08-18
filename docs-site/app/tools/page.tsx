'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Copy, Check, Code, Layers, Compass, Monitor } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

export default function ToolsDocsPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const quickStart = `from connectonion import Agent

def search(query: str) -> str:
    return f"Found results for {query}"

agent = Agent("helper", tools=[search])

print(agent.input("Find Python tutorials"))`

  const functionTool = `from typing import List
from connectonion import Agent

def top_k(query: str, k: int = 5) -> List[str]:
    """Return the top-k result titles for a query."""
    return [f"{i+1}. {query} result" for i in range(k)]

agent = Agent("helper", tools=[top_k])

print(agent.input("top_k('vector db', k=3)"))`

  const structuredReturn = `from typing import TypedDict, List

class SearchHit(TypedDict):
    title: str
    url: str
    score: float

def search_hits(query: str, k: int = 3) -> List[SearchHit]:
    """Structured results for chaining and UI."""
    return [
        {"title": f"{query} {i}", "url": f"https://example.com/{i}", "score": 0.9 - i*0.1}
        for i in range(k)
    ]`

  const playwright = `from typing import List, Optional
from connectonion import Agent

try:
    from playwright.sync_api import sync_playwright, Page
except ImportError:
    raise SystemExit("Install Playwright: pip install playwright && playwright install")

class Browser:
    """Persistent browser session with navigation, screenshots, and tab control."""
    def __init__(self):
        self._p = None
        self._browser = None
        self._pages: dict[str, Page] = {}
        self._active_tab: Optional[str] = None

    def start(self, headless: bool = True) -> str:
        self._p = sync_playwright().start()
        self._browser = self._p.chromium.launch(headless=headless)
        self._pages["main"] = self._browser.new_page()
        self._active_tab = "main"
        return "Browser started"

    def new_tab(self, name: str) -> str:
        if not self._browser:
            return "Error: Browser not started"
        if name in self._pages:
            return f"Tab '{name}' already exists"
        self._pages[name] = self._browser.new_page()
        self._active_tab = name
        return f"Opened tab '{name}'"

    def list_tabs(self) -> List[str]:
        return list(self._pages.keys())

    def switch_tab(self, name: str) -> str:
        if name not in self._pages:
            return f"Error: No tab named '{name}'"
        self._active_tab = name
        return f"Switched to tab '{name}'"

    def goto(self, url: str, tab: Optional[str] = None) -> str:
        if not self._pages:
            return "Error: Browser not started"
        target = tab or self._active_tab
        page = self._pages[target]
        page.goto(url)
        return page.title()

    def screenshot(self, path: Optional[str] = None, tab: Optional[str] = None) -> str:
        if not self._pages:
            return "Error: Browser not started"
        target = tab or self._active_tab
        page = self._pages[target]
        filename = path or f"{target}_screenshot.png"
        page.screenshot(path=filename)
        return filename

    def close(self) -> None:
        for page in list(self._pages.values()):
            page.close()
        self._pages.clear()
        if self._browser:
            self._browser.close()
        if self._p:
            self._p.stop()

browser = Browser()
agent = Agent("helper", tools=browser)

# Try tools directly
print(browser.start())
print(browser.goto("https://example.com"))
print(browser.screenshot("example.png"))
print(browser.new_tab("docs"))
print(browser.goto("https://playwright.dev", tab="docs"))
print(browser.screenshot("docs.png", tab="docs"))
print(browser.list_tabs())
browser.close()`

  return (
    <div className="max-w-5xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Header */}
      <div className="mb-10">
        <div className="flex items-center gap-2 text-sm text-gray-400 mb-3">
          <Link href="/" className="hover:text-white transition-colors">Home</Link>
          <span>/</span>
          <span className="text-white">Tools</span>
        </div>
        <h1 className="text-4xl font-bold text-white mb-3 flex items-center gap-3">
          <Code className="w-7 h-7 text-blue-400" /> Tools
        </h1>
        <p className="text-gray-300 max-w-2xl">
          Build powerful, reusable function tools and stateful class tools. Typed signatures become
          schemas automatically; docstrings become human-friendly descriptions.
        </p>
      </div>

      {/* Quick Start */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2"><Layers className="w-5 h-5 text-purple-400"/>Quick Start</h2>
        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
            <span className="text-sm text-gray-300 font-mono">quick_tool.py</span>
            <button
              onClick={() => copyToClipboard(quickStart, 'quick')}
              className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-700"
            >
              {copiedId === 'quick' ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <div className="p-6">
            <SyntaxHighlighter language="python" style={vscDarkPlus} customStyle={{ background: 'transparent', padding: 0, margin: 0, fontSize: '0.9rem', lineHeight: '1.6' }}>
              {quickStart}
            </SyntaxHighlighter>
          </div>
        </div>
      </section>

      {/* Function Tools */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2"><Code className="w-5 h-5 text-blue-400"/>Function Tools</h2>
        <p className="text-gray-300 mb-4">Use Python type hints as your interface. Keep signatures explicit and return structures when needed.</p>
        <div className="grid grid-cols-1 gap-6">
          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
              <span className="text-sm text-gray-300 font-mono">top_k.py</span>
              <button onClick={() => copyToClipboard(functionTool, 'func')} className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-700">
                {copiedId === 'func' ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
            <div className="p-6">
              <SyntaxHighlighter language="python" style={vscDarkPlus} customStyle={{ background: 'transparent', padding: 0, margin: 0, fontSize: '0.85rem' }}>
                {functionTool}
              </SyntaxHighlighter>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
              <span className="text-sm text-gray-300 font-mono">structured.py</span>
              <button onClick={() => copyToClipboard(structuredReturn, 'structured')} className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-700">
                {copiedId === 'structured' ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
            <div className="p-6">
              <SyntaxHighlighter language="python" style={vscDarkPlus} customStyle={{ background: 'transparent', padding: 0, margin: 0, fontSize: '0.85rem' }}>
                {structuredReturn}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>
      </section>

      {/* Stateful Tools (Playwright) */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2"><Monitor className="w-5 h-5 text-emerald-400"/>Stateful Tools: Playwright</h2>
        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
            <span className="text-sm text-gray-300 font-mono">browser_tools.py</span>
            <button
              onClick={() => copyToClipboard(playwright, 'playwright')}
              className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-700"
            >
              {copiedId === 'playwright' ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <div className="p-6">
            <SyntaxHighlighter language="python" style={vscDarkPlus} customStyle={{ background: 'transparent', padding: 0, margin: 0, fontSize: '0.8rem' }}>
              {playwright}
            </SyntaxHighlighter>
          </div>
        </div>
      </section>
    </div>
  )
}


