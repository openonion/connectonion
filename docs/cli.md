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

## Commands Overview

ConnectOnion provides two main commands for project creation:

- **`co create [name]`** - Creates a new project directory
- **`co init`** - Initializes the current directory

Both commands share the same interactive flow:
1. AI feature toggle (Yes/No)
2. API key input (with auto-detection)
3. Template selection

## Commands

### `co create [name]`

Create a new ConnectOnion project in a new directory.

#### Basic Usage

```bash
# Interactive mode (prompts for project name)
co create

# With project name (skips name prompt)
co create my-agent

# With all options (no interaction)
co create my-agent --ai --key sk-proj-xxx --template minimal
```

#### Options

- `[name]`: Optional project name (creates directory)
- `--ai/--no-ai`: Enable or disable AI features
- `--key`: API key for AI provider (auto-detects provider)
- `--template`: Choose template (`minimal`, `web-research`, `custom`)
- `--description`: Description for custom template (requires AI)
- `--yes, -y`: Skip all prompts, use defaults

#### Interactive Flow

```bash
$ co create

✔ Project name: … my-agent
✔ Enable AI features? (Y/n) … Y
✔ Paste your API key (or Enter to skip): … sk-proj-abc123
  ✓ Detected OpenAI API key
✔ Choose a template:
  ❯ Minimal - Simple starting point
    Web Research - Data analysis & web scraping
    Custom - AI generates based on your needs

✅ Created 'my-agent' with Minimal template

Next steps:
  cd my-agent
  python agent.py
```

### `co init`

Initialize a ConnectOnion project in the current directory.

#### Basic Usage

```bash
# Initialize current directory interactively
co init

# Skip prompts with options
co init --no-ai --template minimal
```

#### Options

Same as `co create`, except no `[name]` parameter (uses current directory name).

#### Interactive Flow

```bash
$ mkdir my-project
$ cd my-project
$ co init

✔ Enable AI features? (Y/n) … Y
✔ Paste your API key (or Enter to skip): … sk-ant-xxx
  ✓ Detected Anthropic API key
✔ Choose a template:
  ❯ Minimal - Simple starting point
    Web Research - Data analysis & web scraping
    Custom - AI generates based on your needs

✅ Initialized current directory with Minimal template
```

## Templates

### Minimal
Basic agent structure with essential components:
- Simple agent.py with basic tools
- Minimal dependencies
- Quick start configuration

### Web Research
Advanced template for data analysis and web scraping:
- Web scraping tools
- Data extraction utilities
- Browser automation support
- API integration examples

### Custom (AI-only)
Only available when AI is enabled. Generates a complete custom template based on your description:

```bash
✔ Choose template: Custom
✔ Describe what you want to build: … 
  I need an agent that monitors GitHub repos and 
  sends notifications for new issues

⚡ Generating custom template with AI...
✅ Created custom GitHub monitoring agent
```

## API Key Detection

The CLI automatically detects your API provider from the key format:

| Provider | Key Format | Example |
|----------|------------|---------|
| OpenAI | `sk-...` or `sk-proj-...` | `sk-proj-abc123...` |
| Anthropic | `sk-ant-...` | `sk-ant-api03-xyz...` |
| Google | `AIza...` | `AIzaSyAbc123...` |
| Groq | `gsk_...` | `gsk_abc123...` |

The appropriate environment variables and model configurations are set automatically.

## What Gets Created

### Project Structure

```
my-agent/
├── agent.py           # Main agent implementation
├── tools/             # Custom tools directory (if applicable)
├── prompts/           # System prompts (for AI-enabled projects)
├── .env               # Environment configuration (API keys)
├── .co/               # ConnectOnion metadata
│   ├── config.toml    # Project configuration
│   ├── keys/          # Agent cryptographic keys
│   │   ├── agent.key  # Private signing key
│   │   ├── recovery.txt # 12-word recovery phrase
│   │   └── DO_NOT_SHARE # Security warning
│   └── docs/
│       └── co-vibe-coding-all-in-one.md # Complete framework docs
├── README.md          # Project documentation
└── .gitignore        # Git ignore rules (if in git repo)
```

### Agent Identity

Every project automatically gets:
- **Ed25519 cryptographic keys** for agent identity
- **Unique address** (hex-encoded public key)
- **12-word recovery phrase** for key restoration
- Keys are stored in `.co/keys/` and auto-added to `.gitignore`

## Examples

### Quick Start Examples

```bash
# Minimal project without AI
co create simple-bot --no-ai --template minimal

# Web research project with AI
co create research-agent --ai --template web-research

# Custom AI agent with description
co create slack-bot --ai --template custom \
  --description "Slack bot that answers questions"

# Initialize existing directory
cd my-existing-project
co init --ai --template minimal
```

### AI-Enabled Custom Template

```bash
$ co create assistant

✔ Enable AI features? Y
✔ Paste your API key: sk-proj-xxx
✔ Choose template: Custom
✔ Describe what you want to build: 
  An assistant that helps with code reviews and 
  suggests improvements

⚡ Generating custom code review assistant...

Your custom agent includes:
  • Code analysis tools
  • Git integration
  • Review comment generator
  • Improvement suggestions

✅ Created 'assistant' with custom template
```

### Non-AI Simple Project

```bash
$ co create automation --no-ai

✔ Choose template: Minimal

✅ Created 'automation' with Minimal template

Next steps:
  cd automation
  python agent.py
```

## Using with AI Coding Assistants

The `.co/docs/co-vibe-coding-all-in-one.md` file contains complete ConnectOnion documentation. Use it with AI coding assistants like Cursor, Claude Code, or GitHub Copilot:

```
Please read .co/docs/co-vibe-coding-all-in-one.md to understand 
ConnectOnion framework, then help me create [your task]
```

## Best Practices

1. **Choose the right command**:
   - Use `co create` when starting a new project
   - Use `co init` when adding to an existing directory

2. **API Key Security**:
   - Never commit `.env` files
   - Store API keys securely
   - Use environment variables in production

3. **Template Selection**:
   - Start with Minimal for learning
   - Use Web Research for data projects
   - Choose Custom (with AI) for specific needs

4. **Agent Keys**:
   - Never share `.co/keys/` directory
   - Backup your recovery phrase
   - Keys are automatically generated and protected

## Troubleshooting

### Command Not Found

If `co` command is not found after installation:
```bash
# Use full command
python -m connectonion.cli.main create

# Or reinstall
pip uninstall connectonion
pip install connectonion
```

### Permission Denied

Ensure you have write permissions in the target directory.

### API Key Issues

- Check key format matches your provider
- Ensure key is active and has credits
- Try pasting without quotes or spaces

### Python Version

ConnectOnion requires Python 3.8+:
```bash
python --version
```

## Next Steps

After creating your project:

1. **Add your API key**: Edit `.env` file with your actual key
2. **Install dependencies**: `pip install python-dotenv`
3. **Run your agent**: `python agent.py`
4. **Customize**: Modify agent.py and add custom tools

For more information:
- [Getting Started Guide](getting-started.md)
- [Templates Documentation](templates.md)  
- [Tools Documentation](tools.md)
- [Agent Identity & Keys](co-directory-structure.md)