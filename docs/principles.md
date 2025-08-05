# Documentation Principles

## Core Philosophy

**"Show, don't tell"** - Every concept should be immediately usable.

## The 7 Principles

### 1. Start with Success
```markdown
BAD:  "ConnectOnion uses function-based tools with automatic schema generation..."
GOOD: "Build your first AI agent in 60 seconds."
```

### 2. One Concept Per Page
```markdown
BAD:  "Agents, Tools, and History" (one page)
GOOD: "Agents" | "Tools" | "History" (separate pages)
```

### 3. Code First, Explanation Second
```markdown
GOOD:
```python
@xray
def my_tool():
    print(xray.task)  # "User's request"
```
That's it! Add @xray to see inside.

BAD:
"The xray decorator provides introspection capabilities..."
```

### 4. Progressive Disclosure
```
Level 1: Quick Start (60 seconds)
Level 2: Basic Usage (5 minutes)  
Level 3: Advanced Patterns (when needed)
```

### 5. Real Output, Not Promises
```markdown
GOOD: 
Task: "Find Python tutorials"
[1] • 45ms search(query="Python tutorials")
      OUT ← "Found 10 tutorials..."

BAD:
"The trace function will show execution details"
```

### 6. Practical Examples Only
```markdown
GOOD: "Check why emergency_shutdown() was called"
BAD:  "Process abstract data with generic handler"
```

### 7. Scannable Structure
```markdown
GOOD:
## Quick Start        (2 lines of code)
## What You Get       (bullet points)
## Real Example       (10 lines max)
## Tips              (4 items max)

BAD:
Long paragraphs explaining theory...
```

## Writing Checklist

Before publishing any doc:

- [ ] Can someone use this in 60 seconds?
- [ ] Is the first example under 5 lines?
- [ ] Does it show real output?
- [ ] One main concept only?
- [ ] Mobile-friendly line lengths?
- [ ] Would I read this if I was in a hurry?

## Examples of Good Docs

### Quick Start Pattern
```
1. Show minimal working code (3-5 lines)
2. Show output
3. Say "That's it!"
4. Then explain what happened
```

### Feature Introduction Pattern
```
1. One-line description
2. Simplest possible example
3. What you can do with it (bullets)
4. Common use cases (2-3)
5. Link to more if needed
```

### API Reference Pattern
```
1. Function signature
2. One-line description
3. Minimal example
4. Parameters table
5. Return value
```

## What to Avoid

❌ **Theory before practice**
❌ **Multiple concepts per section**
❌ **Examples over 20 lines**
❌ **Unexplained output**
❌ **Abstract examples**
❌ **Dense paragraphs**
❌ **Assuming prior knowledge**

## Remember

> "The best documentation is the code itself. The second best is showing the code in action."

Every doc should make someone think: "Wow, that's simple!"