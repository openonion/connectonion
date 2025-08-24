# Agent-to-Agent Trust: Design Principles

## Core Principle: Trust IS an Agent

Trust isn't a protocol - it's just another agent with trust-checking tools.

## Five Guiding Principles

### 1. Trust Through Behavior, Not Credentials

Agents prove themselves by what they DO, not what they CLAIM:
- Pass capability tests (Can you translate "Hello" to "Hola"?)
- Demonstrate consistent performance
- Build trust through successful interactions

No certificates. No signatures. Just observable behavior.

### 2. Unix Philosophy: Small Functions, Composed by Prompts

Each trust function does ONE thing:
- `check_whitelist()` - 5 lines
- `test_capability()` - 10 lines  
- `measure_response_time()` - 10 lines

The agent's prompt combines these into trust strategies. Complexity emerges from composition, not from complicated functions.

### 3. Natural Language Configuration

Trust requirements are markdown prompts, not JSON schemas:

```
I trust agents that:
- Respond within 500ms
- Pass my capability tests
- Are on my whitelist OR from local network
```

Both humans and AI understand this. No documentation needed.

### 4. Local Experience Over Global Reputation

Every agent maintains its OWN trust perspective:
- My experience: 100% weight
- Friend's experience: 30% weight
- Global reputation: 0% weight

This prevents reputation manipulation and respects agent autonomy.

### 5. Progressive Trust, Not Binary

Trust levels grow through interaction:
- Discovered → Tested → Verified → Trusted → Partner

Start with synthetic tests, build to production use. Trust degrades through failures, grows through success.

## Implementation: The `trust` Parameter

The `trust` parameter provides flexible trust configuration for both serving and consuming agents:

### Three Forms of Trust

1. **Trust Level (String)** - Simple predefined levels
   - `"open"` - Trust everyone (development)
   - `"tested"` - Test before trusting (default)
   - `"strict"` - Only verified/whitelisted agents (production)

2. **Trust Policy (Prompt)** - Natural language requirements
   ```python
   trust = """
   I trust agents that:
   - Pass capability tests
   - Respond within 500ms
   - Are on my whitelist OR from local network
   """
   ```

3. **Trust Agent** - Custom agent with trust tools
   ```python
   trust_agent = Agent("guardian", tools=[verify, check_whitelist])
   agent = Agent("my_bot", trust=trust_agent)
   ```

### Bidirectional Trust

The same `trust` parameter works for both:
- **As Server**: `Agent("my_service", tools=[...], trust="strict")` - Who can use me
- **As Client**: `need("service", trust="strict")` - Who I trust to use

## The Result

When agents need to establish trust, their trust agents simply have a conversation. No special protocols. No complex frameworks. Just agents talking to agents using the same ConnectOnion tools.

Trust becomes invisible - exactly as it should be.