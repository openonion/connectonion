/*
  @date: 2025-01-01
  @description: Tools Documentation Page
  
  DESIGN ISSUES TO FIX:
  
  1. **Missing Page Structure** (Priority: HIGH)
     - No breadcrumb navigation like other pages
     - Missing copy-all-content button (per CLAUDE.md requirement)
     - No table of contents for long content
     - Fix: Add navigation components, CopyMarkdownButton, floating TOC sidebar
  
  2. **Code Example Presentation** (Priority: HIGH)
     - Not using CodeWithResult component consistently
     - Results shown in comments instead of separate result panel
     - No visual separation between code and output
     - Fix: Use CodeWithResult for all examples, clear input/output separation
  
  3. **Content Organization** (Priority: MEDIUM)
     - Function tools vs class tools not clearly differentiated
     - Missing visual indicators for tool types
     - No quick reference or cheat sheet section
     - Fix: Add tabs/sections for tool types, add visual type indicators, create quick ref card
  
  4. **Learning Path** (Priority: MEDIUM)
     - Jumps directly into complex examples
     - No progression from simple to complex (violates CLAUDE.md)
     - Missing "common patterns" section
     - Fix: Restructure with beginner → intermediate → advanced flow, add patterns section
  
  5. **Interactive Elements** (Priority: LOW)
     - No try-it-yourself playground
     - Static code examples only
     - Missing links to working examples
     - Fix: Add interactive playground component, link to runnable examples
*/

'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Copy, Check, Code, Layers, Compass, Monitor } from 'lucide-react'
import CodeWithResult from '../../components/CodeWithResult'

export default function ToolsDocsPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const unused_pageContent = `# Tools

Build powerful, reusable function tools and stateful class tools. Typed signatures become schemas automatically; docstrings become human-friendly descriptions.

## Quick Start

\`\`\`python
from connectonion import Agent

def search(query: str) -> str:
    return f"Found results for {query}"

agent = Agent("helper", tools=[search], max_iterations=5)

print(agent.input("Find Python tutorials"))
\`\`\`

**Result:**
\`\`\`
>>> agent = Agent("helper", tools=[search], max_iterations=5)
>>> print(agent.input("Find Python tutorials"))

I'll search for Python tutorials.

Found results for Python tutorials

Based on my search, here are some excellent Python tutorials for you:
1. Official Python Tutorial - Great for beginners
2. Real Python - Comprehensive guides and examples  
3. Python.org Beginner's Guide - Step-by-step introduction
4. W3Schools Python Tutorial - Interactive examples
5. Codecademy Python Course - Hands-on learning
\`\`\`

## Function Tools

Use Python type hints as your interface. Keep signatures explicit and return structures when needed.

\`\`\`python
from typing import List
from connectonion import Agent

def top_k(query: str, k: int = 5) -> List[str]:
    """Return the top-k result titles for a query."""
    return [f"{i+1}. {query} result" for i in range(k)]

agent = Agent("helper", tools=[top_k], max_iterations=8)

print(agent.input("top_k('vector db', k=3)"))
\`\`\`

**Result:**
\`\`\`
>>> agent = Agent("helper", tools=[top_k], max_iterations=8)
>>> print(agent.input("top_k('vector db', k=3)"))

I'll search for the top 3 results about vector databases.

['1. vector db result', '2. vector db result', '3. vector db result']
\`\`\`

\`\`\`python
from typing import TypedDict, List

class SearchHit(TypedDict):
    title: str
    url: str
    score: float

def search_hits(query: str, k: int = 3) -> List[SearchHit]:
    """Structured results for chaining and UI."""
    return [
        {"title": f"{query} {i}", "url": f"https://example.com/{i}", "score": 0.9 - i*0.1}
        for i in range(k)
    ]
\`\`\`

**Result:**
\`\`\`
>>> search_hits("machine learning", k=2)
[{'title': 'machine learning 0', 'url': 'https://example.com/0', 'score': 0.9},
 {'title': 'machine learning 1', 'url': 'https://example.com/1', 'score': 0.8}]
\`\`\`

## Stateful Tools: Playwright

\`\`\`python
from typing import List, Optional
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
agent = Agent("helper", tools=browser, max_iterations=15)

# Try tools directly
print(browser.start())
print(browser.goto("https://example.com"))
print(browser.screenshot("example.png"))
print(browser.new_tab("docs"))
print(browser.goto("https://playwright.dev", tab="docs"))
print(browser.screenshot("docs.png", tab="docs"))
print(browser.list_tabs())
browser.close()
\`\`\`

**Result:**
\`\`\`
>>> browser = Browser()
>>> browser.start()
'Browser started'
>>> browser.goto("https://example.com")
'Example Domain'
>>> browser.new_tab("docs")
'Opened tab \'docs\''
>>> browser.switch_tab("docs")
'Switched to tab \'docs\''
>>> browser.goto("https://playwright.dev")
'Fast and reliable end-to-end testing for modern web apps | Playwright'
>>> browser.list_tabs()
['main', 'docs']
\`\`\`
`

  const quickStart = `from connectonion import Agent

def search(query: str) -> str:
    return f"Found results for {query}"

agent = Agent("helper", tools=[search], max_iterations=5)

print(agent.input("Find Python tutorials"))`

  const functionTool = `from typing import List
from connectonion import Agent

def top_k(query: str, k: int = 5) -> List[str]:
    """Return the top-k result titles for a query."""
    return [f"{i+1}. {query} result" for i in range(k)]

agent = Agent("helper", tools=[top_k], max_iterations=8)

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
agent = Agent("helper", tools=browser, max_iterations=15)

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
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
          <div>
            <h1 className="text-4xl font-bold text-white mb-3 flex items-center gap-3">
              <Code className="w-7 h-7 text-blue-400" /> Tools
            </h1>
            <p className="text-gray-300 max-w-2xl">
              Build powerful, reusable function tools and stateful class tools. Typed signatures become
              schemas automatically; docstrings become human-friendly descriptions.
            </p>
          </div>
          <div className="flex-shrink-0">
          </div>
        </div>
      </div>

      {/* Quick Start */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2"><Layers className="w-5 h-5 text-purple-400"/>Quick Start</h2>
        <CodeWithResult 
          code={quickStart}
          result={`>>> agent = Agent("helper", tools=[search], max_iterations=5)
>>> print(agent.input("Find Python tutorials"))

I'll search for Python tutorials.

Found results for Python tutorials

Based on my search, here are some excellent Python tutorials for you:
1. Official Python Tutorial - Great for beginners
2. Real Python - Comprehensive guides and examples  
3. Python.org Beginner's Guide - Step-by-step introduction
4. W3Schools Python Tutorial - Interactive examples
5. Codecademy Python Course - Hands-on learning`}
        />
      </section>

      {/* Function Tools */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2"><Code className="w-5 h-5 text-blue-400"/>Function Tools</h2>
        <p className="text-gray-300 mb-4">Use Python type hints as your interface. Keep signatures explicit and return structures when needed.</p>
        <div className="grid grid-cols-1 gap-6">
          <CodeWithResult 
            code={functionTool}
            result={`>>> agent = Agent("helper", tools=[top_k], max_iterations=8)
>>> print(agent.input("top_k('vector db', k=3)"))

I'll search for the top 3 results about vector databases.

['1. vector db result', '2. vector db result', '3. vector db result']`}
            className="mb-4"
          />

          <CodeWithResult 
            code={structuredReturn}
            result={`>>> search_hits("machine learning", k=2)
[{'title': 'machine learning 0', 'url': 'https://example.com/0', 'score': 0.9},
 {'title': 'machine learning 1', 'url': 'https://example.com/1', 'score': 0.8}]`}
            className="mb-4"
          />
        </div>
      </section>

      {/* Stateful Tools (Playwright) */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2"><Monitor className="w-5 h-5 text-emerald-400"/>Stateful Tools: Playwright</h2>
        <CodeWithResult 
          code={playwright}
          result={`>>> browser = Browser()
>>> browser.start()
'Browser started'
>>> browser.goto("https://example.com")
'Example Domain'
>>> browser.new_tab("docs")
'Opened tab \\'docs\\''
>>> browser.switch_tab("docs")
'Switched to tab \\'docs\\''
>>> browser.goto("https://playwright.dev")
'Fast and reliable end-to-end testing for modern web apps | Playwright'
>>> browser.list_tabs()
['main', 'docs']`}
        />
      </section>
    </div>
  )
}


