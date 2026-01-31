# Why We Chose "Trust" - The Story Behind ConnectOnion's Authentication Keyword

*December 2024*

When designing ConnectOnion's agent-to-agent authentication system, we faced a crucial decision: what should we call the parameter that controls how agents verify each other? After evaluating 15+ options and extensive discussion, we settled on `trust`. Here's why.

## The Challenge: Finding a Bidirectional Word

Our authentication system needed a keyword that works in two directions:
1. **As a service provider**: "Who can use my services?"
2. **As a service consumer**: "Which services do I trust?"

Most security terms only work in one direction. We needed something that naturally flows both ways.

## Options We Considered

### 1. `auth` / `authentication`
**Why not**: Too technical and implies traditional authentication (passwords, tokens). We're doing behavioral verification, not credential checking.

### 2. `verify` / `validate`
**Why not**: One-directional - you verify others, but saying "I'm verified" sounds like a credential system.

### 3. `guard` / `guardian`
**Why not**: Implies blocking/protection only. Doesn't capture the mutual relationship between agents.

### 4. `policy` / `rules`
**Why not**: Too formal and configuration-heavy. Doesn't match our natural language approach.

### 5. `security` / `safe`
**Why not**: Too broad and creates fear. Security implies threats; we want collaboration.

### 6. `filter` / `allow`
**Why not**: One-directional and negative. Focuses on exclusion rather than building relationships.

### 7. `mode` / `env`
**Why not**: Too generic. Could mean anything - doesn't clearly indicate authentication purpose.

### 8. `strict` / `open` / `tested`
**Why not**: These became our trust *levels*, but the parameter itself needed a clearer name.

### 9. `require` / `expect`
**Why not**: Works for incoming but awkward for outgoing ("I require others" vs "I'm required"?).

### 10. `proof` / `prove`
**Why not**: Implies formal verification. We do behavioral testing, not mathematical proofs.

## Why "Trust" Won

### 1. Naturally Bidirectional
```python
# Both directions feel natural
agent = Agent(name="my_service", trust="strict")  # I trust strict agents
service = need("translator", trust="tested")      # I need tested services
```

The word "trust" flows both ways without awkwardness.

### 2. Human-Friendly
Developers immediately understand trust. It's how we think about relationships:
- "I trust this service"
- "This service trusts me"
- "We need to build trust"

### 3. Progressive, Not Binary
Trust isn't yes/no - it grows through interaction:
```python
trust="open"    # Trust everyone (dev mode)
trust="tested"  # Test first, then trust
trust="strict"  # Only trusted partners
```

### 4. Matches Real Behavior
We're not checking passwords or certificates. We're testing behavior:
- Can you translate "Hello" to "Hola"?
- Do you respond within 500ms?
- Have we worked together successfully before?

This is trust-building, not authentication.

### 5. Enables Natural Language Config
```python
trust = """
I trust agents that:
- Pass my capability tests
- Respond quickly
- Have good track record
"""
```

"Trust policy" sounds natural. "Authentication policy" sounds bureaucratic.

## The Unix Philosophy Connection

Following Unix principles, trust isn't a complex protocol - it's simple functions composed by prompts:

```python
# Small, composable trust functions
def check_whitelist(agent_id): ...
def test_capability(agent, test): ...
def measure_response_time(agent): ...

# Composed into trust agents
trust_agent = Agent(
    name="my_guardian",
    tools=[check_whitelist, test_capability, measure_response_time]
)
```

## Some Challenges with "Trust"

We acknowledge potential confusion:

1. **Overloaded Term**: "Trust" appears in many contexts (TLS, trust stores, web of trust)
2. **Seems Soft**: Some developers might prefer "harder" security terms
3. **Cultural Variations**: Trust has different connotations across cultures

But these are outweighed by its clarity and naturalness for our use case.

## The Final Design

```python
# Three forms, one keyword
translator = need("translate", trust="strict")           # Simple level
translator = need("translate", trust="./trust.md")       # Natural language
translator = need("translate", trust=my_trust_agent)     # Custom agent

# Bidirectional by default
alice = Agent(name="alice", trust="tested")  # Alice tests her users
bob_needs = need("service", trust="strict")  # Bob only uses strict services
# Both must approve for connection!
```

## Conclusion

`trust` won because it's the most honest description of what we're doing. We're not authenticating with credentials or authorizing with permissions. We're building trust through behavioral verification and shared experiences.

In ConnectOnion, agents don't authenticate - they trust. And that makes all the difference.

---

*This design decision exemplifies ConnectOnion's philosophy: make simple things simple, make complicated things possible. Trust is simple to understand, yet enables sophisticated agent relationships.*