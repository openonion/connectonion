# Agent-to-Agent Authentication: Design Principles

## Core Principle: Authentication IS an Agent

Authentication isn't a protocol - it's just another agent with trust-checking tools.

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

## The Result

When agents need to establish trust, their trust agents simply have a conversation. No special protocols. No complex frameworks. Just agents talking to agents using the same ConnectOnion tools.

Authentication becomes invisible - exactly as it should be.