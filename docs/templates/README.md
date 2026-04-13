# Templates

Pre-built agent templates for common use cases. Create a new project with:

```bash
co create my-agent --template <template-name>
```

## Template Selection Guide

| Template | Best For | Key Tools |
|----------|----------|-----------|
| [minimal](minimal.md) | General-purpose default | `bash`, `read_file`, `edit`, `glob`, `grep`, `write`, `BrowserAutomation` |
| [coder](coder.md) | Coding tasks, file editing | `bash`, `read_file`, `edit`, `glob`, `grep`, `write` |
| [browser](browser.md) | Web automation, scraping | Browser control, screenshots |
| [web-research](web-research.md) | Research, data extraction | Web search, analysis |

## Quick Comparison

### minimal
Default starting point. Includes file tools (`bash`, `read_file`, `edit`, `glob`, `grep`, `write`) and browser automation (`BrowserAutomation`) with `image_result_formatter` and `tool_approval` plugins.

```bash
co create my-bot --template minimal
```

### coder
Coding assistant with filesystem and shell access. Read, edit, search, and run code.

```bash
co create my-coder --template coder
```

### browser
Full browser automation. Scrape websites, fill forms, take screenshots.

```bash
co create browser-bot --template browser
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
