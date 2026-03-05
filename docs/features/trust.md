# Trust in ConnectOnion

Trust is a **host layer** concern that controls who can access your agent. It manages onboarding, access control, and client state (stranger → contact → trusted).

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

### Protocol vs Policy

Every request requires **two checks**:

| Layer | Required | Purpose |
|-------|----------|---------|
| **Signature (Protocol)** | ALWAYS | Prove identity (Ed25519) |
| **Trust Policy** | Configurable | Access control (open/careful/strict) |

```
Request Flow:
┌─────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   Request   │ ──► │ Signature Required  │ ──► │  Trust Policy   │
│  (signed)   │     │ (prove identity)    │     │ (access check)  │
└─────────────┘     └─────────────────────┘     └─────────────────┘
                              │                          │
                         ALWAYS                    CONFIGURABLE
                         REQUIRED                  (open/careful/strict)
```

**Important:** Even `trust="open"` requires valid signatures. "Open" means all verified identities are allowed - not that requests can be unsigned.

### Two Types of Access Control

| Type | Tokens | When to Use |
|------|--------|-------------|
| **Fast Rules** | Zero | Simple checks (invite code, payment, whitelist) |
| **Trust Agent** | Burns tokens | Complex decisions (behavior analysis, edge cases) |

**90% of requests**: Fast rules (instant, free)
**10% of requests**: Trust agent (LLM reasoning, rare)

## Trust Levels

All trust levels require **signed requests**. The difference is in access control policy.

### Open (Development)

Allow all **signed** requests. No additional access control.

```python
host(agent, trust="open")
```

- Signature verification: **Required** (protocol level)
- Access control: **None** (all verified identities allowed)

Use for: Local development, Jupyter notebooks, testing.

**Note:** Requests still need valid Ed25519 signatures. "Open" means no access restrictions after identity is verified.

### Careful (Default)

Verify strangers before granting access. Fast rules first, then trust agent for complex cases.

```python
host(agent, trust="careful")
```

- Signature verification: **Required** (protocol level)
- Access control: **Whitelist + contacts allowed, strangers evaluated**

Use for: Staging, testing, pre-production.

### Strict (Production)

Whitelist only. No exceptions.

```python
host(agent, trust="strict")
```

- Signature verification: **Required** (protocol level)
- Access control: **Whitelist only**

Use for: Production, sensitive data, payments.

## Request Format

All requests must be signed with Ed25519:

```json
{
    "payload": {
        "prompt": "Your message here",
        "to": "0xAgentAddress",
        "timestamp": 1699999999
    },
    "from": "0xYourPublicKey",
    "signature": "0xEd25519Signature..."
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `payload.prompt` | Yes | The message to send |
| `payload.to` | Optional | Target agent address |
| `payload.timestamp` | Yes | Unix timestamp (5 min window) |
| `from` | Yes | Your Ed25519 public key |
| `signature` | Yes | Signature of canonicalized payload |

**Signature protects against:**
- Identity spoofing (only you have your private key)
- Replay attacks (timestamp expires in 5 minutes)
- Message tampering (signature covers payload)

## Trust Policy Files

Trust policies are markdown files with YAML frontmatter. The YAML defines fast rules (no tokens), the markdown body defines trust agent behavior (for complex decisions).

### File Format

```yaml
# prompts/trust/careful.md
---
# Fast rules (no LLM, no tokens)
fast_rules:
  # Verification
  - if: has_invite_code
    action: verify_invite
    on_success: promote_to_contact

  - if: has_payment
    action: verify_payment
    on_success: promote_to_contact

  # Access control (checked in order)
  - if: is_blocked
    action: deny

  - if: is_admin
    action: allow

  - if: is_whitelist
    action: allow

  - if: is_contact
    action: allow

  - if: is_stranger
    action: deny

# When to use trust agent (burns tokens, rare)
use_agent:
  - when: requests > 10
    reason: "Evaluate stranger for promotion"

# Cache decisions
cache: 24h
---

# Trust Agent Policy

You handle complex trust decisions that fast rules can't cover.

## Your Role

Evaluate strangers and decide if they should become contacts.

## Available Tools

- `promote_to_contact(client_id)` - Stranger → Contact
- `promote_to_whitelist(client_id)` - Contact → Whitelist
- `demote_to_stranger(client_id)` - Contact → Stranger
- `block(client_id, reason)` - Add to blocklist

## Decision Process

1. Review request history
2. Look for red flags (suspicious patterns, abuse)
3. Consider value provided

## Response

Use tools to take action, or return:
- **allow** - Allow this request
- **deny** - Deny this request
```

### How Host Uses This

```
host(agent, trust=...)
        │
        ├── "open"           ──┐
        ├── "careful"          ├──► TrustAgent(trust)
        ├── "strict"           │
        ├── "./policy.md"    ──┘
        │
        └── TrustAgent(...)  ──► use directly
                │
                ▼
        TrustAgent.should_allow(client_id, request)
                │
                ├── Fast Rules (no tokens)
                │   - Check deny list (blocked)
                │   - Check allow list (whitelist, contacts)
                │   - Try onboarding (invite, payment)
                │   - Apply default
                │
                └── LLM Fallback (only if default: ask)
                    - Evaluate stranger with LLM
```

All trust inputs convert to TrustAgent internally. Developers can use string levels for simplicity or pass TrustAgent directly for more control.

## Client States

Trust manager handles all client state transitions:

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

### State Transitions

**Promotion Chain (earned):**

| From | To | How |
|------|-----|-----|
| Stranger | Contact | `promote_to_contact()` - invite code, payment, or earned |
| Contact | Whitelist | `promote_to_whitelist()` - consistent good behavior |

**Demotion (lost trust):**

| From | To | How |
|------|-----|-----|
| Whitelist | Contact | `demote_to_contact()` - trust issues |
| Contact | Stranger | `demote_to_stranger()` - suspicious activity |
| Any | Blocklist | `block()` - abuse detected |

**Admin (manual only):**

| From | To | How |
|------|-----|-----|
| Any | Admin | `set_admin()` - requires existing admin |
| Admin | Previous | `remove_admin()` - requires existing admin |

### Trust Manager Responsibilities

The trust manager (TrustAgent) handles:

1. **Onboarding** - Verify invite codes, payments
2. **Promotion** - Move clients up the trust hierarchy
3. **Demotion** - Move clients down when trust is broken
4. **Blocking** - Add abusers to blocklist
5. **List Management** - Maintain all client lists

```python
# Trust manager actions
trust_manager.promote(client_id)    # Move up one level
trust_manager.demote(client_id)     # Move down one level
trust_manager.block(client_id)      # Add to blocklist
trust_manager.unblock(client_id)    # Remove from blocklist
trust_manager.set_admin(client_id)  # Promote to admin (requires admin)
```

## Fast Rules Reference

Fast rules are simple if/then checks. No LLM, no tokens.

### Conditions (if)

| Condition | Description |
|-----------|-------------|
| `invite_code` | Client has invite code |
| `payment` | Client has confirmed payment |
| `is_stranger` | Client is a stranger |
| `is_contact` | Client is a contact |
| `is_whitelist` | Client is whitelisted |
| `is_admin` | Client is an admin |
| `is_blocked` | Client is blocked |

### Actions

| Action | Description |
|--------|-------------|
| `allow` | Allow this request |
| `deny` | Deny this request |
| `promote` | Promote to next level (stranger→contact→whitelist) |
| `demote` | Demote to previous level |
| `block` | Add to blocklist |
| `require_admin` | Only allow if client is admin |

### Examples

```yaml
fast_rules:
  # Verification → promote to contact
  - if: has_invite_code
    action: verify_invite
    on_success: promote_to_contact

  - if: has_payment
    action: verify_payment
    on_success: promote_to_contact

  # Access control (checked in order)
  - if: is_blocked
    action: deny

  - if: is_admin
    action: allow

  - if: is_whitelist
    action: allow

  - if: is_contact
    action: allow

  - if: is_stranger
    action: deny
```

## Trust Agent (Complex Decisions)

For decisions that need reasoning, the trust agent uses LLM. This burns tokens, so use sparingly.

### When to Use

```yaml
use_agent:
  # After enough requests to evaluate
  - when: requests > 10
    reason: "Evaluate for promotion"

  # Suspicious patterns
  - when: suspicious_pattern
    reason: "Investigate"

  # Manual review requested
  - when: manual_review
    reason: "Human flagged for review"
```

### Trust Agent Response

```python
# Trust agent returns:
{
    "decision": "promote",  # or allow, deny, block
    "reason": "Consistent good behavior over 50 requests",
    "cache": True  # Cache this decision
}
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

## Preset Policies

### open.md

```yaml
---
fast_rules:
  - if: always
    action: allow
---

# Open Trust (Development Only)

Trust everyone. No verification.
Never use in production.
```

### careful.md

```yaml
---
fast_rules:
  # Verification
  - if: has_invite_code
    action: verify_invite
    on_success: promote_to_contact

  - if: has_payment
    action: verify_payment
    on_success: promote_to_contact

  # Access control
  - if: is_blocked
    action: deny

  - if: is_admin
    action: allow

  - if: is_whitelist
    action: allow

  - if: is_contact
    action: allow

  - if: is_stranger
    action: deny

use_agent:
  - when: requests > 10
    reason: "Evaluate stranger for promotion"

cache: 24h
---

# Careful Trust Policy

Evaluate strangers for promotion to contacts.
```

### strict.md

```yaml
---
fast_rules:
  - if: is_blocked
    action: deny

  - if: is_admin
    action: allow

  - if: is_whitelist
    action: allow

  - if: always
    action: deny

use_agent: []  # Never use LLM
---

# Strict Trust Policy

Whitelist only. No exceptions.
```

## List Management

Trust manager maintains four lists:

```
~/.co/
├── strangers.txt    # Known strangers (optional tracking)
├── contacts.txt     # Verified contacts
├── whitelist.txt    # Trusted, pre-approved
├── admins.txt       # Can manage other clients
└── blocklist.txt    # Blocked clients
```

### Contacts

```
~/.co/contacts.txt
```

Automatically managed. Clients who verified via invite code or payment.

### Whitelist

```
~/.co/whitelist.txt
```

```
# Trusted services (full access)
translator.api.com
analyzer.local
192.168.1.*
```

### Admins

**Default admin:** The agent's own address (from `.co/address.json`) is automatically an admin. No config needed.

**Additional admins:** Add public keys to `~/.co/admins.txt`:

```
~/.co/admins.txt
```

```
# Additional admins (public keys)
0xadmin1234567890...
0xadmin0987654321...
```

Admins can:
- Promote/demote other clients
- Block/unblock clients
- Query client trust levels

### Blocklist

```
~/.co/blocklist.txt
```

```
# Blocked clients (no access)
abuser-123
spam-bot-*
```

## Environment-Based Defaults

```python
# No trust specified - auto-detected from environment
host(agent)

# CONNECTONION_ENV=development → trust="open"
# CONNECTONION_ENV=staging     → trust="careful"
# CONNECTONION_ENV=production  → trust="strict"
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Request                            │
│              (signed with Ed25519)                      │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    HOST LAYER                           │
│                                                         │
│  Routes:                                                │
│  ├── /input              (agent endpoint)              │
│  ├── /admin/trust/*      (any admin)                   │
│  │    ├── POST /admin/trust/promote                    │
│  │    ├── POST /admin/trust/demote                     │
│  │    ├── POST /admin/trust/block                      │
│  │    ├── POST /admin/trust/unblock                    │
│  │    └── GET  /admin/trust/level/{client_id}          │
│  └── /superadmin/*       (super admin only)            │
│       ├── POST /superadmin/add                         │
│       └── POST /superadmin/remove                      │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │           TrustAgent.should_allow()              │   │
│  │                                                  │   │
│  │  1. Fast Rules (no tokens)                      │   │
│  │     - Check deny list (blocked)                 │   │
│  │     - Check allow list (whitelist, contacts)    │   │
│  │     - Try onboarding (invite, payment)          │   │
│  │     - Apply default                             │   │
│  │                                                  │   │
│  │  2. LLM Fallback (only if default: ask)         │   │
│  │     - Evaluate stranger with LLM                │   │
│  │                                                  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ (verified requests only)
┌─────────────────────────────────────────────────────────┐
│                      AGENT                              │
│                                                         │
│  Pure logic - tools, skills, reasoning                  │
│  Doesn't know about trust                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Routes

Host provides these routes:

### Agent Route

| Route | Method | Description |
|-------|--------|-------------|
| `/input` | POST | Main agent endpoint |

### Admin Routes (Requires Admin)

Admin routes use **signed requests** (same as `/input`). The signer's address must be in the admins list.

**Admins list = self address (default) + ~/.co/admins.txt**

The agent's own public key is automatically an admin. No config needed - whoever deployed the agent can manage trust.

| Route | Method | Who | Description |
|-------|--------|-----|-------------|
| `/admin/trust/promote` | POST | Any admin | Promote client to next level |
| `/admin/trust/demote` | POST | Any admin | Demote client to previous level |
| `/admin/trust/block` | POST | Any admin | Block client |
| `/admin/trust/unblock` | POST | Any admin | Unblock client |
| `/admin/trust/level/{client_id}` | GET | Any admin | Get client's current level |

### Super Admin Routes (Self Address Only)

Only the agent's own address (super admin) can manage the admins list.

| Route | Method | Description |
|-------|--------|-------------|
| `/superadmin/add` | POST | Add an admin |
| `/superadmin/remove` | POST | Remove an admin |

**Example admin request:**
```json
{
    "payload": {
        "client_id": "0xclient123...",
        "timestamp": 1699999999
    },
    "from": "0xAdminPublicKey",
    "signature": "0xEd25519Signature..."
}
```

**Example super admin request (add admin):**
```json
{
    "payload": {
        "admin_id": "0xnewadmin...",
        "timestamp": 1699999999
    },
    "from": "0xSelfAddress",
    "signature": "0xEd25519Signature..."
}
```

## Policy File Format

Trust policies are markdown files with YAML frontmatter:

```yaml
---
# Who has access
allow:
  - whitelisted    # ~/.co/whitelist.txt
  - contact        # ~/.co/contacts.txt

# Who is blocked
deny:
  - blocked        # ~/.co/blocklist.txt

# How strangers become contacts
onboard:
  invite_code: [CODE1, CODE2]
  payment: 10

# Strangers without credentials
default: deny  # allow | deny | ask
---

# LLM Policy (only used when default: ask)

Evaluate strangers for access...
```

### Evaluation Order

1. Check `deny` list (blocked → reject)
2. Check `allow` list (whitelist/contacts → allow)
3. Try onboarding (invite code or payment → promote to contact)
4. Apply `default` action


## TrustAgent Class

TrustAgent inherits from Agent and provides trust-specific methods.

```python
class TrustAgent(Agent):
    """Agent specialized for trust decisions."""

    def __init__(self, trust: str = "careful", *, api_key: str = None, model: str = "co/gpt-4o-mini"):
        """Create from level ("open", "careful", "strict") or policy path."""

    # === Main Decision ===

    def should_allow(self, client_id: str, request: dict = None) -> Decision:
        """Check if request is allowed. Returns Decision(allow, reason, used_llm)."""

    # === Verification ===

    def verify_invite(self, client_id: str, invite_code: str) -> bool:
        """Verify invite code. Promotes to contact if valid."""

    def verify_payment(self, client_id: str, payment_info: dict) -> bool:
        """Verify payment. Promotes to contact if valid."""

    # === Promotion (earned) ===

    def promote_to_contact(self, client_id: str) -> bool:
        """Stranger → Contact"""

    def promote_to_whitelist(self, client_id: str) -> bool:
        """Contact → Whitelist"""

    # === Demotion ===

    def demote_to_contact(self, client_id: str) -> bool:
        """Whitelist → Contact"""

    def demote_to_stranger(self, client_id: str) -> bool:
        """Contact → Stranger"""

    # === Blocking ===

    def block(self, client_id: str, reason: str) -> bool:
        """Add to blocklist."""

    def unblock(self, client_id: str) -> bool:
        """Remove from blocklist."""

    # === Admin (manual only) ===

    def set_admin(self, client_id: str, by_admin: str) -> bool:
        """Grant admin. Requires existing admin."""

    def remove_admin(self, client_id: str, by_admin: str) -> bool:
        """Revoke admin. Requires existing admin."""

    # === Queries ===

    def get_level(self, client_id: str) -> str:
        """Returns: stranger, contact, whitelist, admin, or blocked."""

    def get_history(self, client_id: str) -> dict:
        """Returns client's request history."""

    def list_clients(self, level: str = None) -> list:
        """List clients, optionally filtered by level."""
```

## Host Uses TrustAgent Directly

```python
# In host.py
from connectonion.network.trust import TrustAgent

# Load trust agent
trust_agent = TrustAgent("careful")

# Admin routes
@app.post("/admin/trust/promote")
def promote(client_id: str):
    level = trust_agent.get_level(client_id)
    if level == "stranger":
        return trust_agent.promote_to_contact(client_id)
    elif level == "contact":
        return trust_agent.promote_to_whitelist(client_id)

# Agent route
@app.post("/input")
def agent_input(client_id: str, request: dict):
    # Check trust first
    decision = trust_agent.should_allow(client_id, request)
    if not decision.allow:
        return {"error": decision.reason}

    # Process with agent
    return agent.input(request["prompt"])
```

## Atomic Functions (Tools)

Trust manager provides simple atomic functions as tools:

```python
# Promotion (earn trust)
def promote_to_contact(client_id: str) -> str:
    """Stranger → Contact"""

def promote_to_whitelist(client_id: str) -> str:
    """Contact → Whitelist"""

# Demotion (lose trust)
def demote_to_contact(client_id: str) -> str:
    """Whitelist → Contact"""

def demote_to_stranger(client_id: str) -> str:
    """Contact → Stranger"""

# Blocking
def block(client_id: str, reason: str) -> str:
    """Add to blocklist."""

def unblock(client_id: str) -> str:
    """Remove from blocklist."""

# Admin (special, manual only)
def set_admin(client_id: str) -> str:
    """Grant admin privileges. Requires existing admin."""

def remove_admin(client_id: str) -> str:
    """Revoke admin privileges. Requires existing admin."""

# Queries
def get_client_level(client_id: str) -> str:
    """Returns: stranger, contact, whitelist, admin, or blocked."""

def get_client_history(client_id: str) -> str:
    """Returns client's request history summary."""
```

### Promotion Chain vs Admin

```
Promotion chain (earned):
Stranger → Contact → Whitelist

Admin (manual only):
set_admin() / remove_admin()
```

Admin is **not** part of the promotion chain. It's a special role granted manually by an existing admin.

## Logic in Markdown

The markdown body defines policy for complex decisions (when `use_agent` triggers):

```markdown
# Trust Agent Policy

You manage client trust levels using these tools:
- `promote_to_contact(client_id)` - Stranger → Contact
- `promote_to_whitelist(client_id)` - Contact → Whitelist
- `block(client_id, reason)` - Block abuser

## When to Promote

Promote stranger to contact when:
- 10+ requests with good behavior
- No suspicious patterns

Promote contact to whitelist when:
- 100+ successful requests
- Consistently valuable interactions

## When to Block

Block immediately if:
- Abuse detected
- Spam patterns
- Attempting to bypass verification
```

The trust agent reads this from `system_prompt` and uses the atomic functions as tools.

## Best Practices

1. **Use fast rules for common cases** - No tokens burned
2. **Reserve trust agent for edge cases** - Saves money
3. **Cache decisions** - Don't re-evaluate every request
4. **Start with "careful"** - Good default for most cases
5. **Use "strict" in production** - Whitelist critical services
6. **Monitor trust decisions** - Log for audit trail

## FAQ

**Q: What's the default trust level?**
A: `"careful"` - verify strangers, allow contacts.

**Q: Do fast rules burn tokens?**
A: No. Fast rules are simple if/then executed by host. Zero tokens.

**Q: When does trust agent run?**
A: Only when `use_agent` triggers fire (e.g., after 10 requests). Rare.

**Q: Where are lists stored?**
A: `~/.co/` - whitelist.txt, contacts.txt, blocklist.txt

**Q: Can I use the same agent with different trust levels?**
A: Yes. Trust is host config, not agent config.

```python
# Same agent, different trust
host(agent, trust="open")    # Dev
host(agent, trust="strict")  # Prod
```

**Q: How do I add custom verification?**
A: Add tools to TrustAgent:

```python
trust = TrustAgent(
    system_prompt="./my_policy.md",
    tools=[my_custom_verifier]
)
```

## TODO

### Prevent Promote Injection During Skill Test

**Problem:** If trust agent has tools like `promote_to_contact()`, during skill testing a malicious agent could trick the trust agent into calling these tools - essentially promoting itself or manipulating access management.

**Security Risk:**
- Skill test evaluates if agent can do what it claims
- Malicious agent could inject prompts to trigger `promote_to_contact()`
- Could bypass normal verification flow

**Possible Solutions:**
1. Separate skill-test mode (no list management tools available)
2. Require confirmation before list changes
3. Sandbox trust agent during skill evaluation
4. Use different trust agent instance for skill tests (read-only)

**Status:** Needs design decision

### WebSocket Protocol for Admin/Onboard

Both HTTP and WebSocket are supported for admin and onboard operations. WebSocket is future-proof for decentralized/P2P scenarios (WebRTC).

**Client → Server Messages:**

| Type | Payload | Who |
|------|---------|-----|
| `INPUT` | `{ prompt, ... }` | Anyone |
| `ONBOARD_SUBMIT` | `{ invite_code }` or `{ payment }` | Stranger |
| `ADMIN_PROMOTE` | `{ client_id }` | Admin |
| `ADMIN_DEMOTE` | `{ client_id }` | Admin |
| `ADMIN_BLOCK` | `{ client_id, reason }` | Admin |
| `ADMIN_UNBLOCK` | `{ client_id }` | Admin |
| `ADMIN_GET_LEVEL` | `{ client_id }` | Admin |
| `ADMIN_ADD` | `{ admin_id }` | Super Admin |
| `ADMIN_REMOVE` | `{ admin_id }` | Super Admin |

**Server → Client Messages:**

| Type | Payload | When |
|------|---------|------|
| `OUTPUT` | `{ result, session_id }` | Agent response |
| `ONBOARD_REQUIRED` | `{ methods, payment_amount? }` | Stranger needs to onboard |
| `ONBOARD_SUCCESS` | `{ identity, level }` | Onboard complete |
| `ADMIN_RESULT` | `{ action, success, message }` | Admin action result |
| `ERROR` | `{ message }` | Any error |

**Example: Stranger connects, onboards, then chats:**

```
Client: { type: 'INPUT', prompt: 'Hello', payload, signature }
Server: { type: 'ONBOARD_REQUIRED', methods: ['invite_code'], identity: '0x...' }
Client: { type: 'ONBOARD_SUBMIT', payload: { invite_code: 'BETA2024' }, signature }
Server: { type: 'ONBOARD_SUCCESS', identity: '0x...', level: 'contact' }
Client: { type: 'INPUT', prompt: 'Hello', payload, signature }
Server: { type: 'OUTPUT', result: 'Hi there!' }
```
