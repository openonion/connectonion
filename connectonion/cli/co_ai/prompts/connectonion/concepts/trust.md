# Trust in ConnectOnion

Trust is a **host layer** concern that controls who can access your agent. It manages onboarding, access control, and client state transitions.

## Quick Start

```python
from connectonion import Agent
from connectonion.network import host

# Create your agent (no trust here - agent only cares about its job)
agent = Agent("my_service", tools=[process_data])

# Host it with trust (trust is a host concern)
host(agent, trust="careful")  # Default: verify before allowing access
```

## Core Concepts

### Separation of Concerns

| Layer | Responsibility |
|-------|----------------|
| **Agent** | What it does (skills, tools, reasoning) |
| **Host** | How it's accessed (network, trust, security) |

```python
# Agent is pure - only cares about its job
agent = Agent("translator", tools=[translate])

# Trust is configured at host level
host(agent, trust="open")     # Dev: trust everyone
host(agent, trust="careful")  # Staging: verify first
host(agent, trust="strict")   # Prod: whitelist only
```

### Two-Tier Verification

| Type | Tokens | When to Use |
|------|--------|-------------|
| **Fast Rules** | Zero | Simple checks (invite code, payment, whitelist) |
| **Trust Agent** | Burns tokens | Complex decisions (behavior analysis, edge cases) |

90% of requests use fast rules (instant, free). 10% use trust agent (LLM reasoning, rare).

## Trust Levels

### Open (Development)

Trust everyone. No verification.

```python
host(agent, trust="open")
```

Use for: Local development, Jupyter notebooks, testing.

### Careful (Default)

Verify strangers before granting access. Fast rules first, then trust agent for complex cases.

```python
host(agent, trust="careful")
```

Use for: Staging, testing, pre-production.

### Strict (Production)

Whitelist only. No exceptions.

```python
host(agent, trust="strict")
```

Use for: Production, sensitive data, payments.

## Client States

```
Promotion Chain (earned trust):

┌─────────────┐   verify    ┌─────────────┐  earn trust  ┌─────────────┐
│  Stranger   │ ──────────► │   Contact   │ ───────────► │  Whitelist  │
└─────────────┘             └─────────────┘              └─────────────┘
      │                           │                            │
      │ block                     │ demote                     │ demote
      ▼                           ▼                            ▼
┌─────────────┐             ┌─────────────┐              ┌─────────────┐
│  Blocklist  │             │  Stranger   │              │   Contact   │
└─────────────┘             └─────────────┘              └─────────────┘


Admin (separate, manual only):

┌─────────────┐  set_admin()   ┌─────────────┐
│  Any Level  │ ─────────────► │    Admin    │
└─────────────┘                └─────────────┘
                                     │
                               remove_admin()
                                     │
                                     ▼
                               ┌─────────────┐
                               │  Previous   │
                               └─────────────┘
```

### Client Levels

| Level | Description | Access |
|-------|-------------|--------|
| **Stranger** | Unknown client, not verified | Limited or none |
| **Contact** | Verified via invite/payment | Standard access |
| **Whitelist** | Trusted, pre-approved | Full access |
| **Admin** | Can manage other clients | Full access + management |
| **Blocklist** | Blocked, denied access | No access |

## Trust Policy Files

Trust policies are markdown files with YAML frontmatter. YAML defines fast rules (no tokens), markdown body defines trust agent behavior (for complex decisions).

```yaml
# prompts/trust/careful.md
---
fast_rules:
  - if: has_invite_code
    action: verify_invite
    on_success: promote_to_contact

  - if: is_blocked
    action: deny

  - if: is_whitelist
    action: allow

  - if: is_stranger
    action: deny

use_agent:
  - when: requests > 10
    reason: "Evaluate for promotion"

cache: 24h
---

# Trust Agent Policy

You handle complex trust decisions.

## Available Tools
- promote_to_contact(client_id)
- block(client_id, reason)

## When to Promote
Promote stranger to contact when:
- 10+ requests with good behavior
- No suspicious patterns
```

## Atomic Functions

Trust manager provides simple atomic functions as tools:

```python
# Promotion (earned)
promote_to_contact(client_id)    # Stranger → Contact
promote_to_whitelist(client_id)  # Contact → Whitelist

# Demotion
demote_to_contact(client_id)     # Whitelist → Contact
demote_to_stranger(client_id)    # Contact → Stranger

# Blocking
block(client_id, reason)
unblock(client_id)

# Admin (manual only)
set_admin(client_id, by_admin)
remove_admin(client_id, by_admin)
```

## Custom Trust Policies

### Option 1: Use Preset

```python
host(agent, trust="careful")  # Uses prompts/trust/careful.md
```

### Option 2: Custom Markdown File

```python
host(agent, trust="./my_policy.md")
```

### Option 3: Custom TrustAgent

```python
from connectonion.network.trust import TrustAgent

trust = TrustAgent(
    system_prompt="./my_policy.md",
    tools=[my_custom_verifier]
)
host(agent, trust=trust)
```

## Environment-Based Defaults

```python
# No trust specified - auto-detected from environment
host(agent)

# CONNECTONION_ENV=development → trust="open"
# CONNECTONION_ENV=staging     → trust="careful"
# CONNECTONION_ENV=production  → trust="strict"
```

## List Management

Trust manager maintains lists at `~/.co/`:

```
~/.co/
├── contacts.txt     # Verified contacts
├── whitelist.txt    # Trusted, pre-approved
├── admins.txt       # Can manage other clients
└── blocklist.txt    # Blocked clients
```

## FAQ

**Q: What's the default trust level?**
A: `"careful"` - verify strangers, allow contacts.

**Q: Do fast rules burn tokens?**
A: No. Fast rules are simple if/then executed by host. Zero tokens.

**Q: When does trust agent run?**
A: Only when `use_agent` triggers fire (e.g., after 10 requests). Rare.

**Q: Can I use the same agent with different trust levels?**
A: Yes. Trust is host config, not agent config.

```python
# Same agent, different trust
host(agent, trust="open")    # Dev
host(agent, trust="strict")  # Prod
```
