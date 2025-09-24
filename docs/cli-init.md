# ConnectOnion Init Command

The `co init` command initializes ConnectOnion in an existing directory, perfect for adding agent capabilities to existing projects.

## Overview

```bash
co init [options]
```

Initializes ConnectOnion in the current directory with:
- AI features enabled by default
- Global address/email from `~/.co/`
- API keys appended to existing `.env` (or created if missing)
- Template files added to your project
- Docs always updated to latest version

## Command Comparison

| Feature | `co create` | `co init` |
|---------|------------|-----------|
| Creates new directory | ✅ Yes | ❌ No (uses current) |
| Can work in non-empty dir | ❌ No | ✅ Yes |
| Uses global identity | ✅ Yes | ✅ Yes |
| Copies global API keys | ✅ Yes | ✅ Yes (appends) |
| Supports templates | ✅ Yes | ✅ Yes |

## Usage Scenarios

### Scenario 1: Adding to Existing Project with .env

You have a project with existing `.env` file:

```bash
$ cd my-existing-project
$ cat .env
DATABASE_URL=postgres://localhost/mydb
SECRET_KEY=mysecret

$ co init

🧅 ConnectOnion Project Initializer
========================================

✓ Using global identity
✓ Found existing .env file
✓ Appending API keys from ~/.co/keys.env

$ cat .env
DATABASE_URL=postgres://localhost/mydb
SECRET_KEY=mysecret

# ConnectOnion API Keys
OPENAI_API_KEY=sk-proj-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
```

Your existing environment variables are preserved, API keys are appended!

### Scenario 2: Quick Init in Empty Directory

```bash
$ mkdir my-new-agent
$ cd my-new-agent
$ co init --yes

✓ Using global identity
✓ Created new .env with API keys from ~/.co/keys.env

✅ ConnectOnion project initialized!
```

### Scenario 3: Updating Documentation

Running `co init` again updates docs to latest version:

```bash
$ co init

✓ Project already initialized
✓ Updating .co/docs/ to latest version
✓ .env already has API keys

✅ Documentation updated!
```

## What Gets Added/Updated

When you run `co init`:

```
your-project/
├── agent.py             # Added if missing (skipped if exists)
├── .env                 # APPENDED with API keys (created if missing)
├── .co/
│   ├── config.toml     # Project config (uses global identity)
│   └── docs/           # ALWAYS UPDATED to latest version
│       ├── co-vibe-coding-all-in-one.md  # Overwritten
│       └── connectonion.md                # Overwritten
└── [your existing files remain untouched]
```

## File Handling Strategy

| File/Directory | If Exists | Behavior |
|----------------|-----------|----------|
| `agent.py` | Skip | Won't overwrite user code |
| `.env` | **Append** | Adds API keys if missing |
| `.co/docs/` | **Overwrite** | Always latest documentation |
| `.co/config.toml` | Update | Preserves custom settings |
| `.gitignore` | Append | Adds ConnectOnion entries |

## .env Handling Details

### Case 1: No .env File
Creates new `.env` with API keys from `~/.co/keys.env`:
```bash
# Created .env
OPENAI_API_KEY=sk-proj-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
```

### Case 2: .env Exists, No API Keys
Appends API keys to existing file:
```bash
# Original .env
DATABASE_URL=postgres://localhost
REDIS_URL=redis://localhost

# After co init
DATABASE_URL=postgres://localhost
REDIS_URL=redis://localhost

# ConnectOnion API Keys
OPENAI_API_KEY=sk-proj-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
```

### Case 3: .env Has Some API Keys
Only appends missing keys:
```bash
# Original .env
OPENAI_API_KEY=sk-proj-old

# After co init (adds missing keys)
OPENAI_API_KEY=sk-proj-old

# ConnectOnion API Keys
ANTHROPIC_API_KEY=sk-ant-xxx  # Added
GOOGLE_API_KEY=AIza...         # Added
```

### Case 4: .env Has All Keys
No changes made:
```bash
✓ .env already contains all API keys
```

## Global Configuration

Like `co create`, `co init` uses the global configuration:

### First Time Setup
If `~/.co/` doesn't exist, it's created automatically:

```bash
$ co init  # First time ever

🚀 Welcome to ConnectOnion!
✨ Setting up global configuration...
  ✓ Generated master keypair
  ✓ Your address: 0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a
  ✓ Your email: 0x7a9f3b2c@mail.openonion.ai
  ✓ Created ~/.co/config.toml
  ✓ Created ~/.co/keys.env

[continues with project initialization...]
```

### Using Existing Global Config

```bash
$ co init  # After global config exists

✓ Using global identity
✓ Using global email: 0x7a9f3b2c@mail.openonion.ai
✓ Found OpenAI key in ~/.co/keys.env
✓ Appending to existing .env

[continues with project initialization...]
```

## Command Options

```bash
co init [options]

Options:
  --template, -t          Template to use (minimal/web-research/playwright/custom)
  --no-ai                 Disable AI features (not recommended)
  --key                   API key to use (saves to global config)
  --force                 Initialize even in special directories
  --yes, -y              Accept all defaults, skip prompts
  --update-docs          Only update documentation
```

## Templates

Same templates as `co create`:

1. **minimal** - Basic agent with simple tools
2. **web-research** - Web scraping and research
3. **playwright** - Browser automation
4. **custom** - AI-generated based on description

## Special Directory Warnings

`co init` warns when initializing in special directories:

- Home directory (`~`)
- Root directory (`/`)
- System directories (`/usr`, `/etc`)
- Git repositories (warns but allows)

Use `--force` to bypass warnings if you know what you're doing.

## Examples

### Basic Init
```bash
# In current directory
$ co init

# Accept all defaults
$ co init -y

# With specific template
$ co init --template web-research
```

### Adding to Django Project
```bash
$ cd my-django-app
$ co init
# Your existing .env is preserved
# DATABASE_URL, SECRET_KEY remain
# API keys are appended
```

### Updating Documentation Only
```bash
$ co init --update-docs
✓ Updated .co/docs/ to latest version
```

### Custom Template
```bash
$ co init --template custom --description "Discord bot integration"
```

## Smart .env Merging

The `.env` append logic is intelligent:

```python
# Pseudo-code of .env handling
existing_env = read(".env")
global_keys = read("~/.co/keys.env")

for key, value in global_keys:
    if key not in existing_env:
        append_to_env(f"\n# ConnectOnion API Keys\n{key}={value}")
```

This ensures:
- No duplicate keys
- Existing values preserved
- Clear section for ConnectOnion keys
- Original file structure maintained

## Documentation Updates

The `.co/docs/` folder is **always overwritten** to ensure:
- Latest documentation version
- New features documented
- Bug fixes in docs
- Consistent formatting

This is safe because users shouldn't edit framework docs directly.

## Common Workflows

### 1. Existing Django/Flask Project
```bash
cd my-web-app
co init
# .env preserved with database URLs
# API keys appended
# Latest docs installed
```

### 2. Updating Existing ConnectOnion Project
```bash
cd old-agent-project
co init
# Docs updated to latest
# Missing API keys added
# Config preserved
```

### 3. Converting Script to Agent
```bash
cd my-scripts
co init
# Creates .env with API keys
# Adds agent.py template
# Your scripts untouched
```

## Troubleshooting

### .env Already Has Different API Key
The existing key is preserved:
```bash
# Original .env
OPENAI_API_KEY=sk-old-key

# After co init - NOT changed
OPENAI_API_KEY=sk-old-key
```

### Docs Seem Old
Re-run init to update:
```bash
$ co init --update-docs
✓ Documentation updated to latest version
```

### Want Fresh .env
Manually remove and re-init:
```bash
$ rm .env
$ co init
✓ Created new .env with latest API keys
```

## Best Practices

1. **Review .env after init** - Check that API keys were appended correctly

2. **Keep docs updated** - Run `co init --update-docs` periodically

3. **Don't edit framework docs** - They'll be overwritten on update

4. **Commit .co/config.toml** - Track project configuration

5. **Never commit .env** - Keep API keys secret

## File Safety Summary

| Action | Safe? | Why |
|--------|-------|-----|
| Append to .env | ✅ Yes | Only adds missing keys |
| Overwrite docs | ✅ Yes | Framework docs, not user content |
| Skip agent.py | ✅ Yes | Preserves user code |
| Update config | ✅ Yes | Merges, doesn't replace |

## Summary

`co init` intelligently integrates ConnectOnion into existing projects:

- **Preserves** - Your existing `.env` values
- **Appends** - Only missing API keys
- **Updates** - Documentation to latest
- **Respects** - Your existing code
- **Uses** - Global identity and keys

Perfect for adding AI agents to any Python project without disrupting existing configuration!
# ConnectOnion Init (co init)

Add ConnectOnion to an existing folder safely.

## Quick Start

```bash
cd existing-project
co init
```

## What It Does

- Uses your global identity from `~/.co` (address + email)
- Appends missing API keys to `.env` (creates it if missing)
- Adds `.co/config.toml` and refreshes `.co/docs/`
- Never overwrites your code (skips existing files)

## Safe In Existing Folders

- Warns in special/system directories (e.g., `~`, `/`)
- Shows what will be created or updated
- `--force` lets you continue when you know what you’re doing

## Templates

- minimal: basic agent
- playwright: browser automation
- custom: describe it, we generate it with AI

```bash
co init -t minimal
co init -t playwright
co init -t custom --description "Monitor a site and alert me"
```

## Options (the useful bits)

- `--template, -t`: `minimal` | `playwright` | `custom`
- `--key`: paste an API key (auto-detects provider and appends to `.env`)
- `--force`: continue in non-empty/special directories
- `--yes, -y`: accept defaults and skip prompts

Notes:
- Keeps `.env` intact; only appends missing keys
- Provider mapping: OpenAI → `OPENAI_API_KEY`, Anthropic → `ANTHROPIC_API_KEY`, Google → `GOOGLE_API_KEY`, Groq → `GROQ_API_KEY`
- Attempts managed-key authentication on success (or run `co auth` later)

## Next Steps

```bash
python agent.py
```
