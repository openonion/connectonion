# ConnectOnion CLI

The `co` command-line interface lets you create production-ready AI agent projects in seconds.

## The Problem

Setting up AI agent projects is tedious:
- Manual `.env` file configuration
- Copy-pasting boilerplate code
- Setting up authentication and API keys
- Managing cryptographic identity
- Inconsistent project structure

## The Solution

```bash
co create my-agent
cd my-agent
python agent.py
```

Done. You now have a complete, working AI agent.

## Quick Start (60 seconds)

```bash
# Install
pip install connectonion

# Create agent
co create my-agent

# Run it
cd my-agent
python agent.py
```

The CLI automatically:
1. Creates your global identity (`~/.co/`)
2. Guides you through API key setup
3. Generates complete project structure
4. Authenticates for managed keys (free credits)

## All Commands

### Project Commands

#### `co create [name]` - Create New Project

Creates a new directory with complete agent project.

**Basic usage:**
```bash
co create my-agent              # Interactive
co create my-agent --yes        # Skip prompts
co create my-agent -t browser    # Specify template
```

**Options:**
- `[name]` - Project name (creates directory)
- `--template, -t` - Template: `minimal` (default), `coder`, `browser`, `web-research`, `custom`
- `--key` - API key (auto-detects provider)
- `--description` - For custom templates
- `--yes, -y` - Skip all prompts
- `--ai/--no-ai` - Enable/disable AI (enabled by default)

**Templates:**
- **minimal** - Basic agent with simple tools
- **coder** - Filesystem + shell access for coding tasks
- **browser** - Browser automation with Playwright
- **web-research** - Web scraping and research
- **custom** - AI-generated from description

**Examples:**
```bash
# Simple
co create my-agent

# With template
co create scraper -t browser

# Custom AI-generated
co create email-bot -t custom --description "Monitor Gmail and respond to urgent emails"

# Non-interactive
co create quick-agent --yes
```

**What it creates:**
```
my-agent/
├── agent.py                 # Main agent
├── .env                     # API keys (from ~/.co/keys.env)
├── .co/
│   ├── host.yaml            # Project config
│   └── docs/                # Framework docs
├── co-vibecoding-principles-docs-contexts-all-in-one.md
└── .gitignore               # Safe defaults
```

---

#### `co init` - Add to Existing Directory

Adds ConnectOnion to existing project safely.

**Basic usage:**
```bash
cd my-existing-project
co init                      # Safe - preserves existing files
```

**What it does:**
- ✅ **Preserves** existing files and `.env`
- ✅ **Appends** only missing API keys
- ✅ **Updates** `.co/docs/` to latest
- ✅ **Skips** existing files (like `agent.py`)

**Options:**
Same as `co create` (except no `[name]` parameter).

**Examples:**
```bash
# Add to existing project
cd my-django-app
co init

# With template
co init --template browser

# Update docs only
co init  # Refreshes .co/docs/ to latest version
```

**Safe for existing projects:**
```bash
# Your existing .env
DATABASE_URL=postgres://localhost/mydb
SECRET_KEY=mysecret

# After co init - preserved and appended
DATABASE_URL=postgres://localhost/mydb    # ← kept
SECRET_KEY=mysecret                        # ← kept

# ConnectOnion API Keys                    # ← appended
OPENAI_API_KEY=sk-proj-xxx                 # ← added
```

---

### Authentication & Account Commands

#### `co auth` - Authenticate for Managed Keys

One-time setup for managed LLM keys (free credits included).

**Basic usage:**
```bash
co auth
```

**What it does:**
1. Signs message with your Ed25519 key
2. Authenticates with OpenOnion backend
3. Saves `OPENONION_API_KEY` to `~/.co/keys.env`
4. Activates your agent email

**Using managed keys:**
```python
from connectonion import llm_do

# Use co/ prefix
response = llm_do("Hello", model="co/gpt-4o")
response = llm_do("Hello", model="co/claude-3-5-sonnet")
response = llm_do("Hello", model="co/gemini-1.5-pro")
```

**Available models:**
- OpenAI: `co/gpt-4o`, `co/gpt-4o-mini`, `co/o4-mini`
- Anthropic: `co/claude-3-5-sonnet`, `co/claude-3-5-haiku`
- Google: `co/gemini-1.5-pro`, `co/gemini-1.5-flash`
- And more...

**Benefits:**
- Free credits to start
- No separate API keys needed
- Unified billing
- Automatic rate limiting

**Example output:**
```bash
$ co auth

📂 Using global ConnectOnion keys (~/.co)
✓ Authenticated (Balance: $5.00)
✓ Saved to ~/.co/keys.env
✓ Saved to .env
```

---

#### `co status` - Check Account and Deployments

Shows your managed keys balance, usage, and deployed agents.

**Basic usage:**
```bash
co status
```

**Example output:**
```bash
$ co status

ConnectOnion Account Status
============================

Address:  0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a
Email:    0x7a9f3b2c@mail.openonion.ai
Balance:  $5.00

Deployed Agents
┏━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Project     ┃ Status  ┃ Active ┃ Container ┃ URL                                        ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ co-ai-agent │ running │ yes    │ running   │ https://co-ai-agent-0x....agents.openonion.ai │
└─────────────┴─────────┴────────┴───────────┴────────────────────────────────────────────┘
```

**When to use:**
- Check remaining credits
- Verify authentication
- See account details
- See deployed agents and their URLs

---

#### `co reset` - Reset Account

**⚠️ WARNING**: Destructive operation. Deletes all data and creates new account.

**Basic usage:**
```bash
co reset
```

**What it does:**
- Deletes your account data
- Clears balance and usage history
- Creates new account with new keys
- Generates new address and email

**When to use:**
- Starting completely fresh
- Testing account creation
- Removing old identity

**Example:**
```bash
$ co reset

⚠️  WARNING: This will delete ALL your data
Including:
  - Account balance
  - Usage history
  - Current identity

Continue? (y/N): y

✓ Account reset
✓ New identity created
✓ New address: 0x9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0
```

---

### Utility Commands

#### `co doctor` - Diagnose Issues

Comprehensive diagnostics for your ConnectOnion installation.

**Basic usage:**
```bash
co doctor
```

**What it checks:**
- **System Info**
  - ConnectOnion version
  - Python version and path
  - Virtual environment status
  - Command location (`co` in PATH)
  - Package installation path

- **Configuration**
  - Config files (`.co/host.yaml`)
  - Keys directory (`.co/keys/`)
  - API keys in `.env` files
  - Agent identity

- **Connectivity**
  - Backend reachability
  - Authentication status
  - Network connectivity

**Example output:**
```bash
$ co doctor

🔍 ConnectOnion Diagnostics

┌─ System ─────────────────────────────────┐
│ Version        ✓ 0.0.7                   │
│ Python         ✓ 3.11.5                  │
│ Python Path    /usr/local/bin/python3    │
│ Environment    ✓ Virtual environment     │
│ Venv Path      /Users/you/venv           │
│ Command        ✓ /Users/you/venv/bin/co  │
│ Package        /Users/you/venv/lib/...   │
└──────────────────────────────────────────┘

┌─ Configuration ──────────────────────────┐
│ Config         ✓ .co/host.yaml           │
│ Keys           ✓ .co/keys/agent.key      │
│ API Key        ✓ Found in environment    │
│ Key Preview    sk-proj-abc123...         │
└──────────────────────────────────────────┘

┌─ Connectivity ───────────────────────────┐
│ Backend        ✓ https://oo.openonion.ai │
│ Authentication ✓ Valid credentials       │
└──────────────────────────────────────────┘

✅ Diagnostics complete!

Run 'co auth' if you need to authenticate
```

**When to use:**
- Installation issues
- Command not found
- API key problems
- Authentication failures
- General troubleshooting

**Common issues it detects:**
- Missing `co` command in PATH
- Python version incompatibility
- Missing API keys
- Invalid authentication
- Network connectivity problems
- Incorrect file permissions

---

#### `co copy <name>` - Copy Built-In Tools, Plugins, Skills & Prompts

Copy built-in tools, plugins, prompt templates, trust policies, TUI components, and bundled skills to your project for customization.

**Basic usage:**
```bash
co copy --list              # See available items
co copy Gmail               # Copy to ./tools/
co copy re_act              # Copy to ./plugins/
co copy ship-feature        # Copy to ./.co/skills/
```

**Options:**
- `--list, -l` - List available tools, plugins, skills, prompts, trust policies, and TUI components
- `--path, -p` - Custom destination path
- `--force, -f` - Overwrite existing files

**Examples:**
```bash
# Copy a tool
co copy Gmail
# Creates: ./tools/gmail.py

# Copy a plugin
co copy re_act
# Creates: ./plugins/re_act.py

# Copy a bundled skill
co copy ship-feature
# Creates: ./.co/skills/ship-feature/SKILL.md

# Copy multiple items
co copy Gmail Shell memory

# Custom destination
co copy Gmail --path ./my_tools/
```

**After copying:**
```python
# Before (from package)
from connectonion import Gmail

# After (from your copy)
from tools.gmail import Gmail  # Now customize it!
```

See [copy documentation](copy.md) for full details.

---

#### `co setup` - Global Identity & Skill Library

One command to set up everything in `~/.co/` needed to publish an agent: keypair, `agent.json` profile, and a populated skill library.

**Basic usage:**
```bash
co setup --name my-alias --bio "Concise one-liner"
```

**What it does:**
1. Bootstraps identity (`~/.co/keys/agent.key`) if missing
2. Writes `~/.co/agent.json` with signing address, alias, bio, and skill metadata
3. Runs `co skills discover && co skills copy --all && co skills manifest` → populates `~/.co/skills/` and updates `agent.json.skills`
4. Reports auth status

**No separate bundle directory** — `~/.co/` itself is what `oo-publish` reads at publish time.

**Options:**
- `--name, -n` - Alias for `agent.json` (default `$USER`)
- `--bio, -b` - One-line bio
- `--force, -f` - Overwrite existing `agent.json` (backs up to `.bak`)
- `--no-skills` - Skip the library refresh

See [setup documentation](setup.md) for full details.

---

#### `co skills` - Discover & Import Skills

Scan skill files across Claude Code, Codex, Cursor, Kiro, project `.co/skills/`, and user `~/.co/skills/`, then import selected skills into `~/.co/skills/`.

**Basic usage:**
```bash
co skills discover           # Scan all known agent skill directories
co skills copy ship-feature  # Import into ~/.co/skills/
co skills copy --all         # Import every discovered skill
co skills manifest          # Merge {name, description, publish: false}[] into ~/.co/agent.json
co skills list               # Show what's installed
```

**Options for discover:**
- `--no-save` - Don't write `~/.co/skills/index.json`
- `--json` - Print index as JSON
- `--include-namespaced` - Include plugin-namespaced skills (default filtered)

**Options for copy:**
- `--all, -a` - Copy every discovered skill (dedupe by source priority)
- `--source, -s` - Pick a source: `claude`, `codex`, `cursor`, `kiro`, `co-user`, `co-project`
- `--force, -f` - Overwrite existing skill(s)

**Sources scanned:** `./.co/skills/`, `~/.co/skills/`, `~/.claude/skills/`, `~/.codex/skills/`, `~/.cursor/rules/`, `~/.kiro/steering/`

`co ai` loads `.co/skills/` and `~/.co/skills/` automatically. The runtime `skills` plugin also checks Claude skill directories directly, but `co skills copy` gives publishing one normalized library under `~/.co/skills/`.

See [skills documentation](skills.md) for full details.

---

#### `co sub` - Subscribe to & Sync Published Agents

Follow another agent's `0x` address, mirror their published skills into `~/.co/subs/<alias>/`, and fan them out into every coding agent you use (Claude Code, Codex, OpenClaw, Cursor, Kiro). `co sub` is the **sync verb** — record-and-pull are the same operation.

**Basic usage:**
```bash
co sub sync 0xcd92510bb6cc090374ecc345ef8c19b9d3797624fd1fbf7e078a9372fc31bdc1   # sync one (first subscribe or refresh)
co sub                       # sync ALL subscribed publishers
co sub list                  # local view, no relay
co sub remove changxing      # unsubscribe (by alias or address)
```

**What `co sub sync <addr>` does:**
1. `GET /api/relay/agents/<addr>/profile` → write `~/.co/subs/<alias>/agent.json`
2. Pull each `SKILL.md` body → `~/.co/subs/<alias>/skills/<name>/`
3. Append `<address> <alias>` to `~/.co/subscriptions.txt` (deduped)
4. Symlink/copy into every detected `~/.<tool>/` directory

**`co sub` (no subcommand)** walks every entry in `subscriptions.txt` and re-syncs each in order. Stops at the first failure (fail-fast — re-run after fixing).

**Address-only by design** — aliases are mutable and hijackable, so first-time subscriptions require a `0x` address. Once pinned in `subscriptions.txt`, the alias works as a shorthand for refresh and remove.

**Subscriptions file:** `~/.co/subscriptions.txt` (plain text, same shape as `contacts.txt` / `whitelist.txt`).

See [sub documentation](sub.md) for the full fan-out behavior and v1 limitations.

---

#### `co browser <command>` - Browser Automation

Drive one persistent browser from the shell. Call a browser function directly, or use `do` for the AI agent. State persists between commands until you `close`. See [browser.md](browser.md).

**Direct function calls:**
```bash
co browser go_to localhost:3000       # navigate
co browser take_screenshot shot.png   # screenshot
co browser get_current_url            # print current URL
co browser get_links_from_page        # one link per line (pipeable)
co browser close                      # close browser, stop daemon
```

**Natural language (AI agent on the same browser):**
```bash
co browser do "click the login button and open the dashboard"
```

**Scripting (clean stdout, exit codes):**
```bash
url=$(co browser get_current_url)
co browser get_links_from_page | grep github
co browser --headless go_to "$DEPLOY_URL"   # --headless for CI
```

**When to use:**
- Scripting exact browser steps (direct calls)
- Letting the agent handle a task (`do`)
- Visual verification and debugging

---

## Global Configuration

### The `~/.co/` Directory

On first use, ConnectOnion creates global configuration:

```
~/.co/
├── keys.env             # Shared API keys and identity
├── keys/                # Master Ed25519 keypair
│   ├── agent.key        # Private key (NEVER share)
│   ├── agent.pub        # Public key
│   └── recovery.txt     # 12-word recovery phrase
└── logs/                # CLI activity logs
```

**Your Global Identity:**
- **Address**: Hex-encoded Ed25519 public key (`0x7a9f3b2c...`)
- **Email**: Derived address (`0x7a9f3b2c@mail.openonion.ai`)
- **Keys**: For authentication and signing

All projects share this identity by default (like using same email for all repos).

---

## API Key Management

### Auto-Detection

The CLI automatically detects providers:

| Provider | Format | Example | Env Variable |
|----------|--------|---------|--------------|
| OpenAI | `sk-...` / `sk-proj-...` | `sk-proj-abc123...` | `OPENAI_API_KEY` |
| Anthropic | `sk-ant-...` | `sk-ant-api03-xyz...` | `ANTHROPIC_API_KEY` |
| Google | `AIza...` | `AIzaSyAbc123...` | `GEMINI_API_KEY` |
| Groq | `gsk_...` | `gsk_abc123...` | `GROQ_API_KEY` |
| OpenOnion | JWT token | `eyJhbGciOiJ...` | `OPENONION_API_KEY` |

### Priority Order

1. `--key` flag
2. Environment variables
3. `~/.co/keys.env` (global)
4. Interactive prompt
5. Skip (add later)

### Sharing Across Projects

Keys in `~/.co/keys.env` are auto-copied to new projects:

```bash
# First project - enter key once
$ co create first-project
✔ Paste API key: sk-proj-xxx
  ✓ Saved to ~/.co/keys.env

# Every project after - automatic
$ co create second-project
✓ Found API keys in ~/.co/keys.env
✓ Copied to project
```

---

## Complete Examples

### First-Time User

```bash
$ pip install connectonion
$ co create my-first-agent

🚀 Welcome to ConnectOnion!
✨ Setting up global configuration...
  ✓ Generated master keypair
  ✓ Your address: 0x7a9f...7f8a
  ✓ Created ~/.co/keys.env

🔐 Authenticating with OpenOnion...
  ✓ Authenticated (Balance: $5.00)

✔ Paste API key (optional): sk-proj-xxx
  ✓ Detected OpenAI
  ✓ Saved to ~/.co/keys.env

✅ Created my-first-agent

cd my-first-agent && python agent.py

💡 Vibe Coding: Use Claude/Cursor with
   co-vibecoding-principles-docs-contexts-all-in-one.md

📚 Resources:
   Docs    → https://docs.connectonion.com
   Discord → https://discord.gg/4xfD9k8AUF
   GitHub  → https://github.com/openonion/connectonion

$ cd my-first-agent
$ python agent.py
```

### Adding to Existing Project

```bash
$ cd my-django-app
$ ls
manage.py settings.py .env

$ cat .env
DATABASE_URL=postgres://localhost/mydb
SECRET_KEY=mysecret

$ co init

✓ Using global identity
✓ Found existing .env
✓ Appending API keys

$ cat .env
DATABASE_URL=postgres://localhost/mydb
SECRET_KEY=mysecret

# ConnectOnion API Keys
OPENAI_API_KEY=sk-proj-xxx
```

### Quick Troubleshooting

```bash
# Something not working?
$ co doctor

# Shows:
# - What's installed correctly
# - What's missing
# - Connectivity status
# - Specific error locations
```

---

## Security & Identity

### Ed25519 Cryptographic Identity

Every installation generates master Ed25519 keypair:

**Used for:**
1. Agent addressing (unique identifier)
2. Authentication (passwordless)
3. Message signing (cryptographic proof)
4. Secure communication (encryption)

**Security:**
- Never share `.co/keys/` directory
- Never commit `.env` files
- Backup 12-word recovery phrase
- Keys auto-added to `.gitignore`

### Recovery Phrase

12-word phrase in `~/.co/keys/recovery.txt` restores keys:

```bash
# If you lose keys
co restore "your twelve word recovery phrase here"
```

**Store safely:**
- Write down physically
- Use password manager
- Never in git repos
- Never share

---

## Best Practices

### 1. Choose the Right Command

```bash
# New project?
co create my-new-project

# Existing project?
cd my-project && co init
```

### 2. Use Templates

```bash
# Learning? Start simple
co create learn -t minimal

# Browser work? Use template
co create scraper -t browser

# Specific needs? AI generates
co create custom -t custom --description "Your needs"
```

### 3. Set Up Keys Once

```bash
# First project - enter key
co create first-project
# (paste key)

# All future projects - automatic
co create second-project --yes  # No prompt!
```

### 4. Use Managed Keys

```bash
# Authenticate once
co auth

# Free credits in code
agent = Agent("dev", model="co/gpt-4o-mini")
```

### 5. Leverage Documentation

```bash
# Every project includes comprehensive docs
# Drag to Cursor/Claude Code:
co-vibecoding-principles-docs-contexts-all-in-one.md
```

---

## Troubleshooting

### Command Not Found

```bash
# Check installation
pip show connectonion

# Reinstall
pip uninstall connectonion
pip install connectonion

# Use full path
python -m connectonion.cli.main create my-agent
```

### Permission Denied

```bash
# Fix global
chmod 700 ~/.co
chmod 600 ~/.co/keys.env

# Fix project
chmod 700 my-agent/.co
chmod 600 my-agent/.env
```

### API Key Issues

```bash
# Check format
cat ~/.co/keys.env

# Test auth
co auth

# Diagnose
co doctor
```

### Directory Exists

```bash
$ co create my-agent
❌ 'my-agent' exists. Try: co create my-agent-2

# Or add to existing
cd my-agent
co init
```

---

## Advanced Usage

### Non-Interactive CI/CD

```bash
# Fully automated
export OPENAI_API_KEY=sk-proj-xxx
co create prod-agent --yes --template minimal
cd prod-agent
python agent.py --test
```

### Batch Creation

```bash
# Multiple projects
for name in agent1 agent2 agent3; do
    co create $name --yes
done
```

### Update Docs Only

```bash
# Refresh to latest
cd my-old-project
co init  # Updates .co/docs/ without changing code
```

---

#### `co deploy` - Deploy to Cloud

Deploy your agent to ConnectOnion Cloud.

**Basic usage:**
```bash
co deploy
```

**Requirements:**
- Git repository with committed code
- `.co/host.yaml` (created by `co create` or `co init`)
- Authenticated (`co auth`)

**Example:**
```bash
$ co deploy

Deploying to ConnectOnion Cloud...

  Project: my-agent
  Env vars: 3 keys

Uploading...
Building...

Deployed!
Agent URL: https://my-agent-abc123.agents.openonion.ai
```

> **Beta**: This feature is in beta. See [Deploy Guide](../network/deploy.md) for details.

---

## Command Reference Summary

| Command | Purpose | Interactive | Safe for Existing |
|---------|---------|-------------|-------------------|
| `co create` | New project | Yes | N/A (creates new dir) |
| `co init` | Add to existing | Yes | ✅ Yes |
| `co copy` | Copy built-in tools/plugins/skills/prompts | No | ✅ Yes |
| `co skills` | Discover/import skills | No | ✅ Yes |
| `co setup` | Global identity + skill library | No | ✅ Yes (idempotent) |
| `co sub` | Subscribe to a publisher's skills | No | ✅ Yes (idempotent) |
| `co auth` | Get managed keys | No | ✅ Yes |
| `co status` | Check balance and deployments | No | ✅ Yes |
| `co deploy` | Deploy to cloud | No | ✅ Yes |
| `co reset` | Reset account | Yes | ⚠️ Destructive |
| `co doctor` | Diagnose issues | No | ✅ Yes |
| `co browser` | Browser command | No | ✅ Yes |

---

## See Also

- [Agent Documentation](../concepts/agent.md) - Building agents
- [Tools Documentation](../concepts/tools.md) - Custom tools
- [Interactive Debugging](../auto_debug.md) - `@xray` debugger
- [Trust System](../concepts/trust.md) - Multi-agent trust
- [Getting Started](../quickstart.md) - Full tutorial
