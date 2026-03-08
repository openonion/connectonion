# Sub-Agent Tool Resolution System

## How to Add Different Tools to Sub-Agents

### Current System (Only FileTools)

```
explore.md
---
tools:
  - glob
  - grep
  - read_file
---
        ↓
_resolve_tools(["glob", "grep", "read_file"])
        ↓
return [FileTools(permission="read")]
        ↓
Agent has: glob, grep, read_file
```

**Problem:** What if we want browser tools? WebFetch? Email tools?

### Solution: Tool Registry Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│ Tool Name → Tool Class/Function Mapping                         │
└─────────────────────────────────────────────────────────────────┘

TOOL_REGISTRY = {
    # File tools (FileTools class)
    "glob": ("FileTools", "glob"),
    "grep": ("FileTools", "grep"),
    "read_file": ("FileTools", "read_file"),
    "edit": ("FileTools", "edit"),
    "write": ("FileTools", "write"),

    # Browser tools (BrowserAutomation class)
    "browser_navigate": ("BrowserAutomation", "navigate"),
    "browser_click": ("BrowserAutomation", "click"),
    "browser_screenshot": ("BrowserAutomation", "screenshot"),

    # Web tools (standalone functions)
    "WebFetch": ("function", WebFetch),

    # Email tools (Gmail class)
    "send_email": ("Gmail", "send"),
    "get_emails": ("Gmail", "get_emails"),
}
```

## Complete Tool Resolution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Sub-Agent Definition (debug.md)                              │
└─────────────────────────────────────────────────────────────────┘
---
name: debug
tools:
  - glob           # FileTools
  - grep           # FileTools
  - read_file      # FileTools
  - bash           # Shell function
  - WebFetch       # WebFetch function
read_only: false   # Allow bash execution
---
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Loader Creates Definition                                    │
└─────────────────────────────────────────────────────────────────┘
SubAgentDefinition(
    name="debug",
    tools=["glob", "grep", "read_file", "bash", "WebFetch"],
    read_only=False
)
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Factory Resolves Tools                                       │
└─────────────────────────────────────────────────────────────────┘
_resolve_tools(
    tool_names=["glob", "grep", "read_file", "bash", "WebFetch"],
    read_only=False
)
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Tool Resolution Logic                                        │
└─────────────────────────────────────────────────────────────────┘
def _resolve_tools(tool_names: List[str], read_only: bool) -> List:
    from connectonion.useful_tools.file_tools import FileTools
    from connectonion import bash, WebFetch

    # Group tools by type
    needs_file_tools = any(t in ["glob", "grep", "read_file", "edit", "write"]
                          for t in tool_names)

    tools = []

    # Add FileTools if needed
    if needs_file_tools:
        if read_only:
            tools.append(FileTools(permission="read"))
        else:
            tools.append(FileTools(permission="write"))

    # Add individual tools
    if "bash" in tool_names:
        tools.append(bash)

    if "WebFetch" in tool_names:
        tools.append(WebFetch)

    return tools

Result: [FileTools(permission="write"), bash, WebFetch]
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Agent Receives Mixed Tools                                   │
└─────────────────────────────────────────────────────────────────┘
Agent(
    tools=[
        FileTools(permission="write"),  # Class with methods
        bash,                            # Standalone function
        WebFetch                         # Class (not instance)
    ]
)
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Agent.__init__ Processes Each Tool                           │
└─────────────────────────────────────────────────────────────────┘
for tool in tools:
    if is_class_instance(tool):
        # FileTools(permission="write") → instance
        # Extract: glob, grep, read_file, edit, write
        extract_methods_from_instance(tool)

    elif callable(tool):
        # bash function → add directly
        # WebFetch class → instantiate and extract methods
        process_callable(tool)
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. Final ToolRegistry                                           │
└─────────────────────────────────────────────────────────────────┘
agent.tools = {
    "glob": Tool(FileTools.glob),
    "grep": Tool(FileTools.grep),
    "read_file": Tool(FileTools.read_file),
    "edit": Tool(FileTools.edit),
    "write": Tool(FileTools.write),
    "bash": Tool(bash),
    "WebFetch": Tool(WebFetch.fetch),
}
```

## Example: Browser Sub-Agent

```
┌─────────────────────────────────────────────────────────────────┐
│ browser.md                                                       │
└─────────────────────────────────────────────────────────────────┘
---
name: browser
description: Web scraping and browser automation
model: co/gemini-2.5-pro
max_iterations: 20
tools:
  - browser_navigate
  - browser_click
  - browser_type
  - browser_screenshot
  - read_file        # To read scraped HTML
read_only: false
---

# Browser Agent
You are a browser automation agent...
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Tool Resolution                                                  │
└─────────────────────────────────────────────────────────────────┘
def _resolve_tools(tool_names, read_only):
    from connectonion.useful_tools.file_tools import FileTools
    from connectonion.useful_tools.browser_tools import BrowserAutomation

    tools = []

    # Check if file tools needed
    if "read_file" in tool_names:
        tools.append(FileTools(permission="read"))

    # Check if browser tools needed
    browser_tools = ["browser_navigate", "browser_click", "browser_type",
                     "browser_screenshot"]
    if any(t in tool_names for t in browser_tools):
        tools.append(BrowserAutomation())

    return tools

Result: [FileTools(permission="read"), BrowserAutomation()]
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Agent Has                                                        │
└─────────────────────────────────────────────────────────────────┘
agent.tools = {
    "read_file": Tool(FileTools.read_file),
    "navigate": Tool(BrowserAutomation.navigate),
    "click": Tool(BrowserAutomation.click),
    "type": Tool(BrowserAutomation.type),
    "screenshot": Tool(BrowserAutomation.screenshot),
}
```

## Better Design: Tool Groups

Instead of listing individual tools, use **tool groups**:

```
┌─────────────────────────────────────────────────────────────────┐
│ Improved YAML Format                                             │
└─────────────────────────────────────────────────────────────────┘
---
name: scraper
description: Web scraping agent
model: co/gemini-2.5-pro
max_iterations: 20
tool_groups:
  - file_read      # FileTools(permission="read")
  - browser        # BrowserAutomation()
  - web            # WebFetch
---
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Tool Group Registry                                              │
└─────────────────────────────────────────────────────────────────┘
TOOL_GROUPS = {
    "file_read": lambda: FileTools(permission="read"),
    "file_write": lambda: FileTools(permission="write"),
    "browser": lambda: BrowserAutomation(),
    "web": lambda: WebFetch,
    "email": lambda: Gmail(),
    "bash": lambda: bash,
}
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Resolution                                                       │
└─────────────────────────────────────────────────────────────────┘
def _resolve_tools(definition):
    tools = []

    for group_name in definition.tool_groups:
        tool_factory = TOOL_GROUPS.get(group_name)
        if tool_factory:
            tools.append(tool_factory())

    return tools

Result: [FileTools(permission="read"), BrowserAutomation(), WebFetch]
```

## Simplified Design (Recommended)

```
┌─────────────────────────────────────────────────────────────────┐
│ Simple YAML - Just Specify What You Need                        │
└─────────────────────────────────────────────────────────────────┘
---
name: research
tools:
  - files          # All file operations (read/write)
  - web            # WebFetch
---

---
name: explore
tools:
  - files_ro       # Read-only file operations
---

---
name: browser
tools:
  - files_ro       # Read-only files
  - browser        # Browser automation
  - web            # WebFetch
---

---
name: email
tools:
  - files          # Read/write files
  - email          # Gmail
---
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Simple Resolver                                                  │
└─────────────────────────────────────────────────────────────────┘
def _resolve_tools(tool_names: List[str]) -> List:
    """Map tool names to tool classes/functions."""
    from connectonion.useful_tools.file_tools import FileTools
    from connectonion.useful_tools.browser_tools import BrowserAutomation
    from connectonion import bash, WebFetch, Gmail

    TOOL_MAP = {
        "files": FileTools(permission="write"),
        "files_ro": FileTools(permission="read"),
        "browser": BrowserAutomation(),
        "web": WebFetch,
        "bash": bash,
        "email": Gmail(),
    }

    tools = []
    for name in tool_names:
        if name in TOOL_MAP:
            tools.append(TOOL_MAP[name])

    return tools
```

## Complete Example: Multi-Tool Sub-Agent

```
┌─────────────────────────────────────────────────────────────────┐
│ scraper.md                                                       │
└─────────────────────────────────────────────────────────────────┘
---
name: scraper
description: Web scraping with browser automation and file storage
model: co/gemini-2.5-pro
max_iterations: 25
tools:
  - browser        # BrowserAutomation (navigate, click, screenshot)
  - web            # WebFetch (simple HTTP requests)
  - files          # FileTools (save scraped data)
---

# Scraper Agent

You are a web scraping agent with these capabilities:

1. **Browser automation** (browser tools):
   - navigate(url) - Go to a URL
   - click(selector) - Click elements
   - screenshot() - Take screenshots

2. **HTTP requests** (web tool):
   - WebFetch(url, prompt) - Fetch and analyze pages

3. **File operations** (file tools):
   - write(path, content) - Save scraped data
   - read_file(path) - Read existing data

## Strategy
1. Navigate to target URL with browser
2. Click through pages to load dynamic content
3. Fetch and extract data
4. Save results to files
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Tool Resolution                                                  │
└─────────────────────────────────────────────────────────────────┘
_resolve_tools(["browser", "web", "files"])
        ↓
TOOL_MAP = {
    "browser": BrowserAutomation(),
    "web": WebFetch,
    "files": FileTools(permission="write"),
}
        ↓
Result: [BrowserAutomation(), WebFetch, FileTools(permission="write")]
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Agent Has All These Tools                                        │
└─────────────────────────────────────────────────────────────────┘
agent.tools = {
    # From BrowserAutomation
    "navigate": Tool(...),
    "click": Tool(...),
    "type": Tool(...),
    "screenshot": Tool(...),

    # From WebFetch
    "fetch": Tool(...),

    # From FileTools
    "glob": Tool(...),
    "grep": Tool(...),
    "read_file": Tool(...),
    "edit": Tool(...),
    "write": Tool(...),
}
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Runtime Usage                                                    │
└─────────────────────────────────────────────────────────────────┘
result = task("Scrape product prices from example.com", "scraper")

Agent executes:
  1. navigate("https://example.com")
  2. click(".load-more-button")
  3. screenshot() → saves screenshot
  4. fetch("https://example.com/api/products") → get JSON
  5. write("products.json", data) → save results
```

## Implementation: Updated factory.py

```python
# subagents/factory.py

def _resolve_tools(tool_names: List[str]) -> List:
    """
    Resolve tool names to actual tool classes/functions.

    Supported tools:
    - files: FileTools(permission="write") - All file operations
    - files_ro: FileTools(permission="read") - Read-only files
    - browser: BrowserAutomation() - Browser automation
    - web: WebFetch - HTTP requests
    - bash: bash - Shell commands
    - email: Gmail() - Email operations
    """
    from connectonion.useful_tools.file_tools import FileTools
    from connectonion.useful_tools.browser_tools import BrowserAutomation
    from connectonion import bash, WebFetch, Gmail

    TOOL_MAP = {
        "files": FileTools(permission="write"),
        "files_ro": FileTools(permission="read"),
        "browser": BrowserAutomation(),
        "web": WebFetch,
        "bash": bash,
        "email": Gmail(),
    }

    tools = []
    for name in tool_names:
        if name in TOOL_MAP:
            tools.append(TOOL_MAP[name])
        else:
            print(f"Warning: Unknown tool '{name}', skipping")

    return tools
```

## Diagram: Tool Name → Agent Tool

```
┌──────────────────────────────────────────────────────────────────┐
│                    Tool Resolution Flow                           │
└──────────────────────────────────────────────────────────────────┘

YAML:           tools: ["browser", "web", "files"]
                    ↓
Loader:         SubAgentDefinition(tools=["browser", "web", "files"])
                    ↓
Factory:        _resolve_tools(["browser", "web", "files"])
                    ↓
TOOL_MAP:       {
                  "browser" → BrowserAutomation(),
                  "web" → WebFetch,
                  "files" → FileTools(permission="write")
                }
                    ↓
Result:         [BrowserAutomation(), WebFetch, FileTools(...)]
                    ↓
Agent:          Agent(tools=[...])
                    ↓
Extract:        BrowserAutomation methods:
                  - navigate → Tool
                  - click → Tool
                  - screenshot → Tool

                WebFetch methods:
                  - fetch → Tool

                FileTools methods:
                  - glob → Tool
                  - grep → Tool
                  - read_file → Tool
                  - edit → Tool
                  - write → Tool
                    ↓
ToolRegistry:   agent.tools = {
                  "navigate": Tool(BrowserAutomation.navigate),
                  "click": Tool(BrowserAutomation.click),
                  "screenshot": Tool(BrowserAutomation.screenshot),
                  "fetch": Tool(WebFetch.fetch),
                  "glob": Tool(FileTools.glob),
                  "grep": Tool(FileTools.grep),
                  "read_file": Tool(FileTools.read_file),
                  "edit": Tool(FileTools.edit),
                  "write": Tool(FileTools.write),
                }
                    ↓
Runtime:        LLM can call any of these tools
```

## Summary

**Simple abstraction:**
```
YAML tool name → Tool class/function → Methods extracted → Agent can use
```

**Key points:**
1. Use **high-level tool names** in YAML (`"browser"`, `"files"`, `"web"`)
2. Map to **classes/functions** in factory (`BrowserAutomation()`, `FileTools()`)
3. Agent **auto-extracts methods** from classes
4. LLM gets **all individual methods** as callable tools

This design is **clean, extensible, and easy to understand**.
