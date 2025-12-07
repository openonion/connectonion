# Templates

Pre-built agent templates for common use cases. Create a new project with:

```bash
co create my-agent --template <template-name>
```

## Template Selection Guide

| Template | Best For | Key Tools |
|----------|----------|-----------|
| [minimal](minimal.md) | Getting started, learning | `calculator` |
| [playwright](playwright.md) | Web automation, scraping | Browser control, screenshots |
| [meta-agent](meta-agent.md) | Building agents, dev assistance | Docs search, shell, todos |
| [web-research](web-research.md) | Research, data extraction | Web search, analysis |

## Quick Comparison

### minimal
Simple starting point with one tool. Perfect for learning ConnectOnion basics.

```bash
co create my-bot --template minimal
```

### playwright
Full browser automation with 11 tools. Scrape websites, fill forms, take screenshots.

```bash
co create browser-bot --template playwright
```

### meta-agent
Development assistant that knows ConnectOnion. Query docs, run shell commands, manage todos.

```bash
co create dev-helper --template meta-agent
```

### web-research
Research and data extraction. Search web, extract content, save findings.

```bash
co create researcher --template web-research
```

## Creating Custom Templates

Start with any template and customize:

1. Create project: `co create my-agent --template minimal`
2. Add tools to `agent.py`
3. Update `prompt.md` for agent personality
4. Add dependencies to `requirements.txt`

See [Tools](../concepts/tools.md) for creating custom tools.

## What Each Template Includes

```
my-agent/
├── agent.py            # Agent with tools
├── prompt.md           # System prompt (optional)
├── .env                # API keys
├── .co/
│   ├── config.toml     # Project config
│   └── docs/           # ConnectOnion docs for AI
├── requirements.txt    # Dependencies
└── README.md           # Project documentation
```

## Next Steps

- [CLI Create Command](../cli/create.md) - Full `co create` options
- [Tools Documentation](../concepts/tools.md) - Creating custom tools
- [Prompts](../concepts/prompts.md) - Customizing agent behavior
