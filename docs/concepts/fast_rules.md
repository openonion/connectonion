# Fast Rules

Fast rules are code-executed trust checks that run **before** the LLM. They burn zero tokens and are instant.

## Why Fast Rules?

Trust verification that uses an LLM costs tokens. Every verification burns money.

- 1000 requests/day × $0.001/verification = $365/year just for "should I trust this?"
- 90% of trust decisions are mechanical (whitelist check, blocklist check)
- Only 10% need LLM judgment

Fast rules handle the 90%. LLM handles the 10%.

## How It Works

```
Request comes in
       │
       ▼
┌─────────────────┐
│   Fast Rules    │  ← No tokens, instant
│                 │
│ 1. blocked?     │──deny──►
│ 2. whitelisted? │──allow──►
│ 3. contact?     │──allow──►
│ 4. onboard?     │──promote + allow──►
└─────────────────┘
       │
       │ No rule matched
       ▼
┌─────────────────┐
│   Trust Agent   │  ← LLM, burns tokens
│   (if enabled)  │
└─────────────────┘
```

## Policy File Format

Trust policies are markdown files with YAML frontmatter:

```yaml
---
# YAML config (fast rules)
---

# Markdown body (LLM system prompt)
```

### Full Example

```yaml
---
# Who has access
allow:
  - whitelisted
  - contact

# Who is blocked
deny:
  - blocked

# How strangers become contacts (onboarding)
onboard:
  invite_code: [BETA2024, FRIEND123]
  payment: 10

# Strangers without credentials
default: ask  # allow | deny | ask
---

# Careful Trust

You evaluate unknown agents...
```

## Config Options

### `allow:`

Who has access. List of conditions:

```yaml
---
allow:
  - whitelisted  # Users in ~/.co/whitelist.txt
  - contact      # Users in ~/.co/contacts.txt
---
```

### `deny:`

Who is blocked:

```yaml
---
deny:
  - blocked  # Users in ~/.co/blocklist.txt
---
```

### `onboard:`

How strangers become contacts (OR logic):

```yaml
---
onboard:
  invite_code: [CODE1, CODE2]  # Valid invite codes
  payment: 10                   # Minimum payment amount
---
```

- `invite_code`: Client sends `invite_code` in request → becomes contact
- `payment`: Client sends `payment` >= amount → becomes contact

**OR logic**: Either invite_code OR payment passes → promoted to contact.

### `default:`

What to do with strangers who don't onboard:

```yaml
---
default: ask    # Use LLM to decide (careful mode)
# OR
default: deny   # Reject (strict mode)
# OR
default: allow  # Accept (open mode)
---
```

## The Three Presets

### open (Development)

```yaml
---
default: allow
---
```

Everyone allowed. No verification.

### careful (Staging)

```yaml
---
allow:
  - whitelisted
  - contact

deny:
  - blocked

onboard:
  invite_code: [BETA2024]
  payment: 10

default: ask
---
```

Whitelisted and contacts allowed. Strangers can onboard or be evaluated by LLM.

### strict (Production)

```yaml
---
allow:
  - whitelisted

deny:
  - blocked

default: deny
---
```

Whitelist only. Everyone else denied.

## Execution Order

Fast rules execute in this order:

1. Check `deny` list → deny if blocked
2. Check `allow` list → allow if whitelisted/contact
3. Try `onboard` → promote + allow if valid credentials
4. `default` → allow / deny / ask

## List Files

Fast rules read from `~/.co/`:

```
~/.co/
├── whitelist.txt   # Trusted clients
├── contacts.txt    # Verified clients
└── blocklist.txt   # Blocked clients
```

### Format

```
# Comments start with #
client-id-123
another-client

# Wildcards supported
payment-*
*.trusted.com
```

## Implementation

See `connectonion/network/trust/fast_rules.py`:

```python
from connectonion.network.trust import parse_policy, evaluate_request

# Parse policy file
config, markdown_body = parse_policy(policy_text)

# Evaluate request
result = evaluate_request(config, client_id, request)
# Returns: 'allow', 'deny', or None (needs LLM)
```

## Summary

| Feature | Fast Rules | LLM Trust Agent |
|---------|------------|-----------------|
| Tokens | Zero | Burns tokens |
| Speed | Instant | Slow (API call) |
| Logic | Simple checks | Complex reasoning |
| Use | 90% of requests | 10% of requests |
| Config | YAML frontmatter | Markdown body |
