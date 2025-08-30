# ConnectOnion Documentation

Build AI agents with Python functions. No classes, no complexity.

> **Philosophy**: Keep simple things simple, make complicated things possible.

## 🚀 Quick Start (30 seconds)

```bash
pip install connectonion
```

## ⚡ First Agent (1 minute)

```python
from connectonion import Agent

# Any function becomes a tool
def greet(name: str) -> str:
    return f"Hello {name}!"

# Create and use agent
agent = Agent("assistant", tools=[greet])
agent.input("Say hi to Alice")  # "Hello Alice!"
```

## 🎯 Real Example (2 minutes)

```python
from connectonion import Agent

def calculate(expression: str) -> str:
    """Safely evaluate a math expression."""
    return str(eval(expression))

def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Sunny and 72°F in {city}"

# Multi-tool agent
agent = Agent("helper", 
              tools=[calculate, get_weather],
              system_prompt="Be helpful and concise")

# Use it naturally
agent.input("What's 42 * 17 and how's the weather in Paris?")
# "42 * 17 = 714. The weather in Paris is sunny and 72°F."
```

## 📚 Core Learning Path

Our documentation follows a logical progression:

1. **[System Prompts](./app/prompts)** - Define what your agent does (START HERE)
2. **[Tools](./app/tools)** - Give your agent capabilities  
3. **[max_iterations](./app/max-iterations)** - Control execution safely
4. **[LLM Function](./app/llm_do)** - Direct LLM usage without agents
5. **[Trust Parameter](./app/trust)** - Multi-agent communication
6. **[@xray Decorator](./app/xray)** - Debug when needed

## 🏗️ Documentation Site Development

### Running Locally

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build
```

Open [http://localhost:3000](http://localhost:3000) to view the site.

### Directory Structure

```
docs-site/
├── app/                    # Next.js pages (all documentation)
│   ├── quickstart/        # Get started in 60 seconds
│   ├── prompts/           # System prompts guide
│   ├── tools/             # Functions as tools
│   ├── max-iterations/    # Iteration control
│   ├── examples/          # Working examples
│   └── blog/              # Design decisions
├── components/            # Reusable UI components
│   ├── DocsSidebar.tsx   # Main navigation
│   ├── CommandBlock.tsx  # Terminal commands
│   ├── CodeWithResult.tsx # Code + output display
│   └── Footer.tsx        # Site footer
├── public/
│   └── tutorials/        # Markdown documentation source
├── utils/                # Search and utilities
│   ├── searchIndex.ts    # Full-text search
│   └── copyAllDocs.ts    # Copy all docs feature
└── DOCUMENTATION_PRINCIPLES.md  # How we write docs
```

## 📝 Documentation Writing Principles

We follow the **2-5-10 Rule**:

### 2 Lines - It Works!
```python
agent = Agent("helper", tools=[greet])
agent.run("Hello")
```

### 5 Lines - It's Useful!
```python
agent = Agent("helper", 
              tools=[greet, calculate],
              system_prompt="Be helpful")
result = agent.run("Greet and calculate")
print(result)
```

### 10 Lines - It's Production-Ready!
```python
agent = Agent("helper",
              tools=[greet, calculate, search],
              system_prompt=load_prompt("assistant.md"),
              max_iterations=5,
              trust="prompt")
              
with xray.trace():
    result = agent.run(user_input)
    save_to_history(result)
```

## 🎓 Learning Paths

### Day 1 - Beginner
1. [Introduction](/) → [Quick Start](/quickstart)
2. [System Prompts](/prompts) → [Tools](/tools)
3. [Hello World Example](/examples/hello-world)

### Week 1 - Intermediate
1. [max_iterations](/max-iterations) → [LLM Function](/llm_do)
2. [Calculator](/examples/calculator) → [Weather Bot](/examples/weather-bot)
3. [@xray Decorator](/xray)

### Month 1 - Advanced
1. [Trust Parameter](/trust) → [Threat Model](/threat-model)
2. [trace() Visual Flow](/xray/trace)
3. Multi-agent Systems

## 🔧 Adding New Documentation

### Quick Process

1. **Write Tutorial** - Create markdown in `/public/tutorials/`
2. **Create Page** - Add component in `/app/[topic]/page.tsx`
3. **Update Navigation** - Edit `components/DocsSidebar.tsx`
4. **Update Search** - Add to `utils/searchIndex.ts`

### Writing Guidelines

✅ **DO:**
- Start with working code (< 5 lines)
- Show progression (simple → complex)
- Include "When to use this"
- Provide copy-paste examples
- Add interactive demos when possible

❌ **DON'T:**
- Start with theory or abstractions
- Use complex class hierarchies
- Assume prior knowledge
- Hide important details
- Write walls of text

### Page Template

```tsx
// app/your-feature/page.tsx
export default function YourFeaturePage() {
  return (
    <div className="max-w-4xl mx-auto px-8 py-12">
      {/* Quick win - working code immediately */}
      <CodeWithResult 
        code={`# 2 lines that work`}
        result={`Output`}
      />
      
      {/* Progressive examples */}
      {/* Common patterns */}
      {/* Production usage */}
    </div>
  )
}
```

## 🎯 Success Metrics

Good documentation achieves:
- **Time to First Success**: < 60 seconds
- **Concept to Code**: < 5 minutes  
- **Understanding to Production**: < 30 minutes

## 📊 Documentation Coverage

| Section | Status | Coverage |
|---------|--------|----------|
| Getting Started | ✅ Complete | 100% |
| Core Concepts | ✅ Complete | 100% |
| Examples | 🔄 Growing | 80% |
| Advanced Features | 🔄 In Progress | 60% |
| Blog | 🔄 Growing | Ongoing |

## 🤝 Contributing

See [DOCUMENTATION_PRINCIPLES.md](./DOCUMENTATION_PRINCIPLES.md) for detailed writing guidelines.

### Before Committing

- [ ] Test search functionality
- [ ] Verify responsive design
- [ ] Check all links work
- [ ] Run `npm run build` successfully
- [ ] Examples are copy-paste ready

## 🚀 Deployment

The site is automatically deployed via Vercel when changes are pushed to the main branch.

## 🔗 Resources

- **GitHub**: [wu-changxing/connectonion](https://github.com/wu-changxing/connectonion)
- **Discord**: [Join our community](https://discord.gg/4xfD9k8AUF)
- **PyPI**: [connectonion](https://pypi.org/project/connectonion/)
- **Website Maintenance**: [Detailed guide](./public/tutorials/website-maintenance.md)

## 📜 License

MIT - Part of the ConnectOnion project

---

> "If it takes more than 2 lines to start, we've failed at simplicity"  
> "Documentation is UX for developers"