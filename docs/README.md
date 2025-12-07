# ConnectOnion Documentation

> **"Keep simple things simple, make complicated things possible"**

Build AI agents in 2 lines. Scale to production with trust, events, and multi-agent collaboration.

## Quick Start

```python
from connectonion import Agent

agent = Agent("assistant", tools=[search])
result = agent.input("Find Python tutorials")
```

See [Quick Start](quickstart.md) for the full tutorial.

## Core Concepts

Start here to understand ConnectOnion:

- [Agent](concepts/agent.md) - The core building block
- [Tools](concepts/tools.md) - Functions as agent capabilities
- [Events](concepts/events.md) - Lifecycle hooks
- [Plugins](concepts/plugins.md) - Reusable behaviors
- [Models](concepts/models.md) - OpenAI, Claude, Gemini, managed keys
- [Trust](concepts/trust.md) - Verification levels
- [Prompts](concepts/prompts.md) - Agent personality
- [Max Iterations](concepts/max_iterations.md) - Control execution depth
- [llm_do](concepts/llm_do.md) - One-shot LLM calls

## CLI

- [CLI Overview](cli/) - All commands
- [co create](cli/create.md) - Create new projects
- [co init](cli/init.md) - Initialize existing projects
- [co auth](cli/auth.md) - Authentication

## Templates

Pre-built agent templates for common use cases:

- [Templates Overview](templates/) - Selection guide
- [minimal](templates/minimal.md) - Basic starter
- [playwright](templates/playwright.md) - Browser automation
- [meta-agent](templates/meta-agent.md) - Development assistant
- [web-research](templates/web-research.md) - Web research

## Built-in Components

- [Built-in Tools](useful_tools/) - Shell, Gmail, Calendar, Memory
- [Built-in Plugins](useful_plugins/) - re_act, eval, shell_approval
- [TUI Components](tui/) - pick, Input, Dropdown

## Debugging

- [Debugging Overview](debug/) - All debugging tools
- [Interactive Debugging](debug/auto_debug.md) - XRay breakpoints
- [Console Output](debug/console.md) - Rich formatting

## Networking

- [Networking Overview](network/) - Multi-agent collaboration
- [Connect](network/connect.md) - Connect to remote agents
- [Serve](network/serve.md) - Make agents network-accessible

## Integrations

- [Integrations Overview](integrations/) - External service connections
- [Authentication](integrations/auth.md) - Managed keys (`co auth`)
- [Google OAuth](integrations/google.md) - Gmail, Calendar
- [Microsoft OAuth](integrations/microsoft.md) - Outlook, Calendar

## More

- [Examples](examples.md) - Copy-paste patterns
- [Logging](debug/log.md) - Activity logs
- [Roadmap](roadmap.md) - What's coming next

## Folder Structure

```
docs/
├── concepts/          # Core concepts (READ THESE)
├── cli/               # CLI commands
├── templates/         # Project templates
├── debug/             # Debugging & logging
├── network/           # Multi-agent networking
├── integrations/      # OAuth & external services
├── useful_tools/      # Built-in tools
├── useful_plugins/    # Built-in plugins
├── tui/               # TUI components
└── design-decisions/  # Architecture decisions
```

## Quick Links

| I want to... | Go to |
|--------------|-------|
| Create my first agent | [Quick Start](quickstart.md) |
| Use a project template | [Templates](templates/) |
| Add tools to my agent | [Tools](concepts/tools.md) |
| Use managed API keys | [Authentication](integrations/auth.md) |
| Debug my agent | [Debugging](debug/) |
| Connect agents | [Networking](network/) |
| Add planning/reflection | [re_act Plugin](useful_plugins/re_act.md) |

## Resources

- **Discord**: [discord.gg/4xfD9k8AUF](https://discord.gg/4xfD9k8AUF)
- **Docs Site**: [docs.connectonion.com](https://docs.connectonion.com)
- **PyPI**: [pypi.org/project/connectonion](https://pypi.org/project/connectonion)
- **GitHub**: [github.com/openonion/connectonion](https://github.com/openonion/connectonion)
