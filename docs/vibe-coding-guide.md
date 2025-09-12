# Vibe Coding Guide: Build Agents with Cursor AI

> **Quick Start**: Drag our docs into Cursor → Ask AI → Get your agent

## Two Ways to Get Started

### Method 1: Drag & Drop
1. **Open Cursor AI editor**
2. **Drag our documentation** into Cursor:
   - From website: Go to [docs.connectonion.com](https://docs.connectonion.com) → Drag any page
   - From local: After `co init`, drag `.co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md`
3. **Ask Cursor**: "Help me create an agent using these docs"

### Method 2: Copy All
1. **Visit** [docs.connectonion.com](https://docs.connectonion.com)
2. **Click** "Copy All Docs" (purple button in sidebar)
3. **Paste** into Cursor chat
4. **Ask Cursor**: "Help me create an agent using these docs"

## Example: What Cursor Generates

When you ask Cursor: **"Using ConnectOnion docs, create a calculator agent"**

Cursor generates:

```python
from connectonion import Agent

def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

# Create agent
calculator = Agent(
    "calculator",
    tools=[add, multiply],
    instructions="You are a helpful calculator"
)

# Use it
result = calculator.input("What is 5 plus 3?")
print(result)  # Output: "5 plus 3 equals 8"
```

## The Magic

The agent automatically:
- ✅ Understands "plus" means use `add()`
- ✅ Picks the right tool
- ✅ Returns natural language

## What to Ask Cursor

**Basic:**
```
"Using ConnectOnion docs, create a calculator agent"
```

**Advanced:**
```
"Add more math functions to this agent"
```

**Custom:**
```
"Create an agent that [your specific need]"
```

## Why It Works

Cursor + Our Docs = Complete Understanding:
- How to create agents
- How to add tools  
- Best practices
- Natural language processing

## Quick Start

1. **Install**: `pip install connectonion`
2. **Initialize**: `co init`
3. **Open in Cursor**
4. **Drag our docs** into Cursor
5. **Ask**: "Create an agent"
6. **Run**: `python agent.py`

## Get Our Docs

- **Website**: [docs.connectonion.com](https://docs.connectonion.com) → Copy All Docs
- **Local**: `.co/docs/co-vibecoding-principles-docs-contexts-all-in-one.md` (after `co init`)

---

*Drag, drop, ask. Your agent is ready!* 🎉