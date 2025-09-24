# Global .co Directory Structure

The global `.co` directory (`~/.co/`) stores your ConnectOnion identity and shared API keys. It's automatically created when you first run any `co` command.

## Simple Structure

```
~/.co/
├── config.toml          # Basic global configuration
├── keys.env             # Shared API keys (.env format)
├── keys/                # Your cryptographic identity
│   ├── agent.key        # Ed25519 private key (NEVER SHARE)
│   └── recovery.txt     # 12-word recovery phrase
└── logs/                # Operation logs
    └── cli.log          # CLI command history
```

## File Descriptions

### `config.toml` - Basic Configuration
Minimal configuration that matches project structure:

```toml
# ~/.co/config.toml
[connectonion]
framework_version = "0.0.7"
created = "2025-01-15T10:30:00.000000"

[cli]
version = "1.0.0"

[agent]
address = "0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a"
short_address = "0x7a9f...7f8a"
email = "0x7a9f3b2c@mail.openonion.ai"
email_active = true
created_at = "2025-01-15T10:30:00.000000"
algorithm = "ed25519"
default_model = "gpt-4o-mini"
max_iterations = 10

[auth]
token = "eyJhbGciOiJI..."  # JWT token for network auth (auto-generated)
```

That's it - just version info, your agent identity, and auth token. No complex settings.

### `keys.env` - Shared API Keys
Store your API keys once, use in all projects.

```bash
# ~/.co/keys.env
OPENAI_API_KEY=sk-proj-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
GOOGLE_API_KEY=AIzaSyxxx
GROQ_API_KEY=gsk_xxx
```

**Benefits:**
- Enter API keys once, not for every project
- Standard `.env` format
- Automatically copied to new projects

**How it works:**
```bash
# When you create a project
$ co create my-agent

✔ Use API keys from ~/.co/keys.env? (Y/n) › Y
# Keys are copied to project/.env
```

### `keys/` - Cryptographic Identity

Your identity for future network features (agent-to-agent communication, reputation).

#### `agent.key` - Private Key
- Ed25519 private key
- Signs your agent operations
- **NEVER SHARE THIS FILE**

#### `recovery.txt` - Recovery Phrase
```
carbon trophy husband quiz fabric pause obtain practice citizen moral ecology hollow
```
- 12-word recovery phrase
- Can restore your identity
- **Keep this safe**

### `logs/cli.log` - Command History

Simple log of CLI commands for debugging:
```
2024-01-15 10:30:00 co create my-agent
2024-01-15 10:31:00 co init
```

## First Time Setup

When you run your first `co` command:

```bash
$ co create my-first-agent

# If ~/.co doesn't exist:
✨ Creating ConnectOnion home directory...
  ✓ Generated identity keypair
  ✓ Created recovery phrase
  ✓ Created ~/.co/config.toml
  ✓ Created ~/.co/keys.env (add your API keys here)

# Then continues with project creation...
```

The global `config.toml` is automatically created with:
- Current CLI version
- Creation timestamp
- Your unique address (derived from public key)

## Adding API Keys

### Manual Setup
Edit `~/.co/keys.env` directly:
```bash
# Open in your editor
nano ~/.co/keys.env

# Add your keys
OPENAI_API_KEY=sk-proj-your-key-here
```

### During Project Creation
```bash
$ co create my-agent

✔ Enable AI features? › Y
✔ Use API keys from ~/.co/keys.env? › Y
# Or enter new key if keys.env is empty
✔ Paste your API key: › sk-proj-xxx
  ✓ Added to ~/.co/keys.env
  ✓ Copied to project/.env
```

## Security

### File Permissions
The CLI automatically sets secure permissions:
```bash
~/.co/keys.env          # 600 (only you can read/write)
~/.co/keys/             # 700 (only you can access)
~/.co/keys/*.key        # 600 (only you can read/write)
```

### What to Keep Secret
**Never share these files:**
- `keys.env` - Contains API keys
- `keys/agent.key` - Your private key
- `keys/recovery.txt` - Recovery phrase

## Simple Operations

### Check if global config exists
```bash
ls ~/.co
cat ~/.co/config.toml
```

### Add new API key
```bash
echo "NEW_API_KEY=xxx" >> ~/.co/keys.env
```

### View your identity address
```bash
# It's in the config.toml
grep address ~/.co/config.toml
```

### Backup your identity
```bash
# Just save the recovery phrase somewhere safe
cat ~/.co/keys/recovery.txt
```

## Moving to New Machine

### Option 1: Copy the directory
```bash
# Copy ~/.co to new machine
cp -r ~/.co /path/to/backup
```

### Option 2: Use recovery phrase
```bash
# On new machine (future feature)
co recover
> Enter recovery phrase: [twelve words]
```

## Troubleshooting

### Permission Denied
```bash
# Fix permissions if needed
chmod 600 ~/.co/keys.env
chmod 700 ~/.co/keys
```

### Missing keys.env
```bash
# Create it manually
touch ~/.co/keys.env
chmod 600 ~/.co/keys.env
```

## Config File Format

Both global (`~/.co/config.toml`) and project (`.co/config.toml`) configs use the same TOML format with sections:
- `[connectonion]` - Framework version information
- `[cli]` - CLI version
- `[agent]` - Agent identity and settings
- `[auth]` - Authentication token
- That's it - no complex nested settings

## Design Philosophy

We keep `~/.co/` minimal:
- **Only essential files** - Config, API keys, identity, logs
- **Simple config** - Just version and address info
- **Standard formats** - .toml for config, .env for keys
- **Future-ready** - Identity system for future network features

## Summary

The global `~/.co/` directory is simple:
1. **Config** (`config.toml`) - Basic version and address info
2. **API Keys** (`keys.env`) - Share across all projects
3. **Identity** (`keys/`) - For future network features
4. **Logs** (`logs/cli.log`) - Debug command history

That's it. No complex configuration, no unnecessary features. Just the essentials to make creating projects easier.
