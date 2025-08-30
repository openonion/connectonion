# ConnectOnion CLI Reference

The ConnectOnion CLI provides commands to quickly scaffold and manage AI agent projects.

## Installation

The CLI is automatically installed when you install ConnectOnion:

```bash
pip install connectonion
```

This provides two equivalent commands:
- `co` (short form)
- `connectonion` (full form)

## Commands

### `co init`

Initialize a new ConnectOnion agent project in the current directory.

#### Basic Usage

```bash
# Create a meta-agent (default)
mkdir meta-agent
cd meta-agent
co init

# Create a web automation agent
mkdir playwright-agent
cd playwright-agent
co init --template playwright
```

#### Options

- `--template, -t`: Choose a template (`meta-agent`, `playwright`)
  - `meta-agent` (default): ConnectOnion development assistant with docs expertise
  - `playwright`: Web automation agent with stateful browser control
- `--force`: Overwrite existing files

#### What Gets Created

**Meta-Agent Template (default):**
```
my-project/
├── agent.py           # Main agent with llm_do integration
├── prompts/           # System prompts directory
│   ├── metagent.md    # Main system prompt
│   ├── docs_retrieve_prompt.md  # Document retrieval
│   ├── answer_prompt.md         # Answer generation
│   └── think_prompt.md          # Reflection/thinking
├── README.md          # Project documentation
├── .env.example       # Environment variables template
├── .co/               # ConnectOnion metadata
│   ├── config.toml    # Project configuration
│   └── docs/
│       └── connectonion.md  # Embedded framework documentation
└── .gitignore         # Git ignore rules (if in git repo)
```

**Playwright Template:**
```
my-project/
├── agent.py           # Browser automation agent
├── prompt.md          # System prompt
├── .env.example       # Environment variables template
├── .co/               # ConnectOnion metadata
│   ├── config.toml    # Project configuration
│   └── docs/
│       └── connectonion.md  # Embedded framework documentation
└── .gitignore         # Git ignore rules (if in git repo)
```

#### Interactive Features

The CLI will:
- Warn if you're in a special directory (home, root, system)
- Ask for confirmation if the directory is not empty
- Automatically detect git repositories and update `.gitignore`
- Provide clear next steps after initialization

### Examples

#### Meta-Agent (ConnectOnion Development Assistant)

```bash
$ mkdir meta-agent && cd meta-agent
$ co init
✅ ConnectOnion project initialized!

Created:
   ├── agent.py (Meta-agent with llm_do integration)
   ├── prompts/ (System prompts directory)
   ├── README.md (Project documentation)
   ├── .env.example (API key configuration template)
   ├── .co/ (ConnectOnion metadata)
   ├── .co/docs/connectonion.md (ConnectOnion reference documentation)

🚀 Next steps:
   1. Copy .env.example to .env and add your API keys
   2. Edit prompt.md to customize your agent's personality
   3. Run: python agent.py
   4. Start building your agent!
```

The meta-agent template includes powerful development and self-reflective tools:
- `answer_connectonion_question()` - Expert answers from embedded docs
- `create_agent_from_template()` - Generate complete agent code
- `generate_tool_code()` - Create tool functions
- `create_test_for_agent()` - Generate pytest test suites
- `think()` - Self-reflection to analyze task completion
- `generate_todo_list()` - Create structured plans (uses GPT-4o-mini)
- `suggest_project_structure()` - Architecture recommendations

```python
# Learn about ConnectOnion
result = agent.input("What is ConnectOnion and how do tools work?")

# Generate agent code
result = agent.input("Create a web scraper agent")

# Create tool functions
result = agent.input("Generate a tool for sending emails")

# Task planning
result = agent.input("Create a to-do list for building a REST API")

# Self-reflection
result = agent.input("Think about whether you completed the task successfully")
```

#### Playwright Web Automation Agent

```bash
$ co init --template playwright
✅ ConnectOnion project initialized!
💡 You're using the 'playwright' template with specialized tools.
```

The Playwright template includes stateful browser tools:
- `start_browser()` - Launch browser instance
- `navigate()` - Go to URLs
- `scrape_content()` - Extract page content
- `fill_form()` - Fill and submit forms
- `take_screenshot()` - Capture pages
- `extract_links()` - Get all links
- `execute_javascript()` - Run JS code
- `close_browser()` - Clean up resources

Note: Requires `pip install playwright && playwright install`

## Project Structure

### `.co/` Directory

The `.co/` directory contains:
- `config.toml`: Project metadata (version, creation date, template used)
- `docs/connectonion.md`: Embedded documentation for offline reference
- `history/`: Agent behavior history (created at runtime)

### Best Practices

1. **Always use markdown for prompts**: Store system prompts in `prompt.md` files
2. **Environment variables**: Never commit `.env` files, use `.env.example` as template
3. **Git integration**: The CLI automatically handles `.gitignore` for git repositories
4. **Documentation**: The embedded docs in `.co/docs/` allow agents to work offline

## Troubleshooting

### Permission Denied

If you see "Permission denied" errors, ensure you have write permissions in the current directory.

### API Keys

Remember to:
1. Copy `.env.example` to `.env`
2. Add your actual API keys
3. Never commit `.env` to version control

### Python Version

ConnectOnion requires Python 3.8 or higher. Check your version:

```bash
python --version
```

## Next Steps

After initializing your project:

1. **Set up API keys**: Copy `.env.example` to `.env` and add your OpenAI API key
2. **Customize the prompt**: Edit `prompt.md` to define your agent's personality
3. **Add tools**: Create Python functions and add them to your agent
4. **Test your agent**: Run `python agent.py` to test

For more information, see:
- [Getting Started Guide](getting-started.md)
- [Templates Documentation](templates.md)
- [Tools Documentation](tools.md)