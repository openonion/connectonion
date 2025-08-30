# Tutorial Writing & UI/UX Principles

Keep it simple. That's the core philosophy. This guide outlines our principles for writing tutorials and designing the user experience.

## Core Philosophy

**Simplicity First** - If you need to explain how to use the documentation, you've already failed.

## Tutorial Writing Principles

### 1. Start Dead Simple
- First example should be the absolute minimum viable code
- No optional parameters, no advanced features
- If "Hello World" works, start there

```python
# YES - Start with this
agent = Agent("assistant")
result = agent.input("Hello")

# NO - Don't start with this
agent = Agent("assistant", model="gpt-4", temperature=0.7, 
              tools=[calculator, weather], max_iterations=5)
```

### 2. Progressive Disclosure
Build complexity gradually, one concept at a time:

1. **Basic** → Works out of the box
2. **Practical** → Common real-world use case  
3. **Advanced** → Power user features
4. **Edge Cases** → Only if necessary

### 3. Show, Don't Tell
```markdown
# BAD
The agent.input() method accepts a string parameter and returns a response.

# GOOD
```python
result = agent.input("What's 2+2?")
print(result)  # "4"
```
```

### 4. Every Code Block Must Run
- Test every example before documenting
- Include all necessary imports
- Provide real output comments
- Never show pseudo-code without marking it clearly

### 5. Explain the Why, Not Just the What
```markdown
# BAD
Set max_iterations to 10.

# GOOD  
Set max_iterations to 10 to prevent infinite loops while giving the agent 
enough attempts to complete complex tasks.
```

### 6. One Concept Per Section
Don't mix multiple concepts. Each section should teach exactly one thing.

### 7. Use Consistent Terminology
- **Agent** - Not "AI", "bot", or "assistant" 
- **Tool** - Not "function", "utility", or "action"
- **Input** - Not "prompt", "query", or "message"

## UI/UX Design Principles

### Visual Hierarchy

1. **Page Title** - Gradient text, 4xl font
2. **Section Headers** - 2xl font with icon
3. **Subsection Headers** - lg font, medium weight
4. **Body Text** - Default size, gray-600
5. **Code** - Monospace with syntax highlighting

### Color Philosophy

- **Primary Action** - Blue gradient (`from-blue-500 to-purple-600`)
- **Success** - Green (`green-500`)
- **Warning** - Yellow (`yellow-500`)
- **Error** - Red (`red-500`)
- **Text** - Gray scale (`gray-900` to `gray-400`)
- **Backgrounds** - Subtle gradients and borders

### Component Patterns

#### Info Boxes
```tsx
// Important information
<div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg border border-blue-200">

// Warning
<div className="bg-yellow-50 dark:bg-yellow-900/20 p-4 rounded-lg border border-yellow-200">

// Success
<div className="bg-green-50 dark:bg-green-900/20 p-4 rounded-lg border border-green-200">
```

#### Code Blocks
Always use `CommandBlock` for terminal commands:
```tsx
<CommandBlock commands={['pip install connectonion']} />
```

Always include copy functionality for code snippets.

#### Navigation
- Back button at top of every page
- Consistent sidebar always visible
- Breadcrumbs for deep navigation (3+ levels)

### Spacing Guidelines

- **Sections** - `space-y-12` between major sections
- **Paragraphs** - `mb-4` after paragraphs
- **Headers** - `mb-4` after headers  
- **Code blocks** - `my-6` around code
- **Lists** - `space-y-2` between items

### Responsive Design

- **Mobile First** - Design for phones, enhance for desktop
- **Single Column** - Content always in single column for readability
- **Max Width** - `max-w-4xl` for optimal reading length
- **Touch Targets** - Minimum 44px for clickable elements

## Writing Style Guide

### Voice & Tone

- **Friendly but Professional** - Like explaining to a smart colleague
- **Direct** - Get to the point quickly
- **Confident** - State facts, don't hedge
- **Humble** - Acknowledge when things are complex

### Sentence Structure

```markdown
# BAD - Too wordy
You might want to consider possibly using the trust parameter if you're 
planning to work with multiple agents.

# GOOD - Direct
Use the trust parameter for multi-agent systems.
```

### Examples Format

Always follow this structure:
1. Brief explanation (1 sentence)
2. Code example
3. Output or result
4. Why it matters (if not obvious)

### Common Mistakes to Avoid

❌ **Don't**:
- Start with edge cases
- Use jargon without explanation
- Show code that doesn't run
- Mix multiple concepts
- Use inconsistent naming
- Create walls of text
- Assume prior knowledge

✅ **Do**:
- Start simple
- Define terms on first use
- Test all code examples
- Focus on one thing
- Use consistent names
- Break up text with examples
- Explain from scratch

## Page Template Structure

Every tutorial page should follow this structure:

```markdown
# Page Title

One-line description of what this page covers.

## Overview (Optional)
Brief context if needed - 2-3 sentences max.

## Basic Usage
Simplest possible working example.

## Common Patterns
2-3 practical examples that users will actually need.

## Advanced Usage (Optional)
Power user features, only if essential.

## API Reference (Optional)
Complete parameter documentation.

## Troubleshooting (Optional)
Common errors and solutions.

## Next Steps
Where to go from here - link to related topics.
```

## Interactive Elements

### When to Use Interactive Features

- **Copy buttons** - Every code block
- **Collapsible sections** - For optional advanced content
- **Live demos** - For visual/immediate feedback features
- **Checklists** - For multi-step processes

### When NOT to Use Interactive Features

- Don't add interactivity just because you can
- Don't hide essential information behind clicks
- Don't use animations that slow down reading

## Documentation Testing Checklist

Before publishing any tutorial:

- [ ] Code examples run without errors
- [ ] Imports are included
- [ ] Output comments are accurate
- [ ] Links work correctly
- [ ] Mobile layout is readable
- [ ] Search finds the content
- [ ] Examples progress from simple to complex
- [ ] No unexplained jargon
- [ ] Page loads quickly
- [ ] Dark mode looks correct

## Quick Decisions

When in doubt:

- **Shorter is better** - Cut unnecessary words
- **Show code first** - Examples before explanation  
- **One column** - Never side-by-side layouts
- **Flat is better than nested** - Avoid deep hierarchies
- **Real examples** - Use practical, not abstract examples
- **Test it** - If you haven't run it, don't write it

## The 5-Second Rule

A new visitor should understand what your page is about and see a working example within 5 seconds of landing on it.

If they can't, simplify.

## Remember

The best documentation is the one that doesn't need documentation. Make everything so obvious that users succeed without thinking.

When users succeed quickly, you've succeeded completely.