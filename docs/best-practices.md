# Best Practices

**"Keep simple things simple, make complicated things possible"**

---

## 1. YAGNI: Don't Over-Engineer

### Let It Crash

```python
# ❌ BAD: Over-engineered
def search_web(query: str) -> str:
    try:
        if not query or len(query) < 3:
            return "Query too short"
        for attempt in range(3):
            try:
                result = requests.get(f"https://api.example.com?q={query}")
                if result.status_code == 200:
                    break
            except Exception as e:
                if attempt == 2:
                    return f"Error: {e}"
        cache[hash(query)] = result
        return result.text
    except Exception:
        return "Search unavailable"

# ✅ GOOD: Simple
def search_web(query: str) -> str:
    """Search the web."""
    return requests.get(f"https://api.example.com?q={query}").text
```

**Why:** Agent sees real errors and can self-correct. No hidden failures.

**Only add try-except for:**
- Resource cleanup (files, connections)
- Better error messages (when explicitly needed)

### No utils.py

```python
# ❌ BAD: utils.py becomes a dumping ground
# ✅ GOOD: Keep helpers with features

# tools/email.py
def _parse_email(raw: str) -> str:  # Helper stays here
    match = re.search(r'<(.+?)>', raw)
    return match.group(1) if match else raw

def send_email(to: str, subject: str, body: str) -> str:
    recipient = _parse_email(to)
    # ... send
```

**Rule:** Used in ONE place? Keep it in that file.

### Return Raw Data

```python
# ❌ BAD: Formatting in tool
def get_user(user_id: str) -> str:
    user = db.query(...)
    return f"Name: {user['name']}\nEmail: {user['email']}"

# ✅ GOOD: Raw data
def get_user(user_id: str) -> dict:
    return db.query(...)  # Agent formats based on context
```

### Checklist

- [ ] Adding try-except "just in case"? → Remove
- [ ] Creating utils.py? → Keep with feature
- [ ] Adding retry before seeing failures? → Remove
- [ ] Formatting tool output? → Return raw data

---

## 2. Event System: When and How

### Critical Rule: Message Injection

```python
# ❌ BAD: Breaks Anthropic
from connectonion import after_each_tool

def add_reflection(agent):
    agent.current_session['messages'].append({...})  # WRONG EVENT!

agent = Agent("bot", on_events=[after_each_tool(add_reflection)])

# ✅ GOOD: Use after_tools
from connectonion import after_tools, llm_do

def add_reflection(agent):
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_result':
        reflection = llm_do(f"What did we learn from {trace['name']}?", temperature=0.2)
        agent.current_session['messages'].append({'role': 'assistant', 'content': reflection})

agent = Agent("bot", on_events=[after_tools(add_reflection)])
```

**Why:** Anthropic requires tool results immediately after tool_calls. Use `after_tools`, NOT `after_each_tool`.

### Event Selection

| Goal | Use | Example |
|------|-----|---------|
| Add context once | `after_user_input` | Timestamp |
| Approve dangerous tools | `before_each_tool` | Check bash |
| Log performance | `after_each_tool` | Timing only |
| **Add messages** | `after_tools` | **Reflection** |
| Error handling | `on_error` | Alerts |

### Pattern: Reflection with llm_do

```python
from connectonion import Agent, after_tools, llm_do
from pydantic import BaseModel

class NextAction(BaseModel):
    tool: str
    reasoning: str

def suggest_next_tool(agent):
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_result' and trace['status'] == 'success':
        suggestion = llm_do(
            f"Used: {trace['name']}\nResult: {trace['result'][:200]}\nWhat next?",
            output=NextAction,
            temperature=0.2
        )
        agent.current_session['messages'].append({
            'role': 'system',
            'content': f"💡 Use {suggestion.tool}. {suggestion.reasoning}"
        })

agent = Agent("bot", on_events=[after_tools(suggest_next_tool)])
```

### Pattern: Dangerous Command Approval

```python
from connectonion import before_each_tool

def approve_dangerous(agent):
    pending = agent.current_session.get('pending_tool')
    if pending and pending['name'] == 'bash':
        cmd = pending['arguments'].get('command', '')
        if 'rm -rf' in cmd or 'sudo' in cmd:
            if input(f"⚠️  Run '{cmd}'? (y/N): ").lower() != 'y':
                raise ValueError("Rejected by user")

agent = Agent("bot", tools=[bash], on_events=[before_each_tool(approve_dangerous)])
```

### Common Mistakes

- ❌ Message injection in `after_each_tool` → Use `after_tools`
- ❌ Silent exception handling → Let it crash
- ❌ Using `trace[0]` → Use `trace[-1]` for latest

---

## 3. Share State: Use Classes

### When Tools Need Shared Context

```python
# ❌ BAD: Separate functions can't share state
def open_browser() -> str:
    browser = Browser()  # New instance
    browser.start()
    return "Opened"

def navigate(url: str) -> str:
    browser = Browser()  # Different instance! Lost previous state
    browser.goto(url)
    return "Navigated"

# ✅ GOOD: Class shares state across tool calls
class Browser:
    def __init__(self):
        self.page = None

    def open(self) -> str:
        """Open browser."""
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self.page = self._playwright.chromium.launch().new_page()
        return "Browser opened"

    def navigate(self, url: str) -> str:
        """Navigate to URL."""
        self.page.goto(url)  # Uses same browser instance!
        return f"Navigated to {url}"

    def close(self) -> str:
        """Close browser."""
        self.page.close()
        self._playwright.stop()
        return "Browser closed"

browser = Browser()
agent = Agent("web", tools=[browser])  # Pass instance, auto-discovers all methods
```

**Why:** `self.page` persists across `open()` → `navigate()` → `close()`. Same browser instance for all tool calls.

### Pattern: Database Connection

```python
class Database:
    def __init__(self, connection_string: str):
        self.conn = None
        self.connection_string = connection_string

    def connect(self) -> str:
        """Connect to database."""
        import psycopg2
        self.conn = psycopg2.connect(self.connection_string)
        return "Connected"

    def query(self, sql: str) -> list:
        """Run SQL query."""
        cursor = self.conn.cursor()  # Uses shared connection
        cursor.execute(sql)
        return cursor.fetchall()

    def disconnect(self) -> str:
        """Close connection."""
        self.conn.close()
        return "Disconnected"

db = Database("postgresql://localhost/mydb")
agent = Agent("analyst", tools=[db])

# Agent calls: connect() → query() → query() → disconnect()
# All share same database connection!
```

### When to Use Classes

**Use classes when tools need to share:**
- Browser instance (Playwright page)
- Database connection
- API client with auth tokens
- File handles
- Any stateful resource

**Use simple functions when:**
- No shared state needed
- Pure calculations
- One-off operations

---

## 4. CLI Commands: co create & co auth

### Quick Setup

```bash
# One-time authentication (includes 100K free tokens)
co auth

# Create new agent from template
co create my-agent

# Start interactive AI coding assistant
co ai
```

### co create: Bootstrap New Agents

```bash
# Creates agent with best practices baked in
co create my-agent

# Generated structure:
my-agent/
├── agent.py          # Main agent code
├── tools/            # Tool functions
├── prompts/          # System prompts
└── .env             # API keys (gitignored)
```

**What you get:**
- Working agent template
- Example tools
- Best practice patterns
- Ready to run

### co auth: Managed Keys

```bash
co auth
```

**Benefits:**
- 100K free tokens to start
- No API key setup needed
- Use `co/` prefix for models
- ⭐ Star repo for +100K tokens

```python
# After co auth, just use co/ prefix
agent = Agent("bot", model="co/gemini-2.5-pro")
agent = Agent("bot", model="co/gpt-5")
```

### co ai: Interactive Coding Assistant

```bash
co ai
```

**Use cases:**
- Build new agents with guidance
- Get code review
- Fix bugs with AI help
- Learn best practices

**Workflow:**
1. `co ai` starts assistant
2. Describe what you want to build
3. AI suggests approach (plan mode)
4. Approve, then AI writes code
5. Test and iterate

---

## 5. llm_do: Quick LLM Calls

### When to Use llm_do vs Agent

**Use `llm_do()` for:**
- ✅ One-shot tasks (extract, validate, format)
- ✅ Inside event handlers (reflection, planning)
- ✅ Quick decisions without tools
- ✅ Stateless operations

**Use `Agent()` for:**
- ✅ Multi-step workflows
- ✅ Tasks requiring tools
- ✅ Conversations with memory
- ✅ Complex automation

### Pattern: Structured Data Extraction

```python
# ✅ GOOD: Use llm_do with Pydantic for extraction
from connectonion import llm_do
from pydantic import BaseModel

class Invoice(BaseModel):
    invoice_number: str
    total: float
    due_date: str
    vendor: str

def extract_invoice(text: str) -> Invoice:
    """Extract invoice data from text."""
    return llm_do(
        text,
        output=Invoice,
        system_prompt="Extract invoice details. Be precise.",
        temperature=0  # Maximum consistency
    )

# Use in agent tool
from connectonion import Agent

def process_invoice(image_path: str) -> str:
    """Process invoice from image."""
    # OCR the image first
    text = ocr_image(image_path)

    # Extract structured data
    invoice = extract_invoice(text)

    # Save to database
    save_to_db(invoice)

    return f"Invoice {invoice.invoice_number} saved. Total: ${invoice.total}"

agent = Agent("accounting", tools=[process_invoice])
```

### Pattern: Quick Validation

```python
# ✅ GOOD: Quick validation without Agent
from connectonion import llm_do

def is_safe_sql(query: str) -> bool:
    """Check if SQL query is safe."""
    result = llm_do(
        f"Is this SQL query safe (read-only, no destructive operations)?\n\nQuery: {query}\n\nReply SAFE or UNSAFE only.",
        system_prompt="You are a SQL security expert.",
        temperature=0
    )
    return "SAFE" in result.upper()

# Use in tool
def run_query(sql: str) -> str:
    """Execute SQL query."""
    if not is_safe_sql(sql):
        raise ValueError("Unsafe SQL query detected")

    return db.execute(sql)
```

### Pattern: Inside Event Handlers

```python
# ✅ GOOD: Use llm_do in events for reflection
from connectonion import Agent, after_tools, llm_do
from pydantic import BaseModel

class Reflection(BaseModel):
    what_learned: str
    next_action: str
    progress_percent: int

def add_reflection(agent):
    """Add structured reflection after tools."""
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_result' and trace['status'] == 'success':
        reflection = llm_do(
            f"""
            Tool used: {trace['name']}
            Arguments: {trace['args']}
            Result: {trace['result'][:200]}

            Reflect on progress.
            """,
            output=Reflection,
            system_prompt="Be concise and actionable.",
            temperature=0.2
        )

        # Add to conversation
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"💭 {reflection.what_learned}\n🎯 Next: {reflection.next_action} ({reflection.progress_percent}% complete)"
        })

agent = Agent("reflective", tools=[...], on_events=[after_tools(add_reflection)])
```

### Common llm_do Mistakes

**❌ Mistake 1: Using Agent when llm_do is enough**
```python
# ❌ BAD: Overkill for simple task
agent = Agent("summarizer")
summary = agent.input(f"Summarize: {long_text}")

# ✅ GOOD: Just use llm_do
from connectonion import llm_do
summary = llm_do(
    long_text,
    system_prompt="Summarize in 3 sentences.",
    temperature=0.3
)
```

**❌ Mistake 2: Not using temperature=0 for consistent tasks**
```python
# ❌ BAD: Random results for extraction
invoice = llm_do(text, output=Invoice)  # Default temp=0.1, but could be more consistent

# ✅ GOOD: Use temperature=0 for extraction
invoice = llm_do(text, output=Invoice, temperature=0)  # Maximum consistency
```

**❌ Mistake 3: Not using structured output**
```python
# ❌ BAD: Parsing string output
result = llm_do("Analyze sentiment: I love this!")
sentiment = "positive" if "positive" in result.lower() else "negative"  # Fragile!

# ✅ GOOD: Use Pydantic for structure
class Sentiment(BaseModel):
    sentiment: str  # "positive" | "negative" | "neutral"
    confidence: float

result = llm_do("Analyze sentiment: I love this!", output=Sentiment)
print(result.sentiment)  # Type-safe!
```

### Model Selection for llm_do

```python
# ✅ Default: Fast and cheap
llm_do("Quick task")  # Uses gpt-4o-mini

# ✅ For complex reasoning
llm_do("Complex analysis", model="co/gemini-2.5-pro")

# ✅ For structured output (Anthropic 4.5+ only)
from pydantic import BaseModel
class Data(BaseModel):
    value: str

llm_do("Extract data", output=Data, model="co/claude-sonnet-4-5")  # ✅ Works
# llm_do("Extract data", output=Data, model="co/claude-sonnet-4")  # ❌ Fails - no structured output support
```

---

## System Prompts: Organization

### The Problem: Prompts Mixed with Code

```python
# ❌ BAD: Long prompt in code
agent = Agent(
    "expert",
    system_prompt="""
    You are a senior software engineer with 10 years of experience.

    Your expertise includes:
    - Python best practices and PEP 8
    - Design patterns and SOLID principles
    - Performance optimization
    - Security considerations

    Review Guidelines:
    - Be constructive, not critical
    - Explain why something should be changed
    - Provide code examples when suggesting improvements
    - Acknowledge good practices when you see them

    When reviewing code:
    1. Check for syntax errors first
    2. Then look at structure and organization
    3. Finally suggest optimizations

    Always be respectful and helpful.
    """
)
```

**Problems:**
- Hard to read and edit
- No syntax highlighting
- Difficult to version control changes
- Can't reuse across agents
- No markdown formatting

### The Solution: Prompts as Files

```python
# ✅ GOOD: Prompt in separate file
agent = Agent("expert", system_prompt="prompts/code_reviewer.md")
```

**File: prompts/code_reviewer.md**
```markdown
# Senior Code Reviewer

You are a senior software engineer with 10 years of experience.

## Expertise
- Python best practices and PEP 8
- Design patterns and SOLID principles
- Performance optimization
- Security considerations

## Review Guidelines
- Be constructive, not critical
- Explain why something should be changed
- Provide code examples when suggesting improvements
- Acknowledge good practices when you see them

## Process
1. Check for syntax errors first
2. Then look at structure and organization
3. Finally suggest optimizations

Always be respectful and helpful.
```

**Benefits:**
- ✅ Syntax highlighting in editor
- ✅ Easy to read and edit
- ✅ Git shows clear prompt changes
- ✅ Markdown formatting works
- ✅ Can reuse across agents
- ✅ Can be reviewed in PRs

### Organizing Prompts

**Simple project:**
```
project/
├── agent.py
└── prompts/
    ├── assistant.md
    └── expert.md
```

**Complex project with roles:**
```
project/
├── agent.py
└── prompts/
    ├── support/
    │   ├── tier1.md
    │   ├── tier2.md
    │   └── escalation.md
    ├── engineering/
    │   ├── frontend.md
    │   ├── backend.md
    │   └── devops.md
    └── analysis/
        ├── financial.md
        ├── marketing.md
        └── product.md
```

### Pattern: Environment-Based Prompts

```python
# ✅ GOOD: Different prompts per environment
import os
from connectonion import Agent

env = os.getenv("ENV", "development")
prompt_path = f"prompts/{env}/assistant.md"

agent = Agent("assistant", system_prompt=prompt_path)
```

**Structure:**
```
prompts/
├── development/
│   └── assistant.md      # Verbose, helpful errors
├── staging/
│   └── assistant.md      # Production-like
└── production/
    └── assistant.md      # Concise, fast
```

### Pattern: Prompt Templates

```python
# ✅ GOOD: Generate prompts from templates
def create_specialist_prompt(specialty: str, years: int) -> str:
    """Generate specialized prompt from template."""
    template = """
# {specialty} Expert

You are a {specialty} expert with {years} years of experience.

## Core Competencies
- Deep knowledge of {specialty} best practices
- Problem-solving in {specialty} domain
- Mentoring junior team members

## Approach
- Be specific and actionable
- Provide examples when helpful
- Consider edge cases
"""
    return template.format(specialty=specialty, years=years)

# Use it
from connectonion import Agent

agent = Agent(
    "python_expert",
    system_prompt=create_specialist_prompt("Python", 10)
)
```

### Pattern: Dynamic Prompt Loading

```python
# ✅ GOOD: Load different prompts based on task
from pathlib import Path
from connectonion import Agent

def get_agent_for_task(task_type: str) -> Agent:
    """Select appropriate agent based on task type."""

    prompt_map = {
        "technical": "prompts/technical_expert.md",
        "creative": "prompts/creative_writer.md",
        "analytical": "prompts/data_analyst.md",
    }

    prompt_file = prompt_map.get(task_type, "prompts/general.md")

    return Agent(
        f"{task_type}_agent",
        system_prompt=prompt_file,
        tools=[...]  # Add appropriate tools
    )

# Use different agents for different tasks
tech_agent = get_agent_for_task("technical")
creative_agent = get_agent_for_task("creative")
```

### Pattern: Validate Prompts Exist

```python
# ✅ GOOD: Safe prompt loading with fallback
from pathlib import Path
from connectonion import Agent

def create_agent_safely(name: str, prompt_path: str, tools: list) -> Agent:
    """Create agent with prompt validation."""
    path = Path(prompt_path)

    if not path.exists():
        print(f"⚠️  Prompt {prompt_path} not found, using default")
        return Agent(name, tools=tools)

    if path.stat().st_size == 0:
        print(f"⚠️  Prompt {prompt_path} is empty, using default")
        return Agent(name, tools=tools)

    return Agent(name, system_prompt=path, tools=tools)

# Use it
agent = create_agent_safely("assistant", "prompts/assistant.md", [search, calculate])
```

### Common Prompt Mistakes

**❌ Mistake 1: Overly complex instructions**
```markdown
❌ BAD:

You are an AI assistant with advanced natural language processing capabilities,
leveraging state-of-the-art transformer architectures to provide comprehensive
responses across multiple domains of expertise including but not limited to...

[500 more words]
```

**✅ Fix: Be concise and clear**
```markdown
✅ GOOD:

# Helpful Assistant

You are a helpful assistant who provides clear, accurate answers.

Be concise and to the point.
```

**❌ Mistake 2: Too many rules**
```markdown
❌ BAD:

## Rules
1. Always do X
2. Never do Y
3. If Z then A
4. Unless B then C
[50 more rules]
```

**✅ Fix: Focus on principles**
```markdown
✅ GOOD:

## Guidelines
- Be helpful and respectful
- Provide accurate information
- Ask for clarification when needed
```

**❌ Mistake 3: No examples**
```markdown
❌ BAD:

Extract invoice data from text.
```

**✅ Fix: Include examples**
```markdown
✅ GOOD:

# Invoice Extractor

Extract invoice data from text.

## Example

Input: "Invoice #12345 dated 2024-01-15, total $1,234.56"

Output:
- Number: 12345
- Date: 2024-01-15
- Total: 1234.56
```

### Prompt File Checklist

- [ ] Clear role/title at the top
- [ ] Concise instructions (not a novel)
- [ ] Markdown formatting for readability
- [ ] Examples when helpful
- [ ] Principles over rules
- [ ] Version controlled with code
- [ ] Named clearly (role_purpose.md)

---

## 7. Prompt Engineering: Trust the Model

### Core Philosophy

**Don't force, suggest.** Trust the model to make good decisions with background information.

```markdown
# ❌ BAD: Too forceful
**IMPORTANT: You MUST follow these rules:**
1. ALWAYS use tool X before tool Y
2. NEVER do Z under any circumstances
3. CRITICAL: Check A, B, and C every time

# ✅ GOOD: Provide context
Note: Tool X is available for common case A. Tool Y works well for case B.

When dealing with Z, consider the trade-offs between performance and accuracy.
```

**Why:** Models are smart. Over-constraining reduces their ability to reason and adapt.

### Pattern: Notes Over Commands

```markdown
# ❌ BAD: Command-style
**MUST READ THE ENTIRE FILE BEFORE EDITING!**
**ALWAYS VALIDATE INPUT!**
**NEVER USE TRY-EXCEPT WITHOUT EXPLICIT PERMISSION!**

# ✅ GOOD: Informative style
Note: Reading the full file helps understand context before making changes.

Try-except can hide errors - let programs crash unless you need resource cleanup.
```

**Why:** "MUST" and "NEVER" create rigidity. Notes provide reasoning and let the model decide.

### Pattern: Explain Why, Not Just What

```markdown
# ❌ BAD: Rules without reason
- Use temperature=0 for extraction
- Use class instances for tools
- Put prompts in files

# ✅ GOOD: Reasoning included
- Use temperature=0 for extraction — ensures consistent output across runs
- Use class instances for tools — state persists across calls, cleaner than passing methods
- Put prompts in files — easier to edit, version control, and reuse
```

**Why:** Models understand reasoning better than arbitrary rules. They can apply principles to new situations.

### Pattern: Suggest, Don't Dictate

```markdown
# ❌ BAD: Dictating approach
**CRITICAL WORKFLOW:**
1. ALWAYS enter plan mode first
2. MUST load all guides
3. REQUIRED: Get approval before ANY code

# ✅ GOOD: Suggesting workflow
Note: For complex tasks, plan mode helps design before implementation.

Relevant guides (load as needed): best-practices, tools, events.

Consider getting user input on the approach before writing code.
```

**Why:** "ALWAYS", "MUST", "REQUIRED" remove the model's judgment. Suggestions preserve flexibility.

### Pattern: Background Info Over Instructions

```markdown
# ❌ BAD: Too many instructions
**IMPORTANT RULES:**
- Tools must have type hints
- Docstrings become descriptions
- Return types matter
- Class instances auto-discover methods
- NO utils.py files
- NO try-except unless explicitly needed
- Format: MarkdownV2 only
- ... (50 more rules)

# ✅ GOOD: Concise principles
Tools = Python functions with type hints. Docstrings → descriptions.

Pass class instances to share state across tool calls.

Keep helpers with features (avoid utils.py). Let errors crash (see real issues).
```

**Why:** Long rule lists overwhelm. Core principles are memorable and generalizable.

### Common Mistakes

**❌ Too many "IMPORTANT" tags**
```markdown
**IMPORTANT:** Do X
**CRITICAL:** Do Y
**MUST:** Do Z
```
Everything is important = nothing is important.

**✅ Reserve emphasis for truly critical items**
```markdown
Note: X works well for common cases.

When dealing with Y, consider the trade-offs.

Critical: Z can cause data loss - verify before proceeding.
```

**❌ Removing model's judgment**
```markdown
NEVER use approach A
ALWAYS use approach B
```
What if context requires A?

**✅ Explain trade-offs**
```markdown
Approach A is simpler but less flexible.
Approach B handles edge cases better but adds complexity.
```

### Why This Matters

**Over-constraining prompts:**
- Reduces model reasoning ability
- Creates brittleness (breaks in new situations)
- Harder to maintain (many rules to update)
- Model focuses on rules, not user intent

**Informative prompts:**
- Leverage model intelligence
- Adapt to new situations
- Easy to update (change principles, not rules)
- Model focuses on solving the actual problem

### Real Example

```markdown
# ❌ Over-constrained system reminder
<system-reminder>
**CRITICAL INSTRUCTIONS - FOLLOW EXACTLY:**
1. YOU MUST call load_guide("best-practices") FIRST
2. YOU MUST NEVER write code before loading guides
3. ALWAYS enter plan mode for ANY agent creation
4. REQUIRED: Load ALL relevant guides before proceeding
</system-reminder>

# ✅ Trust-based system reminder
<system-reminder>
Note: If unclear about ConnectOnion concepts, load relevant guides first.
Start with `load_guide("best-practices")` for core principles,
then load other guides as needed (tools, events, llm_do, etc).
</system-reminder>
```

The second version:
- Gives the same information
- Doesn't force a specific workflow
- Explains when/why to use guides
- Trusts the model to decide

### Don't Put Everything in System Prompt

**Use system-reminders for contextual guidance** - trigger hints at the right moment instead of loading everything upfront.

```markdown
# ❌ BAD: Everything in main system prompt
System prompt (loaded always):
- YAGNI principles
- Event usage rules
- Class-based tool patterns
- CLI command documentation
- Prompt engineering guidelines
- Error handling best practices
- ... (thousands of lines)

# ✅ GOOD: Contextual system-reminders
System prompt: Core philosophy and basics

System reminders (trigger when relevant):
- plan_mode.md → triggers on enter_plan_mode tool
- simplicity.md → triggers on edit/write tools
- security.md → triggers on bash tool
```

**Why:**
- **Focused context** - Agent sees guidance when needed, not all at once
- **Reduced noise** - Less irrelevant information to parse
- **Better decisions** - Context matches current action
- **Maintainable** - Update specific reminders without touching main prompt

**Example system-reminder structure:**

```markdown
---
name: plan-mode
triggers:
  - tool: enter_plan_mode
---

<system-reminder>
Note: If unclear about ConnectOnion concepts, load relevant guides first.
Start with `load_guide("best-practices")` for core principles,
then load other guides as needed (tools, events, llm_do, etc).
</system-reminder>
```

**Available trigger types:**
- `tool:` - Trigger before/after specific tool usage
- `intent:` - Trigger when user intent matches (like "build")

This keeps the main system prompt lean and provides just-in-time guidance.

---

## Summary

### The 7 Core Principles

1. **YAGNI**: Don't add complexity until you need it
   - Let programs crash to see real errors
   - No utils.py - keep functions with features
   - Return raw data, let agent format

2. **Events**: Use the right event at the right time
   - Use `after_tools` for message injection (NOT `after_each_tool`)
   - Use `llm_do` inside events for reasoning
   - Let events fail fast - don't hide errors

3. **Share State**: Use classes when tools need shared context
   - Browser instance, database connection, API client
   - Pass class instance, auto-discovers all methods
   - State persists across tool calls in same conversation

4. **CLI Commands**: Use co create & co auth
   - `co auth` for managed keys (100K free tokens)
   - `co create` to bootstrap new agents
   - `co ai` for interactive coding assistant

5. **llm_do**: One-shot LLM calls for quick tasks
   - Use Pydantic models for structured output
   - Use temperature=0 for consistency
   - Don't use Agent when llm_do is enough

6. **Prompts**: Keep prompts in files, not code
   - Better editing and version control
   - Organize by role/environment
   - Be concise, include examples

7. **Prompt Engineering**: Trust the model
   - Suggest, don't force - use "Note:" not "MUST"
   - Explain why, not just what - models understand reasoning
   - Background info over instructions - let model decide
   - Avoid over-constraining - preserve model's judgment

### Quick Decision Guide

**Should I add try-except?**
→ No, unless you need resource cleanup or better error messages

**Should I create utils.py?**
→ No, keep helper functions with the features that use them

**Should I format tool output?**
→ No, return raw data and let the agent format

**Which event should I use?**
→ Use `after_tools` for message injection, `after_each_tool` only for logging

**Should I use Agent or llm_do?**
→ Use `llm_do` for one-shot tasks, Agent for multi-step workflows

**Should I put the prompt in code or a file?**
→ File, always. Easier to edit and version control

**Do my tools need shared state?**
→ Yes? Use a class. No? Use simple functions

**Should I use "MUST" and "IMPORTANT" in prompts?**
→ No, use "Note:" and explain why - trust the model to decide

---

## Next Steps

- Read [Agent Guide](concepts/agent.md) for complete Agent API
- Read [Events Guide](concepts/events.md) for all event types
- Read [llm_do Guide](concepts/llm_do.md) for structured output examples
- See [Examples](examples.md) for real-world code patterns

---

**Remember: Start simple. Add complexity only when you see the problem.**
