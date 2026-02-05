# Trust Policy System Design: Two-Tier Verification

*February 2025*

After designing the high-level trust architecture (see [020-trust-system-and-network-architecture.md](020-trust-system-and-network-architecture.md)), we needed to answer a harder question: how do we verify requests without burning tokens on every single one?

---

## The Token Problem

Trust verification that uses an LLM costs tokens. Every verification burns money.

A popular agent receives 1000 requests/day. If each verification costs $0.001 on average, that's $1/day just for trust decisions. $365/year spent on "should I trust this?" instead of doing actual work.

Most verifications are trivial. "Is this client on the whitelist?" doesn't need LLM reasoning. "Does this client have a valid invite code?" is a simple lookup.

90% of trust decisions are mechanical. Only 10% need judgment.

---

## Two-Tier Verification

We split trust into two layers:

```
┌─────────────────────────────────────────────────────┐
│  FAST RULES (no tokens, instant)                    │
│                                                     │
│  - Whitelist check                                  │
│  - Blocklist check                                  │
│  - Invite code verification                         │
│  - Payment verification                             │
│  - Client level checks (stranger, contact, etc.)   │
│                                                     │
│  90% of requests resolved here                      │
└─────────────────────────────────────────────────────┘
                      │
                      │ Only when fast rules can't decide
                      ▼
┌─────────────────────────────────────────────────────┐
│  TRUST AGENT (LLM, burns tokens, rare)              │
│                                                     │
│  - Behavior analysis                                │
│  - Complex promotion decisions                      │
│  - Edge cases                                       │
│                                                     │
│  10% of requests (at most)                          │
└─────────────────────────────────────────────────────┘
```

Fast rules handle common cases. LLM handles complex ones. Most requests never reach the LLM.

### Alternatives We Rejected

**All LLM** - every request goes through trust agent:
- Expensive ($365+/year for active agents)
- Slow (LLM latency on every request)
- Overkill for trivial decisions

**All Code** - hardcoded rules only:
- Inflexible (can't handle edge cases)
- Brittle (every scenario needs explicit code)
- No judgment for nuanced decisions

Two tiers gives us cost efficiency (90% free), speed (instant for common cases), flexibility (LLM for edge cases), and progressive complexity.

---

## Client States

We needed a clear model for how trust evolves:

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

### Why Admin Is Separate

Early design had `promote_to_admin()` as part of the chain. Wrong for several reasons:

1. **Different nature**: Admin is about authority, not trust level. A contact can be admin. A whitelist member might not be.

2. **Security**: Auto-promotion to admin is dangerous. Admin should be a deliberate, manual decision.

3. **Audit trail**: Admin changes need explicit `by_admin` tracking. Who granted it? Who revoked it?

4. **Simplicity**: Keeping admin separate makes the promotion chain cleaner.

### The Atomic Functions

Instead of generic `promote()` and `demote()`, we use explicit atomic functions:

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

`promote_to_contact()` is clearer than `promote(client_id, level="contact")`. No ambiguity. No wrong level. Self-documenting.

These functions serve as tools for both host (direct calls for fast rule actions) and trust agent (LLM calls for complex decisions).

---

## YAML + Markdown Format

Trust policies need two things:
1. Configuration for fast rules (structured, machine-readable)
2. Instructions for trust agent (natural language, LLM-readable)

We chose YAML frontmatter for config, Markdown body for instructions.

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

### Why YAML Frontmatter

**Separate config file** (`careful.yaml` + `careful.md`): Two files to maintain, easy to get out of sync.

**JSON in markdown**: Awkward to edit, syntax highlighting breaks.

**Pure YAML file** with policy as multi-line string: Ugly, no markdown preview, harder to write prose.

YAML frontmatter won: single file, standard format (Jekyll, Hugo, Obsidian all use it), editors understand it, clear separation between config and prose.

### Fast Rules Structure

We iterated on the syntax. First version had separate `verify:` and `fast_rules:` sections—confusing overlap, unclear precedence.

Final version: everything under `fast_rules:`. Single place for all rules, order determines precedence.

```yaml
fast_rules:
  - if: has_invite_code
    action: verify_invite
    on_success: promote_to_contact
  - if: is_stranger
    action: deny
```

---

## TrustAgent Design

### Why Inherit from Agent

Should TrustAgent be a separate class or inherit from Agent?

**Separate interface** (`TrustVerifier` Protocol): New abstraction to learn, can't reuse Agent features (tools, LLM, events), inconsistent with framework.

**Inherit from Agent**: Consistent with framework, all Agent features available, same API users already know.

```python
class TrustAgent(Agent):
    # Inherits: system_prompt, tools, input(), etc.
    # Adds: should_allow(), verify_invite(), etc.
```

We went with inheritance.

### No Formal Interface

No formal Protocol/ABC. TrustAgent is just an Agent with specific methods.

Python isn't Java—duck typing is idiomatic. If it has `should_allow()`, it's a trust agent. There's only one implementation, so no need to abstract. "TrustAgent inherits from Agent" is clearer than "TrustAgent implements ITrustVerifier which extends Protocol..."

YAGNI. We can add an interface later if we need it.

### Config vs system_prompt

Early design: `TrustAgent(config="prompts/trust/careful.md")`

We changed to: `TrustAgent(system_prompt="prompts/trust/careful.md")`

Every Agent has `system_prompt`. TrustAgent is an Agent. Therefore TrustAgent uses `system_prompt`. The YAML frontmatter is parsed internally and stored as `self.trust_config`, but externally it looks like a normal Agent.

---

## Fixed Routes in Host

### The Dynamic Routes Problem

Early design: trust agent dynamically registers routes based on policy. Policy enables `verify_invite` → route appears. Policy disables it → route disappears.

Problems: unpredictable (which routes exist depends on policy), documentation nightmare, client confusion (consumers don't know what endpoints to call).

### Fixed Routes Solution

Host provides fixed routes. Policy enables/disables behavior, not existence.

```python
# Always exist:
/trust/verify/invite     # If disabled → returns clear error
/trust/verify/payment
/trust/promote
/trust/demote
/trust/block
/trust/admin/set
/trust/admin/remove
/input
```

Same routes always exist. One set to document. Clients know what's available. No route registration logic.

---

## Security Considerations

### Promote Injection

TrustAgent has `promote_to_contact()` as a tool. During skill testing, a malicious agent could craft prompts to trick the trust agent into calling it—promoting itself, bypassing verification.

Possible solutions (needs design decision):
1. Skill-test mode with no list management tools
2. Human confirmation for list changes
3. Read-only trust agent instance for skill tests
4. All promotions logged, easy to review/revert

Open TODO. The design acknowledges the risk.

### Why We Accept This Risk (For Now)

Trust agent having tools is the right design. The injection risk is edge-case. Unexpected promotions are auditable and revertable. By documenting it, we ensure it's not forgotten.

---

## Principles

**Simple things simple**: `host(agent, trust="careful")` just works. Full control when needed: `host(agent, trust=custom_trust_agent)`.

**Progressive disclosure**: Level 0 (`host(agent)`) → Level 1 (`trust="strict"`) → Level 2 (`trust="./my_policy.md"`) → Level 3 (`trust=TrustAgent(...)`). Users at level 0 don't see levels 1-3.

**Behavior over identity**: Trust levels (stranger, contact, whitelist) are earned through behavior, not granted through identity. Admin is the exception—identity matters (which existing admin granted it).

**Explicit over implicit**: `promote_to_contact()` not `promote(level="contact")`. `set_admin(by_admin="...")` not `set_admin()`. `verify_invite` in YAML, not automatic route detection.

---

## Summary

| Decision | Choice | Why |
|----------|--------|-----|
| Verification approach | Two-tier (fast rules + LLM) | 90% free, 10% smart |
| Policy format | YAML frontmatter + Markdown | One file, clear separation |
| Client states | Stranger → Contact → Whitelist (Admin separate) | Clear progression, admin is special |
| Functions | Atomic (promote_to_contact, not promote) | Self-documenting, no ambiguity |
| TrustAgent | Inherits from Agent | Consistent API, reuse features |
| Interface | No formal Protocol | YAGNI, duck typing is fine |
| Routes | Fixed in host | Predictable, documentable |
| Config parameter | system_prompt (not config) | Consistent with Agent |

The system balances cost (fast rules are free), flexibility (LLM for edge cases), simplicity (presets for common cases), and power (custom agents for advanced users).
