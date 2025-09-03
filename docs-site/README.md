# ConnectOnion Documentation Site

Official documentation for ConnectOnion - Production-ready AI agents with Python functions. No classes, no complexity.

> **Philosophy**: Keep simple things simple, make complicated things possible.

🎉 **Production Ready** - Battle-tested in real applications with comprehensive documentation and examples.

## 🚀 Quick Start

### Use ConnectOnion (Production Ready)
```bash
# Install from PyPI
pip install connectonion

# Create your first agent in seconds
python -c "from connectonion import Agent; agent = Agent('assistant'); print(agent.input('Hello!'))"
```

### Run Documentation Site
```bash
# Clone and run locally
git clone https://github.com/wu-changxing/connectonion.git
cd connectonion/docs-site
npm install
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) to view the documentation.

## 📚 Documentation Structure

Our documentation follows a logical learning path:

### 🎯 Getting Started
- **[Introduction](/)** - Overview and philosophy
- **[Quick Start](/quickstart)** - Get running in 60 seconds
- **[CLI Reference](/cli)** - Command-line tools (`co` command)

### 🧠 Core Concepts
- **[System Prompts](/prompts)** - Define agent behavior (START HERE)
- **[Tools](/tools)** - Functions as agent capabilities
- **[max_iterations](/max-iterations)** - Control and safety
- **[llm_do](/llm_do)** - Direct LLM function calls (OpenAI, Gemini, Anthropic)
- **[Trust Parameter](/trust)** - Multi-agent communication
- **[@xray Decorator](/xray)** - Debugging and visualization

### 💡 Examples
- **[Overview](/examples)** - All working examples
- **[Hello World](/examples/hello-world)** - Simplest starting point
- **[Calculator](/examples/calculator)** - Math operations
- **[Weather Bot](/examples/weather-bot)** - API integration
- **[File Analyzer](/examples/file-analyzer)** - File operations
- **[Task Manager](/examples/task-manager)** - Stateful agents
- **[API Client](/examples/api-client)** - External APIs
- **[E-commerce Manager](/examples/ecommerce-manager)** - Complex workflows
- **[Math Tutor Agent](/examples/math-tutor-agent)** - Educational assistant

### 📖 Advanced Topics
- **[Blog](/blog)** - Design decisions and deep dives
- **[Threat Model](/threat-model)** - Security considerations
- **[Roadmap](/roadmap)** - Future development plans
- **[Website Maintenance](/website-maintenance)** - Contributing guide

## 🏗️ Site Architecture

### Tech Stack
- **Framework**: Next.js 14 with App Router
- **Styling**: Tailwind CSS
- **Search**: Client-side full-text search
- **Code Highlighting**: Prism.js
- **Icons**: Lucide React
- **Deployment**: Vercel

### Directory Structure

```
docs-site/
├── app/                    # Next.js pages
│   ├── quickstart/        # Getting started guide
│   ├── prompts/           # System prompts documentation
│   │   └── examples/      # Prompt example pages
│   ├── tools/             # Tools documentation
│   ├── max-iterations/    # Iteration control
│   ├── llm_do/           # LLM function docs
│   ├── trust/            # Trust parameter
│   ├── xray/             # Debugging features
│   ├── examples/         # Working code examples
│   ├── blog/             # Design decisions
│   └── website-maintenance/ # Contribution guide
├── components/            # Reusable components
│   ├── DocsSidebar.tsx   # Navigation sidebar
│   ├── ContentNavigation.tsx # Prev/Next navigation
│   ├── CommandBlock.tsx  # Terminal command display
│   ├── CodeWithResult.tsx # Code + output blocks
│   ├── CopyMarkdownButton.tsx # Copy page as markdown
│   └── Footer.tsx        # Site footer
├── lib/
│   └── navigation.ts     # Centralized navigation config
├── public/
│   └── tutorials/        # Markdown content files
├── utils/                
│   ├── searchIndex.ts    # Search functionality
│   ├── markdownLoader.ts # Markdown processing
│   └── copyAllDocs.ts    # Export documentation
└── styles/
    └── globals.css       # Global styles

## 📝 Content Guidelines

### The 2-5-10 Rule
Every feature should be learnable in progressive steps:

**2 Lines - It Works!**
```python
agent = Agent("helper", tools=[greet])
agent.input("Hello")  # Immediate result
```

**5 Lines - It's Useful!**
```python
agent = Agent("helper", 
              tools=[greet, calculate],
              system_prompt="Be helpful")
result = agent.input("Greet and calculate")
print(result)
```

**10 Lines - Production-Ready!**
```python
from connectonion import Agent, xray

agent = Agent("production_assistant",
              tools=[greet, calculate, search],
              system_prompt=load_prompt("assistant.md"),
              max_iterations=5,
              trust="prompt")
              
@xray
def process(user_input):
    return agent.input(user_input)
    
# Ready for production deployment
result = process("Complex task")
```

### Writing Best Practices
✅ **DO:**
- Start with working code immediately
- Show real output for every example
- Progress from simple to complex
- Include "When to use this" sections
- Provide copy-paste ready code

❌ **DON'T:**
- Start with theory or abstractions
- Use complex inheritance patterns
- Assume prior knowledge
- Hide important details
- Write walls of text

## 🔧 Development Workflow

### Local Development
```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Run production build locally
npm run start
```

### Adding New Documentation

1. **Create content** in `/public/tutorials/your-feature.md`
2. **Add page** in `/app/your-feature/page.tsx`
3. **Update navigation** in `/lib/navigation.ts`
4. **Test locally** with `npm run dev`
5. **Build test** with `npm run build`

### Navigation System

The site uses a centralized navigation structure in `/lib/navigation.ts`:
- Single source of truth for all pages
- Automatic prev/next navigation
- Section grouping for sidebar
- Keyword support for search

## 🎯 Key Features

### For Users
- **Quick Start**: Get running in < 60 seconds
- **Progressive Examples**: Learn step by step
- **Copy as Markdown**: Export any page for AI assistants
- **Full-Text Search**: Find anything instantly
- **Mobile Responsive**: Works on all devices

### For Contributors
- **Centralized Navigation**: Single config file
- **Reusable Components**: Consistent UI patterns
- **Markdown Support**: Write content easily
- **Hot Reload**: See changes instantly
- **Type Safety**: TypeScript throughout

## 📊 Production Status

### ✅ Production Ready
- **Core Framework**: Stable and battle-tested
- **Documentation**: Comprehensive with 30+ pages
- **Examples**: 16+ working examples covering all use cases
- **Multi-Provider Support**: OpenAI, Google Gemini, Anthropic
- **Testing**: Extensive unit and integration tests
- **Community**: Active Discord and GitHub community

| Component | Status | Maturity |
|-----------|--------|----------|
| Core Agent System | ✅ Stable | Production |
| Tool System | ✅ Stable | Production |
| LLM Integration | ✅ Stable | Production |
| Documentation | ✅ Complete | Production |
| Examples | ✅ Complete | Production |
| CLI Tools | ✅ Stable | Production |

## 🚀 Deployment

### Production Website
The documentation site is live and production-ready:
- **Live Site**: [connectonion.com](https://connectonion.com)
- **Auto-Deploy**: Push to main branch triggers deployment
- **Preview URLs**: Every PR gets a preview deployment
- **Zero-Config**: Vercel handles everything automatically

### Package Distribution
ConnectOnion is available for production use:
- **PyPI**: `pip install connectonion`
- **Version**: Stable releases with semantic versioning
- **Support**: Python 3.8+ with async support

## 🔗 Links

- **GitHub**: [wu-changxing/connectonion](https://github.com/wu-changxing/connectonion)
- **Discord**: [Community](https://discord.gg/4xfD9k8AUF)
- **PyPI**: [connectonion](https://pypi.org/project/connectonion/)
- **npm**: [@connectonion/cli](https://www.npmjs.com/package/@connectonion/cli)

## 📜 License

MIT License - See [LICENSE](../LICENSE) for details

---

> "Keep simple things simple, make complicated things possible"