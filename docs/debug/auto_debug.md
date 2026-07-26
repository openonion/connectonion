# Interactive Debugging for AI Agents

**Debug your agents like you debug code** - pause at breakpoints, inspect state, modify variables, and explore "what if" scenarios.

> **Most Important:** Use arrow keys to navigate menus, or press `c` to continue. That's all you need to know to start!

## Feature Status (Updated Oct 20, 2025)

| Feature | Status | Notes |
|---------|--------|-------|
| Continue execution | ✅ Available (v0.3.2) | Press `c` or Enter |
| Edit variables (Python REPL) | ✅ Available (v0.3.2) | Press `e` for full Python shell |
| Stop debugging | ✅ Available (v0.3.2) | Press `q` to exit |
| Source code display | ✅ Available (v0.3.2) | Shows actual function with line numbers |
| Next action preview | ✅ Available (v0.3.2) | See what LLM plans next |
| **Ask AI for help** | 🚧 Coming by Nov 2 | Context-aware debugging assistance |
| **View execution trace** | 🚧 Coming by Nov 2 | Full timeline visualization |
| **Toggle step mode** | 🚧 Coming by Nov 2 | Pause at every tool |
| **Universal commands** | 🚧 Coming by Nov 2 | `/menu`, `/continue`, `?` |

**Current version:** v0.3.2
**Next release:** v0.4.0 (targeting Nov 2, 2025)

## Quick Start

```python
from connectonion import Agent, xray

@xray  # Tools with @xray become breakpoints
def search_emails(query: str):
    return api.search(query)

def send_email(to: str, body: str):
    return api.send(to, body)

agent = Agent(
    name="email_assistant",
    tools=[search_emails, send_email]
)

# Launch interactive debug session
agent.auto_debug()
```

**What happens:**

```
🔍 Interactive Debug Session Started
Agent: email_assistant | Tools: 2

💡 Quick Tips:
  - Tools with @xray will pause for inspection
  - Use arrow keys to navigate menus
  - Press '?' anytime for help

Type your message to the agent:
> Send email to John

────────────────────────────────────────────────────

Iteration 1/10
→ LLM Request (co/gemini-3.6-flash)
← LLM Response (234ms): 2 tool calls

→ Tool: search_emails({"query": "John"})
← Result (123ms): Found 1 email from john@company.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@xray BREAKPOINT: search_emails

Local Variables:
  query = "John"
  result = "Found 1 email from john@company.com"
  tool_args = {"query": "John"}

Context:
  User: "Send email to John"
  Iteration: 1/10
  Tools executed: []
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What do you want to do?
  → Continue execution 🚀       [c or Enter]
    Edit values 🔍             [e]
    Quit debugging 🚫          [q]

💡 Coming soon (by Nov 2): Ask AI [a], View trace [v], Step mode [s]
>
```

**Press `c` or use arrow to select "Continue":**

```
> c

→ Tool: send_email(to="john@company.com", body="Following up...")
← Result (187ms): Email sent successfully

✓ Task complete (1.5s)

Type your message to the agent:
>
```

---

`★ Insight ─────────────────────────────────────`
**Why this design works:**
1. **Always show tips** - Learn by doing, no documentation lookup needed
2. **Multiple input methods** - Arrow keys (beginner) or shortcuts (power user)
3. **Universal commands** - `/menu`, `/continue`, `?` work everywhere
4. **Clear mode indicators** - Always know if you're in AI, Python, or menu mode
`─────────────────────────────────────────────────`

---

## The Interactive Menu

At every `@xray` breakpoint, you see this menu:

```
What do you want to do?
  → Continue execution 🚀       [c or Enter]
    Edit values 🔍             [e]
    Quit debugging 🚫          [q]

💡 Coming soon (by Nov 2): Ask AI [a], View trace [v], Step mode [s]
>
```

### Two Ways to Select

**Method 1: Arrow Keys** (Beginner-friendly)
- Use `↑` and `↓` to highlight option
- Press `Enter` to select

**Method 2: Shortcuts** (Power user) - ✅ Available now
- Type `c` for Continue
- Type `e` for Edit
- Type `q` for Quit

**🚧 Coming by Nov 2:**
- Type `a` for Ask AI
- Type `v` for View trace
- Type `s` for Step mode

Both methods do exactly the same thing - use whichever feels natural!

---

## Continue Execution ✅

The most common action - just press `c` or `Enter`:

```
What do you want to do?
  → Continue execution       [Enter or c]
    ...

> c

→ Execution resumes...
→ Tool: send_email(...)
✓ Complete
```

**Continue works from anywhere:**
- From menu: `c` or `Enter`
- From AI mode: `/continue`
- From Python mode: `/continue` or `Ctrl+D`

---

## Ask AI for Help 🚧

**Coming by Nov 2, 2025**

Get context-aware help from AI about what's happening:

```
> a

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI Help Mode - Ask questions about execution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ai> why did it only find 1 email?

🤖 AI: The search used query="John" which is a broad search term.
The API might be limiting results, or there's actually only 1 email
from someone named John in the database.

You can check the tool's implementation or test with a modified
result to see how the agent handles multiple emails.

ai> how can I test with more emails?

🤖 AI: You can switch to Python mode and modify the result variable:

1. Type '/menu' to go back to the menu
2. Select 'Edit variables (Python)'
3. Set: result = ["email1@ex.com", "email2@ex.com", "email3@ex.com"]
4. Continue execution to see how the agent handles multiple results

ai> what should the query have been?

🤖 AI: Based on your input "Send email to John", the query "John"
is reasonable. If you want more specific results, the agent could
have used additional context like "urgent John" or "recent John"
to narrow down the search.

ai>

💡 Tip: '/menu' = back to menu | '/continue' = resume execution | '?' = help
```

**AI knows everything:**
- Your agent's code and behavior
- Current execution state
- All variables and results
- Previous tool calls
- User's original request

**Ask questions like:**
- `why did this happen?`
- `is this the right result?`
- `how can I test edge cases?`
- `what should I do next?`

**Getting back:**
- Type `/menu` → Return to breakpoint menu
- Type `/continue` → Resume execution immediately
- Type `?` → Show help

---

## Edit Variables (Python) ✅

Modify variables to test "what if" scenarios:

```
> e

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Python Editor - Modify variables to test scenarios
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Available variables: query, result, tool_args

>>> result
'Found 1 email from john@company.com'

>>> # Test: What if we found 3 emails?
>>> result = ["email1@ex.com", "email2@ex.com", "email3@ex.com"]

>>> result
['email1@ex.com', 'email2@ex.com', 'email3@ex.com']

>>> # Test: What if we found no emails?
>>> result = []

>>> result
[]

>>>

💡 Tip: '/menu' = back to menu | '/continue' or Ctrl+D = resume | '?' = help
```

**This is a full Python REPL:**
- View variables: `>>> result`
- Modify data: `>>> result = new_value`
- Execute code: `>>> len(result)`
- Multi-line: Just keep typing

**Test scenarios:**
```python
>>> # Empty results
>>> result = []

>>> # Large dataset
>>> result = [f"email{i}@example.com" for i in range(100)]

>>> # Error case
>>> result = {"error": "API timeout", "status": 500}

>>> # Edge case
>>> result = "unusual@格式.com"  # Unicode email
```

**Getting back:**
- Type `/menu` → Return to breakpoint menu
- Type `/continue` → Resume with modified variables
- Press `Ctrl+D` → Resume with modified variables
- Type `?` → Show help

---

## View Execution Trace 🚧

**Coming by Nov 2, 2025**

See the full execution history:

```
> v

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Execution Trace
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Timeline:
  [0] user_input: "Send email to John"
  [1] llm_call: 234ms → 2 tool calls requested
  [2] tool: search_emails ✓ 123ms ← YOU ARE HERE
  [3] (pending) tool: send_email

Conversation Messages:
  [0] system: "You are an email assistant..."
  [1] user: "Send email to John"
  [2] assistant: [tool_calls: search_emails, send_email]
  [3] tool: "Found 1 email from john@company.com" ← CURRENT
  [4] (pending) tool: send_email

Agent State:
  Name: email_assistant
  Model: co/gemini-3.6-flash
  Iteration: 1/10
  Tools available: [search_emails, send_email]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Press Enter to return to menu...
```

**Shows:**
- Timeline of all events
- Conversation history
- Current position
- Pending operations
- Agent configuration

---

## Toggle Step Mode 🚧

**Coming by Nov 2, 2025**

Pause at **EVERY tool**, not just `@xray` tools:

```
> s

✓ Step mode enabled - will pause at EVERY tool

What do you want to do?
  → Continue execution       [Step Mode: ON]
    Ask AI for help          [a]
    Edit variables (Python)  [e]
    View execution trace     [v]
    Toggle step mode        [s] ← Toggle off
    Stop debugging          [q]

💡 Use ↑↓ arrows and Enter, or type shortcuts
>
```

**What happens in step mode:**

```
> c

→ Tool: validate_input(...)    [No @xray, but pauses anyway!]
← Result: Valid

[BREAKPOINT - Menu appears]

> c

→ Tool: fetch_data(...)
← Result: 50 records

[BREAKPOINT - Menu appears]

> c

→ Tool: transform_data(...)
← Result: Transformed

[BREAKPOINT - Menu appears]

> s    [Toggle step mode OFF]

✓ Step mode disabled - only pausing at @xray tools

> c

→ Tool: save_result(...)
→ Tool: send_notification(...)
→ Tool: log_activity(...)
✓ Complete (no more pauses)
```

**Use step mode when:**
- Debugging complex multi-tool workflows
- Understanding unfamiliar agent behavior
- Tracing execution step-by-step
- Finding which tool causes problems

---

## Universal Commands 🚧

**Coming by Nov 2, 2025**

These commands work **everywhere** (menu, AI mode, Python mode):

| Command | What It Does |
|---------|--------------|
| `/menu` | Return to breakpoint menu |
| `/continue` | Resume execution immediately |
| `?` or `/help` | Show help |
| `/quit` | Exit debug session |

**Example in AI mode:**
```
ai> asking questions...

ai> /continue

→ Resuming execution...
✓ Complete
```

**Example in Python mode:**
```
>>> result = modified_value

>>> /continue

→ Resuming with modified variables...
✓ Complete
```

**Always there when you need them!**

---

## Complete User Journey Example

Let's walk through a full debugging session:

```python
@xray
def search_products(query: str):
    return api.search(query)

def filter_results(products: list, criteria: dict):
    return [p for p in products if matches(p, criteria)]

def rank_by_popularity(products: list):
    return sorted(products, key=lambda p: p['sales'], reverse=True)

agent = Agent(
    name="shop_assistant",
    tools=[search_products, filter_results, rank_by_popularity]
)

agent.auto_debug()
```

**Session:**

```
Type your message to the agent:
> Find popular purple shoes under $100

────────────────────────────────────────────────────

→ Tool: search_products({"query": "purple shoes"})
← Result: Found 15 products

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@xray BREAKPOINT: search_products

Local Variables:
  query = "purple shoes"
  result = [15 product objects]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What do you want to do?
  → Continue execution 🚀       [c or Enter]
    Edit values 🔍             [e]
    Quit debugging 🚫          [q]

💡 Coming soon (by Nov 2): Ask AI [a], View trace [v], Step mode [s]
> a    [Select "Ask AI"]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI Help Mode - Ask questions about execution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ai> what if no products were found?

🤖 AI: Good question! If search_products returned an empty list,
the filter_results and rank_by_popularity tools would also receive
empty lists. You can test this scenario by modifying the result
in Python mode.

ai> /menu

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@xray BREAKPOINT: search_products
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What do you want to do?
  → Continue execution
    Ask AI for help
    Edit variables (Python)
    ...

> e    [Select "Edit variables"]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Python Editor - Modify variables to test scenarios
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

>>> result = []    [Test empty result]

>>> /continue

→ Resuming with modified variables...

→ Tool: filter_results({"products": [], "criteria": {"price": {"max": 100}}})
← Result: []

→ Tool: rank_by_popularity({"products": []})
← Result: []

Agent: "Sorry, no purple shoes under $100 are available."

✓ Task complete

[Success! We tested the empty result scenario and confirmed the agent handles it correctly]
```

---

`★ Insight ─────────────────────────────────────`
**Complete workflow:**
1. **Hit breakpoint** → See state automatically
2. **Ask AI** → Understand what's happening
3. **Edit variables** → Test edge cases
4. **Continue** → See results
5. **Iterate** → Build confidence in agent behavior

**No context switching to docs, no memorizing commands - tips guide you through!**
`─────────────────────────────────────────────────`

---

## Real-World Examples

### Example 1: Debugging Wrong Email Recipient

```python
@xray
def find_contact(name: str):
    return contacts_db.search(name)[0]  # Bug: returns first match

@xray
def send_email(to: str, message: str):
    return email_api.send(to, message)

agent = Agent("email_bot", tools=[find_contact, send_email])
agent.auto_debug()
```

**Session:**

```
> Send birthday wishes to Mike

→ Tool: find_contact({"name": "Mike"})
← Result: mike.jones@old-company.com

[BREAKPOINT]

> a

ai> is this the right email address?

🤖 AI: The result shows "old-company.com" which might be outdated.
The find_contact tool returns the first match, but there could be
multiple Mikes in the database. You should verify this is the
correct person before sending.

ai> how can I use the correct email?

🤖 AI: You can modify the result in Python mode to test with the
correct email, then fix the find_contact tool to use better matching
logic (like most recent contact, or prompt user to choose).

ai> /menu

> e

>>> result = "mike.anderson@current-company.com"

>>> /continue

→ Tool: send_email(to="mike.anderson@current-company.com", ...)
✓ Email sent to correct person!

[After debugging, you fix find_contact to return most recent contact]
```

---

### Example 2: Testing Edge Cases with Step Mode

```python
agent = Agent("data_processor", tools=[
    load_file,
    parse_data,
    validate_schema,
    transform_data,
    save_results
])

agent.auto_debug()
```

**Session:**

```
> Process users.csv

→ Tool: load_file({"path": "users.csv"})
← Result: Loaded 1000 rows

[BREAKPOINT]

> s    [Enable step mode to see ALL tools]

✓ Step mode enabled

> c

→ Tool: parse_data({"rows": 1000})
← Result: Parsed 1000 records

[BREAKPOINT - Step mode pauses here even without @xray]

> e

>>> # Test: What if parsing found corrupt data?
>>> result = {"valid": 800, "corrupt": 200, "data": [...]}

>>> /continue

→ Tool: validate_schema({"valid": 800, "corrupt": 200})
← Result: Validation failed - 200 corrupt records

[BREAKPOINT]

> a

ai> should the agent stop or continue with valid records?

🤖 AI: The validate_schema tool failed, so the agent should either:
1. Stop and report the error
2. Continue with only the 800 valid records
3. Attempt to fix the corrupt records

Check your error handling logic in the agent's system prompt.

ai> /continue

→ Tool: transform_data(...)
✓ Agent handled error gracefully!

[After debugging, you improve error handling in system prompt]
```

---

### Example 3: Prompt Engineering

```python
agent = Agent(
    name="support_bot",
    system_prompt="Help customers with their orders.",
    tools=[check_order, cancel_order, refund_order]
)

agent.auto_debug()
```

**Session:**

```
> Cancel my order and refund me

→ Tool: cancel_order({"order_id": "auto-detected"})
← Result: Order cancelled

[BREAKPOINT]

> a

ai> should the agent verify the order exists first?

🤖 AI: Yes! The agent should use check_order BEFORE cancelling
to verify:
1. Order exists
2. Order status allows cancellation
3. Order belongs to the user

Then after cancelling, check_order again to verify success before
processing refund.

ai> what should I add to the system prompt?

🤖 AI: Add this to your system_prompt:

"When handling order operations:
1. Always use check_order first to verify order exists and status
2. After making changes, verify success with check_order again
3. Only proceed to next step after confirming previous step succeeded"

ai> /continue

→ Tool: refund_order(...)
← Result: Refund processed

✓ Complete

[Exit session, update system_prompt with the improvement]
```

---

## Best Practices

### 1. Strategic `@xray` Placement

```python
@xray  # ✅ External API calls
def fetch_user_data(user_id: str):
    return api.get(f"/users/{user_id}")

@xray  # ✅ Database operations
def save_order(order: dict):
    return db.insert("orders", order)

def format_date(date: str):  # ❌ Simple utility - no need
    return datetime.parse(date)

@xray  # ✅ Complex business logic
def calculate_price(items: list, discounts: dict):
    # 50 lines of pricing logic
    return total
```

**Add `@xray` to:**
- API calls
- Database operations
- Complex logic
- Tools that often fail
- Tools with important business logic

**Skip `@xray` for:**
- Simple utilities
- Format converters
- Pure functions with no side effects

**Or use step mode to see everything!**

---

### 2. Use AI to Understand

Before modifying anything, ask AI:

```
ai> what is this tool doing?
ai> why did it return this result?
ai> is this the expected behavior?
ai> what edge cases should I test?
```

**AI has full context** - it knows your code, execution state, and history.

---

### 3. Test Edge Cases in Python Mode

```python
>>> # Empty results
>>> result = []

>>> # Large dataset
>>> result = [item for item in range(10000)]

>>> # Error responses
>>> result = {"error": "API timeout", "retry_after": 60}

>>> # Malformed data
>>> result = "unexpected string instead of list"

>>> # Unicode/special characters
>>> result = {"name": "用户名", "emoji": "🎉"}
```

**Time-travel debugging** - change one variable, see entire agent behavior change.

---

### 4. Step Mode for Complex Workflows

```python
# Normal: Only @xray breakpoints
agent.auto_debug()

# Deep dive: See every tool
agent.auto_debug(step=True)

# Or toggle during session
> s    [Enable step mode]
> s    [Disable step mode]
```

**Use step mode when:**
- You don't know which tool is causing problems
- Understanding a complex workflow
- Tracing data flow through multiple tools
- Learning how an unfamiliar agent works

---

### 5. Always Check Trace Before Editing

```
> v    [View execution trace]

[See full context]

> [Enter to go back]

> e    [Now edit with full understanding]
```

**Understand before you modify!**

---

## Command Reference

### Menu Options (v0.3.2)

| Option | Shortcut | Status | Description |
|--------|----------|--------|-------------|
| Continue execution | `c` or `Enter` | ✅ Available | Resume agent execution |
| Edit variables (Python) | `e` | ✅ Available | Enter Python REPL to modify state |
| Stop debugging | `q` | ✅ Available | Exit debug session |
| **Ask AI for help** | `a` | 🚧 Nov 2 | Enter AI mode for questions |
| **View execution trace** | `v` | 🚧 Nov 2 | Show full execution history |
| **Toggle step mode** | `s` | 🚧 Nov 2 | Pause at ALL tools (not just @xray) |

### Universal Commands 🚧 (Coming by Nov 2)

| Command | Description |
|---------|-------------|
| `/menu` | Return to breakpoint menu |
| `/continue` | Resume execution immediately |
| `?` or `/help` | Show help |
| `/quit` | Exit debug session |

### AI Mode Commands 🚧 (Coming by Nov 2)

| Input | What Happens |
|-------|--------------|
| Natural question | AI answers with full context |
| `/menu` | Back to menu |
| `/continue` | Resume execution |
| `?` | Show help |

### Python Mode Commands ✅ (Available in v0.3.2)

| Input | What Happens |
|-------|--------------|
| Python code | Execute in current scope |
| Exit REPL | Press `Ctrl+D` to continue execution |

---

## When to Use

### ✅ Perfect For

- **Development** - Building and testing agents
- **Debugging** - Finding why agents behave unexpectedly
- **Learning** - Understanding how agents make decisions
- **Testing edge cases** - Exploring "what if" scenarios
- **Prompt engineering** - Discovering what instructions work best
- **Exploring behavior** - Seeing tool execution in detail

### ❌ Not For

- **Production** - Requires human interaction
- **Automated tests** - Use assertions instead
- **Simple scripts** - Overkill for basic tasks
- **CI/CD pipelines** - Not non-interactive

### 🤝 Use Together With

- **Unit tests** - Tests verify expected behavior automatically
- **Logging** - Logs record what happened for post-mortem
- **`@xray` decorator** - Visibility into tool execution
- **Step mode** - Deep visibility when needed
- **Type hints** - Better variable inspection

---

## FAQ

**Q: How do I continue execution?**
A: Three ways:
- From menu: Press `c` or `Enter`
- From AI/Python mode: Type `/continue` or press `Ctrl+D` (Python only)
- From anywhere: Type `/continue`

**Q: How do I go back to the menu?**
A: Type `/menu` from any mode (AI or Python)

**Q: What's the difference between `@xray` and step mode?**
A:
- **`@xray` breakpoints** - Pause only at marked tools (selective)
- **Step mode** - Pause at EVERY tool (comprehensive)

Toggle step mode with `s` in the menu.

**Q: How do I ask AI for help?**
A: Press `a` in the menu, then ask questions naturally:
```
ai> why did this happen?
ai> what should I do?
ai> how can I test this?
```

**Q: How do I modify variables?**
A: Press `e` in the menu, then use Python:
```
>>> result = new_value
>>> /continue
```

**Q: Can I switch between AI and Python modes?**
A: Yes! Use `/menu` to go back, then select the other mode.

**Q: What if I forget the commands?**
A: Tips are always shown at the bottom of each mode. Or press `?` for help.

**Q: Works in Jupyter notebooks?**
A: Yes! Works in any Python environment with terminal support.

**Q: Can I still use `agent.input()` directly?**
A: Yes - `.auto_debug()` is optional. Use it only when you need interactive debugging.

**Q: Is this slow?**
A: No - execution speed is the same. Pausing only happens at breakpoints.

**Q: Production usage?**
A: No - this is a development tool only. Don't use in production.

**Q: What if I have no `@xray` tools?**
A: The session automatically enables step mode (pauses at all tools).

**Q: Can I script or automate debugging?**
A: Not currently - this is an interactive tool. For automation, use unit tests with assertions.

---

## Keyboard Shortcuts Summary (v0.3.2)

### Menu Navigation ✅
- `↑` `↓` - Move selection
- `Enter` - Select highlighted option
- `c` - Continue ✅
- `e` - Edit Python ✅
- `q` - Quit ✅

**🚧 Coming by Nov 2:**
- `a` - Ask AI
- `v` - View trace
- `s` - Step mode

### Python Mode ✅
- Type Python code
- `Ctrl+D` - Resume execution

---

`★ Insight ─────────────────────────────────────`
**Design principles:**
1. **Always show tips** - Zero documentation lookup needed
2. **Multiple paths** - Arrow keys OR shortcuts, both work
3. **Universal commands** - `/menu`, `/continue`, `?` work everywhere
4. **Clear modes** - Always know where you are (menu, AI, Python)
5. **No dead ends** - Always a way to continue or go back
`─────────────────────────────────────────────────`

---

## See Also

- [Getting Started](../quickstart.md) - ConnectOnion basics
- [`@xray` Decorator](xray.md) - Tool visibility and context
- [Tools Guide](../concepts/tools.md) - Creating tools
- [Examples](../examples.md#debugging) - More debugging examples

---

**Ready to debug?** Just call `agent.auto_debug()` and explore! 🔍

The tips will guide you through - no memorization needed.
