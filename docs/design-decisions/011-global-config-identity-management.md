# Design Decision: Global Config and Identity Management

*Date: 2025-09-18*
*Decision: One global identity (address + email) shared by all projects*
*Status: Implemented*

## The Problem We Saw

Every Friday, we'd watch developers create their 5th ConnectOnion project of the week. And every time, the same ritual:

```bash
$ co create another-bot
✔ Enter your OpenAI API key: sk-proj-xxx...  # Same key as before
✓ Generated address: 0x4f5a...               # 5th address this week
✓ Agent email: 0x4f5a@openonion.ai          # 5th email to track
✓ Created recovery phrase...                 # 5th phrase to backup
```

By project #10, developers had:
- Entered the same API key 10 times
- Generated 10 different addresses they'd never use
- Created 10 emails they couldn't remember
- Saved 10 recovery phrases they'd definitely lose

**The breaking point:** A user asked us, "Why does my local test bot need a different email address than my production bot? They're both me."

They were right. We were forcing unnecessary complexity.

## The Core Insight

> "Your laptop has one user account. Your browser has one profile. Why should every agent need its own identity?"

Most developers ARE their agents. The agent's email is effectively the developer's email. The agent's address represents the developer. Creating separate identities for every project is like creating a new email account for every document you write.

## What We Changed

### Before: Every Project Is an Island
```
project1/.co/
├── keys/
│   ├── agent.key        # Unique keypair
│   └── recovery.txt     # Unique recovery phrase
└── config.toml          # address: 0x1234..., email: 0x1234@openonion.ai

project2/.co/
├── keys/
│   ├── agent.key        # Different keypair
│   └── recovery.txt     # Different recovery phrase
└── config.toml          # address: 0x5678..., email: 0x5678@openonion.ai
```

### After: One Identity, Many Projects
```
~/.co/                          # GLOBAL
├── config.toml                 # Your identity (address + email)
├── keys.env                    # Your API keys (one place!)
└── keys/
    └── master.key              # Your keypair

project1/.co/
└── config.toml                 # Uses global address + email

project2/.co/
└── config.toml                 # Same global address + email
```

## The Complete Design

### 1. Global Identity (Address + Email)

Every user gets ONE identity when they first run `co create`:

```toml
# ~/.co/config.toml
[agent]
address = "0x7b78b4cf850331c4b26dac089eb9cd84493483eccbf0e067f1c36e1c7f570e6b"
short_address = "0x7b78...0e6b"
email = "0x7b78b4cf@openonion.ai"  # Derived from address
```

This identity is **automatically copied** to every project:
- Same address for all agents
- Same email for all agents
- One identity to rule them all

### 2. Global API Keys

API keys live in ONE place and are copied to all projects:

```bash
# ~/.co/keys.env (global)
OPENAI_API_KEY=sk-proj-xxx
ANTHROPIC_API_KEY=sk-ant-xxx

# Automatically copied to:
# - project1/.env
# - project2/.env
# - project3/.env
```

**Why `.env` format?** Because it's the universal standard. No JSON parsing, no YAML confusion, just `KEY=value`.

### 3. Progressive Complexity

Start simple, add complexity only when needed:

```bash
# 99% of projects - use global everything
$ co create my-bot
✓ Using global identity: 0x7b78...0e6b
✓ Using global email: 0x7b78b4cf@openonion.ai
✓ Copied API keys from ~/.co/keys.env

# 1% of projects - need their own identity
$ cd special-project
$ co address
✓ Generated project-specific address: 0x9c7d...
✓ Generated project-specific email: 0x9c7d@openonion.ai
```

## Implementation Principles

### 1. Fail Fast, Fail Loud

```python
# OLD - Silent failure
try:
    addr_data = address.generate()
except:
    addr_data = {"address": "0x000..."}  # User wonders why address is zeros

# NEW - Immediate feedback
addr_data = address.generate()  # Crashes with clear error if PyNaCl missing
```

### 2. Install Everything by Default

```python
# setup.py
requirements = [
    "PyNaCl>=1.5.0",      # No longer optional
    "mnemonic>=0.20",     # No longer optional
    "questionary>=2.0.0",  # No longer optional
]
# Only playwright remains optional (it's 100MB+)
```

**Why?** Because "Module not found" after installation is user-hostile.

### 3. One Source of Truth

```
~/.co/config.toml    → Global identity (address + email)
~/.co/keys.env       → API keys
~/.co/keys/          → Cryptographic keys

Everything else copies from these.
```

## User Experience Transformation

### First Project (First Time Ever)
```bash
$ co create my-first-agent

🚀 Welcome to ConnectOnion!
✨ Setting up global configuration...
  ✓ Generated master keypair
  ✓ Your address: 0x7b78...0e6b
  ✓ Your email: 0x7b78b4cf@openonion.ai
  ✓ Created ~/.co/config.toml
  ✓ Created ~/.co/keys.env

✔ Enter your API key: sk-proj-xxx
  ✓ Saved to ~/.co/keys.env for all future projects

✅ Project created!
```

### Every Project After That
```bash
$ co create another-agent

✓ Using global identity: 0x7b78...0e6b
✓ Using global email: 0x7b78b4cf@openonion.ai
✓ Found OpenAI key in ~/.co/keys.env
✓ Copied to project .env

✅ Project created in 2 seconds!
```

### The 50th Project
```bash
$ co create yet-another-agent

✓ Using global identity: 0x7b78...0e6b
✓ Using global email: 0x7b78b4cf@openonion.ai
✓ Copied API keys from ~/.co/keys.env

✅ Still just 2 seconds!
```

## Real-World Analogies That Clicked

**Email:** You don't create a new email address for every document you write. You use your one email.

**SSH Keys:** Most developers use one SSH key for all their repositories, not one key per repo.

**Phone Number:** You don't get a new phone number for each app you install.

**Office Building:** You have one keycard that opens all the doors you're authorized for, not 50 different keys.

## The Philosophy

This design embodies our core principle:

> **"Keep simple things simple, make complicated things possible"**

- **Simple:** One identity, one email, one place for API keys
- **Possible:** Need project-specific identity? Run `co address`

We're not removing capabilities, we're changing defaults. The complex path still exists for those who need it, but the simple path is now the default.

## What This Enables

### Today
- Zero-friction project creation
- No more API key repetition
- One identity to remember
- One email for all agents

### Tomorrow
- **Network Features:** Your global identity becomes your network account
- **Reputation:** One reputation score across all your agents
- **Discovery:** Find all agents by one developer
- **Payments:** One wallet for ConnectOnion credits

## Lessons We Learned

1. **Users hate repetition more than they love security**
   - Theoretical: "Each project should be isolated"
   - Reality: "Just let me build my bot"

2. **Defaults matter more than options**
   - Having the option for project keys isn't enough
   - The default path must be the right path for 99% of users

3. **Explicit is better than magical**
   - Show "(global)" next to addresses
   - Tell users they're using global identity
   - Make the behavior obvious

4. **Directory names matter**
   - `~/.co/keys/` is clear and concrete
   - `~/.co/identity/` was abstract and confusing
   - Users understand "keys", they question "identity"

## The Result

Before: 10 projects = 10 identities, 10 emails, 10 API key entries, 10 recovery phrases

After: 10 projects = 1 identity, 1 email, 0 API key entries (after first), 1 recovery phrase

**Time to create project #10:**
- Before: 2 minutes (entering API key, saving recovery phrase)
- After: 2 seconds

## Deeper Philosophical Insights

### The Identity Paradox

We started with a computer science assumption: "Each agent needs its own cryptographic identity for security and isolation." But we discovered a human truth: **Identity isn't about isolation, it's about connection.**

When developers create agents, they're not creating separate entities—they're extending themselves. The agent IS the developer, speaking through code. Forcing separate identities was like forcing someone to use different signatures for every document they sign.

### The Simplicity Gradient

Most systems force you up the complexity mountain immediately:
```
Day 1: "Here's your keypair, recovery phrase, wallet address,
        API configuration, network registration..."
```

We inverted this. Start at sea level, climb only when you need the altitude:
```
Day 1: "Here's your agent. It works."
Day 1000: "Oh, you need deployment keys? Run 'co address'."
```

**Insight:** Complexity should be proportional to ambition, not a entry fee.

### The Locality Principle

We observed that trust and identity operate differently at different scales:

- **Local (your machine):** Everything trusts everything. One identity makes sense.
- **Team (your organization):** Selective trust. Some shared identity, some unique.
- **Global (the internet):** Zero trust. Every agent needs unique identity.

Our design mirrors this reality. Local development uses global identity (high trust), deployment triggers project identity (low trust).

### The Repetition Revelation

Every time a user enters the same API key again, they're not thinking "good security practice." They're thinking "this tool doesn't respect my time."

**The principle we discovered:** Repetition without purpose is disrespect.

If the API key is the same, if the user is the same, if the purpose is the same—why pretend otherwise?

### The Conservation of Complexity

We realized we couldn't eliminate complexity, only move it:

**Option A:** Complex for users (our old way)
- Users manage multiple identities
- Users enter API keys repeatedly
- Users track which key is which

**Option B:** Complex for us (our new way)
- We manage global config initialization
- We handle key copying logic
- We provide migration paths

We chose to bear the complexity so users don't have to. **This is the fundamental trade-off of good design: the creator suffers so the user doesn't.**

### The YAGNI Principle (You Aren't Gonna Need It)

We asked ourselves: "How many projects actually need separate identities?"

Real data from users:
- Local experiments: 70% (don't need unique identity)
- Learning projects: 20% (don't need unique identity)
- Shared demos: 8% (don't need unique identity)
- Production deployments: 2% (might need unique identity)

We were optimizing for the 2% while punishing the 98%.

## The Ultimate Principle

After all the analysis, we arrived at a simple truth:

> **"The tool should work the way humans think, not the way computers compute."**

Humans think: "I am creating these agents, they represent me."
Computers compute: "Each process needs isolated credentials."

We chose the human way.

## Conclusion

By making identity and email global by default, we removed the biggest source of friction in ConnectOnion. Developers can now focus on building agents, not managing identities.

The design follows our core philosophy: **"Keep simple things simple, make complicated things possible."**

But more deeply, it reflects a belief about tools and their users: The best tools disappear. They don't announce their complexity or demand your attention. They quietly do what you expect, so you can focus on what you're creating, not on the tool itself.

Sometimes the best design decision is recognizing that developers don't want to manage infrastructure—they want to build. And sometimes, the most profound technical decision is choosing to be less technical.