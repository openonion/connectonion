# Sync Browser Agent Features from Standalone Browser-Agent

## Summary

The ConnectOnion CLI browser agent (`connectonion/cli/browser_agent/`) and the standalone `browser-agent` project have diverged. This issue tracks advanced features from the standalone version that should be adopted to enable complex automation workflows.

## Current State

- **CLI Version**: Simple, reliable browser automation with good UX
- **Standalone**: Multi-agent architecture, deep research, advanced automation features
- **Last Migration**: Form filling methods removed (Feb 2025) to match standalone philosophy
- **Last Sync**: Never systematically synced

## Features to Adopt from Standalone Browser-Agent

### 1. Deep Research System
**Priority: High**

**Feature:** Multi-step research workflows with specialized sub-agent

**Current:** Single agent with simple automation
**Proposed:** Add deep research capability as optional advanced feature

**Implementation:**
```python
# In connectonion/cli/browser_agent/deep_research.py (NEW FILE)
from connectonion import Agent

def perform_deep_research(topic: str, browser_instance) -> str:
    """Perform deep multi-step research on a topic.

    Spawns a specialized research agent that shares the browser session.
    Creates research_notes.md and research_results.md files.

    Args:
        topic: Research topic or question
        browser_instance: Shared BrowserAutomation instance

    Returns:
        Summary of research findings
    """
    research_agent = Agent(
        name="deep_research_agent",
        model="co/gemini-2.5-pro",
        system_prompt=Path(__file__).parent / "prompts" / "deep_research.md",
        tools=[browser_instance],  # Share browser session
        max_iterations=50
    )

    result = research_agent.input(f"Research this topic: {topic}")
    return result
```

**Files to create:**
- `connectonion/cli/browser_agent/deep_research.py`
- `connectonion/cli/browser_agent/prompts/deep_research.md`

**Files to modify:**
- `connectonion/cli/browser_agent/browser.py` - Add `perform_deep_research` to tools
- `connectonion/cli/browser_agent/__init__.py` - Export new function

**Benefits:**
- Complex multi-page research workflows
- Specialized agent for focused tasks
- File-based research note management

---

### 2. Google Search Integration
**Priority: Medium**

**Feature:** Built-in Google search with structured result extraction

**Implementation:**
```python
# Add to BrowserAutomation class in browser.py
@xray
def google_search(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Performs a web search on Google and extracts results.

    Args:
        query: Search query
        max_results: Maximum number of results to extract

    Returns:
        List of dicts with 'title' and 'url' keys
    """
    if not self.page:
        return []

    self.go_to(f"https://www.google.com/search?q={query}")
    self.page.wait_for_load_state('networkidle')

    h3_elements = self.page.locator("h3").all()
    results = []
    for h3_element in h3_elements[:max_results]:
        parent_link = h3_element.locator("xpath=./ancestor::a").first
        if parent_link.count() > 0:
            title = h3_element.inner_text()
            url = parent_link.get_attribute("href")
            if title and url and url.startswith("http"):
                results.append({"title": title, "url": url})

    return results
```

**Files to modify:**
- `connectonion/cli/browser_agent/browser.py` (add method to BrowserAutomation class)

**Benefits:**
- Enables search-based research workflows
- Returns structured data for LLM processing
- Foundation for web research automation

---

### 3. HTML Analysis Tools
**Priority: Medium**

**Feature:** AI-powered HTML content analysis with custom objectives

**Implementation:**
```python
# Add to BrowserAutomation class in browser.py
@xray
def analyze_html(self, html_content: str, objective: str) -> str:
    """Analyzes HTML content based on a given objective.

    Args:
        html_content: HTML to analyze
        objective: What to look for or analyze

    Returns:
        AI analysis result
    """
    class AnalysisResult(BaseModel):
        analysis: str = Field(..., description="Analysis result")

    result = llm_do(
        f"Analyze this HTML based on: {objective}\n\nHTML:\n{html_content}",
        output=AnalysisResult,
        model="co/gemini-2.5-flash",
        temperature=0.2
    )
    return result.analysis

@xray
def explore(self, url: str, objective: str) -> str:
    """Navigate to URL and analyze it based on objective.

    One-shot navigation + analysis convenience method.

    Args:
        url: URL to navigate to
        objective: What to analyze or look for

    Returns:
        Analysis result
    """
    self.go_to(url)
    return self.analyze_html(self.page.content(), objective)
```

**Files to modify:**
- `connectonion/cli/browser_agent/browser.py` (add methods)

**Benefits:**
- AI-powered content understanding
- Objective-driven page analysis
- Reduces need for manual element selection

---

### 4. File Management Tools
**Priority: Low**

**Feature:** Read/write research notes and results

**Implementation:**
```python
# Create new file: connectonion/cli/browser_agent/file_tools.py
from pathlib import Path
from typing import Optional

class FileTools:
    """File operations for research and data collection."""

    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path.cwd()

    def write_file(self, filename: str, content: str) -> str:
        """Write content to a file."""
        path = self.base_dir / filename
        path.write_text(content)
        return f"Wrote {len(content)} characters to {filename}"

    def read_file(self, filename: str) -> str:
        """Read content from a file."""
        path = self.base_dir / filename
        if not path.exists():
            return f"File not found: {filename}"
        return path.read_text()

    def append_file(self, filename: str, content: str) -> str:
        """Append content to a file."""
        path = self.base_dir / filename
        with path.open('a') as f:
            f.write(content)
        return f"Appended to {filename}"
```

**Files to create:**
- `connectonion/cli/browser_agent/file_tools.py`

**Files to modify:**
- `connectonion/cli/browser_agent/browser.py` - Optionally include FileTools in tools

**Benefits:**
- Save research findings
- Persist automation results
- Enable file-based workflows

---

### 5. Base64 Screenshot Encoding
**Priority: Low**

**Feature:** Return screenshots as base64 data URIs for LLM analysis

**Current:** Returns file path string
**Proposed:** Add optional parameter to return base64

**Implementation:**
```python
def take_screenshot(self, url: str = None, path: str = "",
                   width: int = 1920, height: int = 1080,
                   full_page: bool = False, return_base64: bool = False) -> str:
    """Take a screenshot.

    Args:
        ...existing args...
        return_base64: If True, returns data URI instead of file path
    """
    # ... existing screenshot code ...

    if return_base64:
        screenshot_bytes = self.page.screenshot(full_page=full_page)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        return f"data:image/png;base64,{screenshot_base64}"
    else:
        self.page.screenshot(path=path, full_page=full_page)
        return f'Screenshot saved: {path}'
```

**Files to modify:**
- `connectonion/cli/browser_agent/browser.py` (`take_screenshot` method)

**Benefits:**
- Screenshots can be sent to vision models
- No file system pollution
- Better for programmatic use

---

### 6. Multi-Agent Architecture Support
**Priority: Medium**

**Feature:** Enable browser session sharing between agents

**Current:** Single agent owns browser instance
**Proposed:** Refactor to support multiple agents sharing one browser

**Implementation:**
```python
# In browser.py
class SharedBrowserSession:
    """Singleton browser session that multiple agents can share."""

    _instance = None

    @classmethod
    def get_instance(cls, **kwargs):
        if cls._instance is None:
            cls._instance = BrowserAutomation(**kwargs)
        return cls._instance

    @classmethod
    def reset(cls):
        if cls._instance:
            cls._instance.close()
        cls._instance = None

# Usage example:
browser = SharedBrowserSession.get_instance(headless=True)

main_agent = Agent("main", tools=[browser], ...)
research_agent = Agent("research", tools=[browser], ...)  # Shares same browser
```

**Files to modify:**
- `connectonion/cli/browser_agent/browser.py`
- `connectonion/cli/commands/browser_commands.py`

**Benefits:**
- Multiple specialized agents can work together
- Shared context across agents
- More complex automation patterns

---

### 7. Enhanced Model Configuration
**Priority: Low**

**Feature:** Make agent model configurable via environment

**Current:** Hardcoded `co/gemini-2.5-pro`
**Proposed:** Use environment variable with fallback

**Implementation:**
```python
# In browser.py BrowserAutomation.__init__()
self.DEFAULT_AI_MODEL = os.getenv("BROWSER_AGENT_MODEL", "co/gemini-2.5-flash")

# In browser.py execute_browser_command()
agent = Agent(
    name="browser_cli",
    model=os.getenv("BROWSER_AGENT_MODEL", "co/gemini-2.5-pro"),
    api_key=api_key,
    system_prompt=PROMPT_PATH,
    tools=[browser],
    max_iterations=100
)
```

**Files to modify:**
- `connectonion/cli/browser_agent/browser.py`

**Benefits:**
- Users can switch models for cost/performance tradeoffs
- Testing with cheaper models
- Flexibility for different use cases

---

### 8. Increased Iteration Limit
**Priority: Low**

**Feature:** Support longer automation workflows

**Current:** `max_iterations=100`
**Proposed:** `max_iterations=200` (match standalone)

**Rationale:**
- Complex workflows need more steps
- Research tasks can be very long
- Standalone has proven 200 works well

**Implementation:**
```python
# In browser.py execute_browser_command()
agent = Agent(
    name="browser_cli",
    model="co/gemini-2.5-pro",
    api_key=api_key,
    system_prompt=PROMPT_PATH,
    tools=[browser],
    max_iterations=200  # Increased from 100
)
```

**Files to modify:**
- `connectonion/cli/browser_agent/browser.py` (line 540)

---

## Implementation Plan

### Phase 1: Core Advanced Features
- [ ] Deep research system (Feature #1)
- [ ] Google search integration (Feature #2)
- [ ] HTML analysis tools (Feature #3)
- [ ] Increased iteration limit (Feature #8)

### Phase 2: Multi-Agent Support
- [ ] Multi-agent architecture support (Feature #6)
- [ ] Enhanced model configuration (Feature #7)

### Phase 3: Nice-to-Have
- [ ] File management tools (Feature #4)
- [ ] Base64 screenshot encoding (Feature #5)

## Testing Checklist

After implementing:
- [ ] Test deep research workflow with multi-page navigation
- [ ] Test Google search extraction accuracy
- [ ] Test HTML analysis with various objectives
- [ ] Test multi-agent browser sharing (no conflicts)
- [ ] Test file tools with research notes
- [ ] Verify model configuration via environment
- [ ] Test long workflows with 200 iterations

## Backward Compatibility

All changes are **additive and backward compatible**:
- Existing `BrowserAutomation` usage unchanged
- New features are optional advanced capabilities
- No breaking changes to public API

## Documentation Updates

After implementation:
- [ ] Update `connectonion/cli/browser_agent/prompt.md` with new tools
- [ ] Update ConnectOnion docs site with deep research examples
- [ ] Add tutorial for multi-agent browser automation
- [ ] Document model configuration options

## Related Issues

- This issue created as part of browser agent sync effort
- Related: Standalone browser-agent sync issue (link TBD)
- Complements the removal of deprecated form filling APIs

## Files to Create

- `connectonion/cli/browser_agent/deep_research.py`
- `connectonion/cli/browser_agent/prompts/deep_research.md`
- `connectonion/cli/browser_agent/file_tools.py` (optional)

## Files to Modify

- `connectonion/cli/browser_agent/browser.py` - Add new methods and features
- `connectonion/cli/browser_agent/__init__.py` - Export new functions
- `connectonion/cli/commands/browser_commands.py` - Support new features in CLI

## Migration Path

Users can opt into advanced features gradually:

**Basic usage (unchanged):**
```python
from connectonion.cli.browser_agent import BrowserAutomation
browser = BrowserAutomation()
# Use as before
```

**Advanced usage (new):**
```python
from connectonion.cli.browser_agent import BrowserAutomation, perform_deep_research
browser = BrowserAutomation()

# Use deep research
result = perform_deep_research("AI agent frameworks comparison", browser)

# Use Google search
results = browser.google_search("ConnectOnion framework")

# Use HTML analysis
analysis = browser.explore("https://example.com", "extract pricing information")
```

## Success Criteria

- Deep research successfully completes multi-step workflows
- Google search returns accurate, structured results
- HTML analysis provides useful insights
- Multi-agent setup works without browser conflicts
- All existing functionality remains working
- Tests pass for both basic and advanced features
