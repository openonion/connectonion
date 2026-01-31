# ConnectOnion Create Command

The `co create` command creates new ConnectOnion projects with intelligent defaults and automatic setup.

## Overview

```bash
co create [name] [options]
```

Creates a new agent project with:
- AI features enabled by default (agents need LLMs)
- API keys copied from global config (if available)
- Global address and email used for all projects
- Complete agent implementation ready to run

## Command Flow

### First-Time User

When `~/.co/` doesn't exist, `co create` automatically sets up global configuration:

```bash
$ co create my-first-agent

🚀 Welcome to ConnectOnion!
✨ Setting up global configuration...
  ✓ Creating ~/.co/ directory
  ✓ Generating master keypair
  ✓ Your address: 0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a
  ✓ Your email: 0x7a9f3b2c@mail.openonion.ai
  ✓ Creating ~/.co/config.toml
  ✓ Creating ~/.co/keys.env (ready for your API keys)

🧅 ConnectOnion Project Creator
========================================

✔ Choose a template:
  ❯ Minimal - Simple starting point
    Web Research - Data scraping & analysis
    Playwright - Browser automation
    Custom - AI generates based on needs

✔ Paste your API key (or Enter to skip): › sk-proj-xxx
  ✓ Detected OpenAI API key
  ✓ Saved to ~/.co/keys.env for future projects

✔ Project name: › my-first-agent

✅ Project created successfully!

📁 Created: my-first-agent
📦 Template: Minimal
✨ AI Features: Enabled
📧 Agent email: 0x7a9f3b2c@mail.openonion.ai (global)
🔑 Agent address: 0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a (global)

🚀 Next steps:
────────────────────────────────────────
1️⃣  cd my-first-agent
2️⃣  pip install python-dotenv
3️⃣  python agent.py
```

### Returning User

When `~/.co/` already exists:

```bash
$ co create another-agent

🧅 ConnectOnion Project Creator
========================================
✓ Using global identity: 0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a
✓ Using global email: 0x7a9f3b2c@mail.openonion.ai

✔ Choose a template: › Web Research

✓ Found API keys in ~/.co/keys.env
  ✓ OpenAI key will be copied to project

✔ Project name: › research-bot

✅ Project created successfully!

📁 Created: research-bot
📦 Template: Web Research
✨ AI Features: Enabled
📧 Agent email: 0x7a9f3b2c@mail.openonion.ai (global)
🔑 Agent address: 0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a (global)
🔑 API keys: Copied from global config

💡 Using global email/address. Run 'co status' to view.

🚀 Next steps:
────────────────────────────────────────
1️⃣  cd research-bot
2️⃣  pip install -r requirements.txt
3️⃣  python agent.py
```

## What Gets Created

### Global Configuration (First Time Only)

```
~/.co/
├── config.toml          # Global configuration with address & email
├── keys.env             # Shared API keys
├── keys/                # Master identity
│   ├── agent.key        # Private key (for signing)
│   └── recovery.txt     # Recovery phrase
└── logs/
    └── cli.log          # Command history
```

### Project Structure

```
my-agent/
├── agent.py             # Main agent implementation
├── .env                 # API keys (from ~/.co/keys.env)
├── .co/
│   ├── config.toml     # Project config (uses global address/email)
│   └── docs/           # Framework documentation
│       ├── co-vibe-coding-all-in-one.md
│       └── connectonion.md
├── README.md           # Project documentation
└── .gitignore          # Excludes .env and sensitive files
```

Note: Projects use global address/email by default.

## Configuration Files

### Global Config (`~/.co/config.toml`)

```toml
[connectonion]
framework_version = "0.0.7"
created = "2025-01-15T10:30:00.000000"

[cli]
version = "1.0.0"

[agent]
# Global address and email used by all projects
address = "0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a"
short_address = "0x7a9f...7f8a"
email = "0x7a9f3b2c@mail.openonion.ai"
email_active = true
created_at = "2025-01-15T10:30:00.000000"
algorithm = "ed25519"
default_model = "co/gemini-2.5-pro"
max_iterations = 10

[auth]
token = "eyJhbGciOiJI..."  # If authenticated with network
```

### Project Config (`.co/config.toml`)

```toml
[project]
name = "my-agent"
template = "minimal"
created = "2025-01-15T11:00:00.000000"

[connectonion]
framework_version = "0.0.7"

[cli]
version = "1.0.0"
command = "co create my-agent"

[agent]
# Copies global address and email
address = "0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a"
short_address = "0x7a9f...7f8a"
email = "0x7a9f3b2c@mail.openonion.ai"
email_active = true
algorithm = "ed25519"
default_model = "co/gemini-2.5-pro"
max_iterations = 10
```

### API Keys (`.env`)

Automatically copied from `~/.co/keys.env`:

```bash
# my-agent/.env
OPENAI_API_KEY=sk-proj-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
# Any other keys from global config
```

## Address and Email Management

All projects use the global identity (address + email) from `~/.co`. Run `co status` to view your address and email.

## Templates

### Available Templates

1. **minimal** - Basic agent with simple tools
2. **web-research** - Web scraping and research capabilities
3. **playwright** - Browser automation
4. **custom** - AI-generated based on your description

### Template Selection

```bash
# Interactive selection
$ co create
✔ Choose a template: ›

# Direct specification
$ co create my-bot --template minimal

# Custom with description
$ co create assistant --template custom --description "Slack integration bot"
```

## Command Options

```bash
co create [name] [options]

Options:
  [name]                    Project name (optional, will prompt)
  --template, -t            Template to use (minimal/web-research/playwright/custom)
  --description, -d         Description for custom template
  --no-ai                   Disable AI features (not recommended)
  --key                     API key to use (overrides global)
  --yes, -y                 Accept all defaults
```

## API Key Management

### Priority Order

1. **Command line** (`--key` flag)
2. **Global config** (`~/.co/keys.env`)
3. **Interactive prompt** (if not found)
4. **Skip** (user adds to .env later)

### Auto-Detection

The CLI automatically detects API key providers:
- `sk-proj-...` → OpenAI
- `sk-ant-...` → Anthropic
- `AIza...` → Google
- `gsk_...` → Groq

## Special Features

### AI Enabled by Default

AI features are always enabled because agents need LLMs. To disable (not recommended):
1. Edit `.co/config.toml` after creation
2. Use `--no-ai` flag (limits functionality)

### Global Identity Reuse

By default, all projects share:
- Same address (from global config)
- Same email (from global config)
- Same API keys (from global config)

This keeps things simple - one identity for all your agents.

## Examples

### Quick Start

```bash
# Simplest form - uses global identity
$ co create

# With name - uses global identity
$ co create my-bot

# With template - uses global identity
$ co create my-bot --template web-research

# Accept all defaults
$ co create quickbot -y
```

### Custom Template

```bash
# Interactive
$ co create --template custom

# With description
$ co create slack-bot -t custom -d "Slack bot for answering questions"
```

## Identity Flow Summary

1. **First `co create`**: Generates global address/email
2. **All projects**: Use same global address/email
3. **API keys**: Copied from global `keys.env`

This keeps things simple - one identity for all your agents (like using same email for all repos).

## Troubleshooting

### Check Your Address

```bash
$ co status
```

### Permission Errors

```bash
# Fix global permissions
$ chmod 700 ~/.co
$ chmod 600 ~/.co/keys.env

# Fix project permissions
$ chmod 700 my-agent/.co
```

## Workflow Summary

1. **First time**: Creates global address/email
2. **Every project**: Uses same global address/email
3. **API keys**: Copied from global to each project
4. **Ready to run**: Complete agent with identity

Simple and consistent - one identity for all your agents.
