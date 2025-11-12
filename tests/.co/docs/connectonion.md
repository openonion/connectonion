# ConnectOnion Framework - Complete Reference for AI Assistants

## Context for AI Assistants

You are helping a developer who wants to use ConnectOnion, a Python framework for creating AI agents with behavior tracking. This document contains everything you need to help them write effective ConnectOnion code.

**Key Principles:**
- Keep simple things simple, make hard things possible
- Function-based tools are preferred over classes
- Activity logging to .co/logs/ (Python SDK only)
- Default settings work for most use cases

---

## What is ConnectOnion?

ConnectOnion is a simple Python framework for creating AI agents that can use tools and track their behavior. Think of it as a way to build ChatGPT-like agents with custom tools.

**Core Features:**
- Turn regular Python functions into agent tools automatically
- Control agent behavior with max_iterations parameter
- Automatic behavior tracking and history
- System prompts for agent personality
- Built-in OpenAI integration
- Debugging with @xray decorator

---

## Installation & Setup

```bash
pip install connectonion
```

**Environment Setup:**
```bash
export OPENAI_API_KEY="your-api-key-here"
# Or use .env file
```

---

## CLI Reference - Quick Project Setup

ConnectOnion includes a CLI for quickly scaffolding agent projects.

### Installation
The CLI is automatically installed with ConnectOnion:
```bash
pip install connectonion
# Provides two commands: 'co' and 'connectonion'
```

### Initialize a Project

```bash
# Create meta-agent (default) - ConnectOnion development assistant
mkdir meta-agent
cd meta-agent
co init

# Create web automation agent
mkdir playwright-agent  
cd playwright-agent
co init --template playwright
```

### CLI Options

- `co init` - Initialize a new agent project
  - `--template, -t` - Choose template: `meta-agent` (default), `playwright`
  - `--force` - Overwrite existing files

### What Gets Created

```
my-project/
├── agent.py           # Main agent implementation
├── prompt.md          # System prompt (markdown)
├── .env.example       # Environment variables template
├── .co/               # ConnectOnion metadata
│   ├── config.toml    # Project configuration
│   └── docs/
│       └── connectonion.md  # Embedded framework documentation
└── .gitignore         # Git ignore rules (if in git repo)
```

### Available Templates

**Meta-Agent (Default)** - ConnectOnion development assistant with built-in tools:
- `answer_connectonion_question()` - Expert answers from embedded docs
- `create_agent_from_template()` - Generate complete agent code
- `generate_tool_code()` - Create tool functions
- `create_test_for_agent()` - Generate pytest test suites
- `think()` - Self-reflection to analyze task completion
- `generate_todo_list()` - Create structured plans (uses GPT-4o-mini)
- `suggest_project_structure()` - Architecture recommendations

**Playwright Template** - Web automation with stateful browser control:
- `start_browser()` - Launch browser instance
- `navigate()` - Go to URLs
- `scrape_content()` - Extract page content
- `fill_form()` - Fill and submit forms
- `take_screenshot()` - Capture pages
- `extract_links()` - Get all links
- `execute_javascript()` - Run JS code
- `close_browser()` - Clean up resources

Note: Playwright template requires `pip install playwright && playwright install`

### Interactive Features

The CLI will:
- Warn if you're in a special directory (home, root, system)
- Ask for confirmation if the directory is not empty
- Automatically detect git repositories and update `.gitignore`
- Provide clear next steps after initialization

### Quick Start After Init

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Add your OpenAI API key to .env
echo "OPENAI_API_KEY=sk-your-key-here" > .env

# 3. Run your agent
python agent.py
```

---

## Quick Start Template

```python
from connectonion import Agent

# 1. Define tools as regular functions
def search(query: str) -> str:
    """Search for information."""
    return f"Found information about {query}"

def calculate(expression: str) -> float:
    """Perform mathematical calculations."""
    return eval(expression)  # Use safely in production

# 2. Create agent
agent = Agent(
    name="my_assistant",
    system_prompt="You are a helpful assistant.",
    tools=[search, calculate]
    # max_iterations=10 (default)
)

# 3. Use agent
result = agent.input("What is 25 * 4?")
print(result)
```

**Example output (will vary):**

```
100
```

---

## How ConnectOnion Works - The Agent Loop

### Input → Processing → Output Flow

```python
# 1. User provides input
result = agent.input("Search for Python tutorials and summarize them")

# 2. Agent processes in iterations:
# Iteration 1: LLM decides → "I need to search first"
#              → Calls search("Python tutorials") 
#              → Gets result: "Found 10 tutorials about Python"

# Iteration 2: LLM continues → "Now I need to summarize"
#              → Calls summarize("Found 10 tutorials...")
#              → Gets result: "Summary: Python tutorials cover..."

# Iteration 3: LLM concludes → "Task complete"
#              → Returns final answer (no more tool calls)

# 3. User gets final result
print(result)  # "Here's a summary of Python tutorials: ..."
```

### The Agent Execution Loop

Each `agent.input()` call follows this pattern:

1. **Setup**: Agent receives user prompt + system prompt
2. **Loop** (up to `max_iterations` times):
   - Send current conversation to LLM
   - If LLM returns tool calls → execute them → add results to conversation
   - If LLM returns text only → task complete, exit loop
3. **Return**: Final LLM response to user

### Message Flow Example

```python
# Internal conversation that builds up:

# Initial messages
[
  {"role": "system", "content": "You are a helpful assistant..."},
  {"role": "user", "content": "Search for Python tutorials and summarize"}
]

# After iteration 1 (LLM called search tool)
[
  {"role": "system", "content": "You are a helpful assistant..."},
  {"role": "user", "content": "Search for Python tutorials and summarize"},
  {"role": "assistant", "tool_calls": [{"name": "search", "arguments": {"query": "Python tutorials"}}]},
  {"role": "tool", "content": "Found 10 tutorials about Python basics...", "tool_call_id": "call_1"}
]

# After iteration 2 (LLM called summarize tool)
[
  # ... previous messages ...
  {"role": "assistant", "tool_calls": [{"name": "summarize", "arguments": {"text": "Found 10 tutorials..."}}]},
  {"role": "tool", "content": "Summary: Python tutorials cover variables, functions...", "tool_call_id": "call_2"}
]

# Final iteration (LLM provides answer)
[
  # ... previous messages ...
  {"role": "assistant", "content": "Here's a summary of Python tutorials: They cover..."}
]
```

### Input/Output Types

**Input to `agent.input()`:**
- `prompt` (str): User's request/question
- `max_iterations` (optional int): Override iteration limit for this request

**Output from `agent.input()`:**
- String: Final LLM response to user
- If max iterations reached: `"Task incomplete: Maximum iterations (N) reached."`

**Tool Function Signatures:**
```python
# Tools always follow this pattern:
def tool_name(param1: type, param2: type = default) -> return_type:
    """Description for LLM."""
    # Your logic here
    return result  # Must match return_type
```

### Automatic Behavior Tracking

Every `agent.input()` call creates a record:

```python
# Automatic tracking in ~/.connectonion/agents/{name}/behavior.json
{
  "timestamp": "2024-01-15T10:30:00",
  "user_prompt": "Search for Python tutorials and summarize",
  "tool_calls": [
    {
      "name": "search",
      "arguments": {"query": "Python tutorials"},
      "result": "Found 10 tutorials...",
      "status": "success",
      "timing": 245.3  # milliseconds
    },
    {
      "name": "summarize", 
      "arguments": {"text": "Found 10 tutorials..."},
      "result": "Summary: Python tutorials...",
      "status": "success", 
      "timing": 156.7
    }
  ],
  "result": "Here's a summary of Python tutorials...",
  "duration": 2.34  # total seconds
}

# Access history
print(agent.history.summary())  # Human-readable summary
print(len(agent.history.records))  # Number of tasks completed
```

---

## Core API Reference

### Agent Class

```python
class Agent:
    def __init__(
        self,
        name: str,
        llm: Optional[LLM] = None,
        tools: Optional[List[Callable]] = None,
        system_prompt: Union[str, Path, None] = None,
        api_key: Optional[str] = None,
        model: str = "gpt-4-mini",
        max_iterations: int = 10
    )
    
    def input(self, prompt: str, max_iterations: Optional[int] = None) -> str:
        """Send input to agent and get response."""
    
    def add_tool(self, tool: Callable):
        """Add a new tool to the agent."""
    
    def remove_tool(self, tool_name: str) -> bool:
        """Remove a tool by name."""
    
    def list_tools(self) -> List[str]:
        """List all available tool names."""
```

### Key Parameters Explained

**max_iterations** (Default: 10):
- Controls how many tool calls the agent can make per task
- Simple tasks: 3-5 iterations
- Standard workflows: 10-15 iterations  
- Complex analysis: 20-40 iterations
- Research projects: 30-50 iterations

**system_prompt** (Recommended: Use markdown files):
- **Path/str: Load from file (RECOMMENDED)** - Keep prompts separate from code
- String: Direct prompt text (only for very simple cases)
- None: Uses default helpful assistant prompt

---

## Function-Based Tools (Recommended Approach)

### Basic Tool Creation

```python
def my_tool(param: str, optional_param: int = 10) -> str:
    """This docstring becomes the tool description."""
    return f"Processed {param} with value {optional_param}"

# Automatic conversion - just pass the function!
agent = Agent("assistant", tools=[my_tool])
```

### Tool Guidelines

**Type Hints are Required:**
```python
# Good - clear types
def search(query: str, limit: int = 10) -> str:
    return f"Found {limit} results for {query}"

# Bad - no type hints
def search(query, limit=10):
    return f"Found {limit} results for {query}"
```

**Docstrings Become Descriptions:**
```python
def analyze_data(data: str, method: str = "standard") -> str:
    """Analyze data using specified method.
    
    Methods: standard, detailed, quick
    """
    return f"Analysis complete using {method} method"
```

### Tool Descriptions and Schemas (What the LLM Sees)

The first line of a tool's docstring is used as the human‑readable description. ConnectOnion also builds a JSON schema from the function signature and type hints.

```python
from typing import Literal, Annotated

Priority = Literal["low", "normal", "high"]

def create_ticket(
    title: str,
    description: str,
    priority: Priority = "normal",
    assignee: Annotated[str, "email"] | None = None,
) -> str:
    """Create a ticket and return its ID."""
    return "T-1024"

# Internally, the agent exposes a schema like this to the LLM:
schema = {
  "name": "create_ticket",
  "description": "Create a ticket and return its ID.",
  "parameters": {
    "type": "object",
    "properties": {
      "title": {"type": "string"},
      "description": {"type": "string"},
      "priority": {"enum": ["low", "normal", "high"]},
      "assignee": {"type": "string"}
    },
    "required": ["title", "description"]
  }
}
```

Best practices for descriptions:

- Start with a concise, imperative one‑liner: “Create…”, “Search…”, “Summarize…”.
- Mention key constraints and side effects (“Sends network request”, “Writes to disk”).
- Clarify required vs optional parameters and valid ranges/enums.
- Prefer deterministic behavior; if not, state what is non‑deterministic.
- Keep the first line under ~90 characters; add additional details on following lines.

---

## Stateful Tools with Playwright (Shared Context via Classes)

**✅ RECOMMENDED: Pass the class instance directly to ConnectOnion!**

ConnectOnion automatically discovers all public methods with type hints when you pass a class instance. This is much cleaner than listing methods individually.

Use a class instance when tools need to share state (browser, cache, DB handles). You can also mix class methods with regular function tools.

Prerequisites:

```bash
pip install playwright
playwright install
```

```python
from connectonion import Agent

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit("Install Playwright: pip install playwright && playwright install")


class BrowserAutomation:
    """Real browser session with shared context across tool calls."""

    def __init__(self):
        self._p = None
        self._browser = None
        self._page = None
        self._screenshots: list[str] = []

    def start_browser(self, headless: bool = True) -> str:
        """Start a Chromium browser session."""
        self._p = sync_playwright().start()
        self._browser = self._p.chromium.launch(headless=headless)
        self._page = self._browser.new_page()
        return f"Browser started (headless={headless})"

    def goto(self, url: str) -> str:
        """Navigate to a URL and return the page title."""
        if not self._page:
            return "Error: Browser not started"
        self._page.goto(url)
        return self._page.title()

    def screenshot(self, filename: str = "page.png") -> str:
        """Save a screenshot and return the filename."""
        if not self._page:
            return "Error: Browser not started"
        self._page.screenshot(path=filename)
        self._screenshots.append(filename)
        return filename

    def close(self) -> str:
        """Close resources and end the session."""
        try:
            if self._page:
                self._page.close()
            if self._browser:
                self._browser.close()
            if self._p:
                self._p.stop()
            return "Browser closed"
        finally:
            self._page = None
            self._browser = None
            self._p = None


def format_title(title: str) -> str:
    """Format a page title for logs or UIs."""
    return f"[PAGE] {title}"


# Mix class instance (stateful tools) and regular functions
browser = BrowserAutomation()
agent = Agent(
    name="web_assistant",
    tools=[browser, format_title],
    system_prompt="You are a web automation assistant. Be explicit about each step."
)

# Manual session (no LLM) — call tools directly
print(agent.tool_map["start_browser"](headless=True))
title = agent.tool_map["goto"]("https://example.com")
print(agent.tool_map["format_title"](title=title))
print(agent.tool_map["screenshot"](filename="example.png"))
print(agent.tool_map["close"]())
```

**Example output:**

```
Browser started (headless=True)
[PAGE] Example Domain
example.png
Browser closed
```

Agent‑driven session (LLM decides which tools to call):

```python
# Natural language instruction — the agent chooses and orders tool calls
result = agent.input(
    """
    Open https://example.com, return the page title, take a screenshot named
    example.png, then close the browser.
    """
)
print(result)
```

**Example output (simplified):**

```
Title: Example Domain
Screenshot saved: example.png
Browser session closed.
```

Why this pattern works:

- Class instance keeps shared state (browser/page) across calls.
- Function tools are great for lightweight utilities (formatting, parsing, saving records).
- The agent exposes both as callable tools with proper schemas and docstring descriptions.

---

## max_iterations Control

### Basic Usage

```python
# Default: 10 iterations (good for most tasks)
agent = Agent("helper", tools=[...])

# Simple tasks - fewer iterations
calc_agent = Agent("calculator", tools=[calculate], max_iterations=5)

# Complex tasks - more iterations  
research_agent = Agent("researcher", tools=[...], max_iterations=25)
```

### Per-Request Override

```python
agent = Agent("flexible", tools=[...])

# Normal task
result = agent.input("Simple question")

# Complex task needs more iterations
result = agent.input(
    "Analyze all data and generate comprehensive report",
    max_iterations=30
)
```

### When You Hit the Limit

```python
# Error message when limit reached:
"Task incomplete: Maximum iterations (10) reached."

# Solutions:
# 1. Increase agent's default
agent.max_iterations = 20

# 2. Override for specific task  
result = agent.input("complex task", max_iterations=25)

# 3. Break task into smaller parts
result1 = agent.input("First analyze the data")
result2 = agent.input(f"Based on {result1}, create summary")
```

---

## System Prompts & Personality

**Best Practice: Use Markdown Files for System Prompts**

Keep your prompts separate from code for better maintainability, version control, and collaboration.

### Recommended: Load from Markdown File

```python
# ✅ RECOMMENDED: Load from markdown file
agent = Agent(
    name="support_agent",
    system_prompt="prompts/customer_support.md",  # Clean separation
    tools=[...]
)

# Using Path object (also good)
from pathlib import Path
agent = Agent(
    name="data_analyst", 
    system_prompt=Path("prompts") / "data_analyst.md",
    tools=[...]
)

# Any extension works (.md, .txt, .prompt, etc.)
agent = Agent(
    name="coder",
    system_prompt="prompts/senior_developer.txt",
    tools=[...]
)
```

### Example Prompt File (`prompts/customer_support.md`)

```markdown
# Customer Support Agent

You are a senior customer support specialist with 10+ years of experience.

## Your Expertise
- Empathetic communication with frustrated customers
- Root cause analysis for technical issues  
- Clear, step-by-step problem solving
- Escalation management

## Guidelines
1. **Always acknowledge** the customer's concern first
2. **Ask clarifying questions** to understand the real problem
3. **Provide actionable solutions** with clear next steps
4. **Follow up** to ensure satisfaction

## Tone
- Professional but warm
- Patient and understanding
- Confident in your recommendations
- Never dismissive of concerns

## Example Responses
When a customer is frustrated:
> "I completely understand your frustration with this issue. Let me help you resolve this right away. Can you tell me exactly what happened when you tried to [action]?"
```

### Why Markdown Files Are Better

**✅ Advantages:**
- **Version Control**: Track prompt changes over time
- **Collaboration**: Team members can easily review and edit prompts
- **Readability**: Markdown formatting makes prompts clear and professional
- **Reusability**: Share prompts across different agents
- **No Code Pollution**: Keep business logic separate from implementation
- **IDE Support**: Syntax highlighting and formatting in markdown files

**❌ Avoid Inline Strings:**
```python
# ❌ DON'T DO THIS - Hard to maintain
agent = Agent(
    name="support", 
    system_prompt="You are a customer support agent. Be helpful and friendly. Always ask follow-up questions. Use empathetic language. Provide step-by-step solutions...",  # This gets messy!
    tools=[...]
)
```

### Advanced Prompt Organization

```python
# Organize prompts by role/domain
prompts/
├── customer_support/
│   ├── tier1_support.md
│   ├── technical_support.md
│   └── billing_support.md
├── data_analysis/
│   ├── financial_analyst.md
│   └── research_analyst.md
└── development/
    ├── code_reviewer.md
    └── senior_developer.md

# Load specific prompts
support_agent = Agent(
    name="tier1_support",
    system_prompt="prompts/customer_support/tier1_support.md",
    tools=[create_ticket, search_kb, escalate]
)

analyst_agent = Agent(
    name="financial_analyst", 
    system_prompt="prompts/data_analysis/financial_analyst.md",
    tools=[fetch_data, analyze_trends, generate_report]
)
```

### Simple Cases Only

For very simple, single-line prompts, inline strings are acceptable:

```python
# ✅ OK for simple cases
calculator = Agent(
    name="calc",
    system_prompt="You are a helpful calculator. Always show your work step by step.",
    tools=[calculate]
)
```

---

## Debugging with @xray

Debug your agent's tool execution with real-time insights - see what your AI agent is thinking.

### Quick Start

```python
from connectonion.decorators import xray

@xray
def my_tool(text: str) -> str:
    """Process some text."""
    
    # Now you can see inside the agent's mind!
    print(xray.agent.name)    # "my_assistant"
    print(xray.task)          # "Process this document"
    print(xray.iteration)     # 1, 2, 3...
    
    return f"Processed: {text}"
```

That's it! Add `@xray` to any tool to unlock debugging superpowers.

### What You Can Access

Inside any `@xray` decorated function:

```python
xray.agent         # The Agent instance calling this tool
xray.task          # Original request from user  
xray.messages      # Full conversation history
xray.iteration     # Which round of tool calls (1-10)
xray.previous_tools # Tools called before this one
```

### Real Example

```python
@xray
def search_database(query: str) -> str:
    """Search our database."""
    
    # See what led to this search
    print(f"User asked: {xray.task}")
    print(f"This is iteration {xray.iteration}")
    
    if xray.previous_tools:
        print(f"Already tried: {xray.previous_tools}")
    
    # Adjust behavior based on context
    if xray.iteration > 2:
        return "No results found, please refine your search"
    
    return f"Found 5 results for '{query}'"
```

### Visual Execution Trace

See the complete flow of your agent's work from inside a tool:

```python
@xray
def analyze_data(text: str) -> str:
    """Analyze data and show execution trace."""
    
    # Show what happened so far
    xray.trace()
    
    return "Analysis complete"
```

**Output:**
```
Task: "Find Python tutorials and summarize them"

[1] • 89ms  search_database(query="Python tutorials")
      IN  → query: "Python tutorials"
      OUT ← "Found 5 results for 'Python tutorials'"

[2] • 234ms summarize_text(text="Found 5 results...", max_words=50)
      IN  → text: "Found 5 results for 'Python tutorials'"
      IN  → max_words: 50
      OUT ← "5 Python tutorials found covering basics to advanced topics"

Total: 323ms • 2 steps • 1 iterations
```

### Debug in Your IDE

Set a breakpoint and explore:

```python
@xray
def analyze_sentiment(text: str) -> str:
    # 🎯 Set breakpoint on next line
    sentiment = "positive"  # When stopped here in debugger:
                           # >>> xray
                           # <XrayContext active>
                           #   agent: 'my_bot'
                           #   task: 'How do people feel about Python?'
                           # >>> xray.messages
                           # [{'role': 'user', 'content': '...'}, ...]
    
    return sentiment
```

### Practical Use Cases

**1. Understand Why a Tool Was Called**
```python
@xray
def emergency_shutdown():
    """Shutdown the system."""
    
    # Check why this drastic action was requested
    print(f"Shutdown requested because: {xray.task}")
    print(f"After trying: {xray.previous_tools}")
    
    # Maybe don't shutdown if it's the first try
    if xray.iteration == 1:
        return "Try restarting first"
    
    return "System shutdown complete"
```

**2. Adaptive Tool Behavior**
```python
@xray
def fetch_data(source: str) -> str:
    """Fetch data from a source."""
    
    # Use cache on repeated calls
    if "fetch_data" in xray.previous_tools:
        return "Using cached data"
    
    # Fresh fetch on first call
    return f"Fresh data from {source}"
```

**3. Debug Complex Flows**
```python
@xray
def process_order(order_id: str) -> str:
    """Process an order."""
    
    # See the full context when debugging
    if xray.agent:
        print(f"Processing for agent: {xray.agent.name}")
        print(f"Original request: {xray.task}")
        print(f"Conversation length: {len(xray.messages)}")
    
    return f"Order {order_id} processed"
```

### Tips

1. **Development Only** - Remove @xray in production for best performance
2. **Combine with IDE** - Set breakpoints for interactive debugging  
3. **Use trace()** - Call `xray.trace()` to see full execution flow
4. **Check context** - Always verify `xray.agent` exists before using

### Common Patterns

**Logging What Matters:**
```python
@xray
def important_action(data: str) -> str:
    # Log with context
    if xray.agent:
        logger.info(f"Agent {xray.agent.name} performing action")
        logger.info(f"Original task: {xray.task}")
        logger.info(f"Iteration: {xray.iteration}")
    
    return "Action completed"
```

**Conditional Logic:**
```python
@xray
def smart_search(query: str) -> str:
    # Different strategies based on context
    if xray.iteration > 1:
        # Broaden search on retry
        query = f"{query} OR related"
    
    if "analyze" in xray.previous_tools:
        # We already analyzed, search differently
        query = f"summary of {query}"
    
    return f"Results for: {query}"
```

---

## Common Patterns & Examples

### Pattern 1: Simple Calculator Bot

```python
def calculate(expression: str) -> float:
    """Perform mathematical calculations."""
    try:
        # Safe eval for demo - use proper parsing in production
        allowed = "0123456789+-*/(). "
        if all(c in allowed for c in expression):
            return eval(expression)
        else:
            raise ValueError("Invalid characters")
    except Exception as e:
        raise ValueError(f"Calculation error: {e}")

calc_agent = Agent(
    name="calculator",
    system_prompt="You are a helpful calculator. Always show your work.",
    tools=[calculate],
    max_iterations=5  # Math rarely needs many iterations
)

result = calc_agent.input("What is (25 + 15) * 3?")
```

### Pattern 2: Research Assistant

```python
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for information."""
    # Your search implementation
    return f"Found {num_results} results for '{query}'"

def summarize(text: str, length: str = "medium") -> str:
    """Summarize text content."""
    # Your summarization implementation
    return f"Summary ({length}): {text[:100]}..."

def save_notes(content: str, filename: str = "research.txt") -> str:
    """Save content to a file."""
    # Your file saving implementation
    return f"Saved content to {filename}"

research_agent = Agent(
    name="researcher",
    system_prompt="You are a thorough researcher who provides well-sourced information.",
    tools=[web_search, summarize, save_notes],
    max_iterations=25  # Research involves many steps
)

result = research_agent.input(
    "Research the latest developments in quantum computing and save a summary"
)
```

### Pattern 3: File Analyzer

```python
def read_file(filepath: str) -> str:
    """Read contents of a text file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File {filepath} not found"
    except Exception as e:
        return f"Error reading file: {e}"

def analyze_text(text: str, analysis_type: str = "summary") -> str:
    """Analyze text content."""
    if analysis_type == "summary":
        return f"Text summary: {len(text)} characters, {len(text.split())} words"
    elif analysis_type == "sentiment":
        return "Sentiment analysis: Neutral tone detected"
    else:
        return f"Analysis type '{analysis_type}' not supported"

def generate_report(findings: str, format: str = "markdown") -> str:
    """Generate a formatted report."""
    if format == "markdown":
        return f"# Analysis Report\n\n{findings}\n\nGenerated by ConnectOnion"
    else:
        return findings

file_agent = Agent(
    name="file_analyzer",
    system_prompt="You are a document analyst who provides detailed insights.",
    tools=[read_file, analyze_text, generate_report],
    max_iterations=15
)
```

### Pattern 4: Multi-Agent Coordination

```python
# Specialized agents for different tasks
calculator = Agent("calc", tools=[calculate], max_iterations=5)
researcher = Agent("research", tools=[web_search, summarize], max_iterations=20)
writer = Agent("writer", tools=[generate_report, save_notes], max_iterations=10)

def coordinate_agents(task: str) -> str:
    """Coordinate multiple agents for complex tasks."""
    if "calculate" in task.lower():
        return calculator.input(task)
    elif "research" in task.lower():
        return researcher.input(task)
    elif "write" in task.lower():
        return writer.input(task)
    else:
        # Default to research agent for general tasks
        return researcher.input(task)
```

---

## Advanced Patterns

### Auto-Retry with Increasing Limits

```python
def smart_input(agent: Agent, prompt: str, max_retries: int = 3) -> str:
    """Automatically retry with higher iteration limits if needed."""
    limits = [10, 25, 50]
    
    for i, limit in enumerate(limits):
        result = agent.input(prompt, max_iterations=limit)
        if "Maximum iterations" not in result:
            return result
        if i < max_retries - 1:
            print(f"Retrying with {limits[i+1]} iterations...")
    
    return "Task too complex even with maximum iterations"

# Usage
agent = Agent("adaptive", tools=[...])
result = smart_input(agent, "Complex multi-step task")
```

### Self-Adjusting Agent

```python
class SmartAgent:
    def __init__(self, name: str, tools: list):
        self.agent = Agent(name, tools=tools)
        self.task_patterns = {
            'simple': (['what', 'when', 'calculate'], 5),
            'moderate': (['analyze', 'compare', 'summarize'], 15),
            'complex': (['research', 'comprehensive', 'detailed'], 30)
        }
    
    def input(self, prompt: str) -> str:
        # Detect complexity from keywords
        max_iter = 10  # default
        prompt_lower = prompt.lower()
        
        for pattern_name, (keywords, iterations) in self.task_patterns.items():
            if any(keyword in prompt_lower for keyword in keywords):
                max_iter = iterations
                break
        
        return self.agent.input(prompt, max_iterations=max_iter)

# Usage
smart = SmartAgent("adaptive", tools=[...])
smart.input("What is 2+2?")  # Uses 5 iterations
smart.input("Research and analyze market trends")  # Uses 30 iterations
```

---

## Best Practices

### Tool Design

✅ **Good:**
```python
def search_papers(query: str, max_results: int = 10, field: str = "all") -> str:
    """Search academic papers with specific parameters."""
    return f"Found {max_results} papers about '{query}' in {field}"
```

❌ **Avoid:**
```python
def search(q, n=10):  # No type hints
    return "some results"  # Vague return
```

### Error Handling

✅ **Good:**
```python
def read_file(filepath: str) -> str:
    """Read file with proper error handling."""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File '{filepath}' not found"
    except PermissionError:
        return f"Error: Permission denied for '{filepath}'"
    except Exception as e:
        return f"Error reading file: {e}"
```

### Agent Configuration

✅ **Good:**
```python
# Clear purpose, markdown prompts, appropriate limits
data_analyst = Agent(
    name="data_analyst",
    system_prompt="prompts/data_scientist.md",  # Use markdown files!
    tools=[load_data, analyze_stats, create_visualization],
    max_iterations=20  # Data analysis can be multi-step
)
```

❌ **Avoid:**
```python
# Vague purpose, inline prompts, arbitrary limits
agent = Agent(
    name="agent",
    system_prompt="You are an agent that does stuff. Be helpful and do things when asked. Always be polite and provide good answers...",  # Too long inline!
    tools=[lots_of_random_tools],
    max_iterations=100  # Way too high
)
```

### System Prompt Best Practices

✅ **Use Markdown Files:**
```python
# Recommended approach
agent = Agent(
    name="support_specialist",
    system_prompt="prompts/customer_support.md",
    tools=[create_ticket, search_kb]
)
```

❌ **Avoid Inline Strings:**
```python
# Hard to maintain and review
agent = Agent(
    name="support_specialist", 
    system_prompt="You are a customer support specialist. Always be empathetic. Ask clarifying questions. Provide step-by-step solutions. Use professional language...",
    tools=[create_ticket, search_kb]
)
```

---

## Troubleshooting Guide

### Common Issues & Solutions

**Issue: "Maximum iterations reached"**
```python
# Check what happened
if "Maximum iterations" in result:
    # Look at the last record to see what went wrong
    last_record = agent.history.records[-1]
    for tool_call in last_record.tool_calls:
        if tool_call['status'] == 'error':
            print(f"Tool {tool_call['name']} failed: {tool_call['result']}")

# Solutions:
# 1. Increase iterations
result = agent.input(prompt, max_iterations=30)

# 2. Break down the task
step1 = agent.input("First, analyze the data")
step2 = agent.input(f"Based on {step1}, create summary")
```

**Issue: Tools not working**
```python
# Check tool registration
print(agent.list_tools())  # See what tools are available

# Check tool schemas
for tool in agent.tools:
    print(tool.to_function_schema())
```

**Issue: Unexpected behavior**
```python
# Use @xray for debugging
@xray
def debug_tool(input: str) -> str:
    context = get_xray_context()
    print(f"Iteration: {context.iteration}")
    print(f"Previous tools: {context.previous_tools}")
    return f"Processed: {input}"
```

---

## When to Use ConnectOnion

### Good Use Cases
- Building custom AI assistants with specific tools
- Automating workflows that need multiple steps
- Creating domain-specific chatbots (customer support, data analysis, etc.)
- Prototyping agent behaviors with automatic tracking
- Educational projects to understand agent architectures

### Not Ideal For
- Simple single-function calls (just call the function directly)
- Real-time applications requiring <100ms response times
- Production systems without proper error handling and security
- Tasks that don't benefit from LLM reasoning

---

## Links & Resources

- **GitHub**: https://github.com/openonion/connectonion
- **PyPI**: https://pypi.org/project/connectonion/
- **Latest Version**: 0.0.1b4

---

## AI Assistant Instructions

When helping users with ConnectOnion:

1. **Start Simple**: Use the basic patterns first, add complexity only when needed
2. **Type Hints**: Always include proper type hints in tool functions
3. **Error Handling**: Add try/catch blocks for robust tools
4. **Iteration Limits**: Help users choose appropriate max_iterations based on task complexity
5. **Debugging**: Suggest @xray decorator when users have issues
6. **Best Practices**: Guide users toward function-based tools over complex classes

Remember: ConnectOnion is designed to make simple things simple and hard things possible. Start with the basics and build up complexity gradually.