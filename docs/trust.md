# Trust in ConnectOnion

The `trust` parameter provides flexible, bidirectional trust configuration for agent interactions.

## Quick Start

```python
from connectonion import Agent, need

# Simple trust levels
translator = need("translate", trust="strict")   # Production: verified only
analyzer = need("analyze", trust="tested")       # Default: test first
scraper = need("scrape", trust="open")          # Development: trust all

# For your own agent
agent = Agent(
    name="my_service",
    tools=[process_data],
    trust="strict"  # Who can use my services
)
```

## Three Forms of Trust

### 1. Trust Levels (String)

Simple predefined levels for common scenarios:

```python
# Development - trust everyone
agent = need("service", trust="open")

# Default - test before trusting
agent = need("service", trust="tested")

# Production - only verified/whitelisted
agent = need("service", trust="strict")
```

### 2. Trust Policy (Natural Language)

Express complex requirements in plain English:

```python
# Inline policy
translator = need("translate", trust="""
    I trust agents that:
    - Pass capability tests
    - Respond within 500ms
    - Are on my whitelist OR from local network
""")

# From file
translator = need("translate", trust="./trust_policy.md")
```

Example trust policy file:
```markdown
# My Trust Requirements

I trust agents that meet ALL of these criteria:
- Successfully translate "Hello" to "Hola"
- Respond in less than 1 second
- Have processed at least 10 requests successfully

I immediately reject agents that:
- Fail basic capability tests
- Take longer than 5 seconds
- Are on my blacklist
```

### 3. Trust Agent

For maximum control, use a custom trust agent:

```python
# Create a trust agent with verification tools
trust_agent = Agent(
    name="my_guardian",
    tools=[
        check_whitelist,
        verify_capability,
        measure_response_time,
        check_reputation
    ],
    system_prompt="""
        You verify other agents before allowing interaction.
        Be strict with payment processors, relaxed with read-only services.
    """
)

# Use it for your agent
my_agent = Agent(
    name="my_service",
    tools=[process_payment],
    trust=trust_agent  # My guardian protects me
)

# And for discovering services
payment = need("payment processor", trust=trust_agent)
```

## Bidirectional Trust

The same `trust` parameter works in both directions:

```python
# As a SERVICE provider (who can use me?)
alice_agent = Agent(
    name="alice_translator",
    tools=[translate],
    trust="tested"  # Users must pass my tests
)

# As a SERVICE consumer (who do I trust?)
translator = need("translate", trust="strict")  # I only use verified services

# Both trust requirements must be satisfied for interaction!
```

## Trust Flow Example

```python
# Alice creates a translation service
alice = Agent(
    name="alice_translator",
    tools=[translate],
    trust="tested"  # Test users before serving them
)
share(alice)

# Bob looks for a translator
translator = need(
    "translate to Spanish",
    trust="strict"  # Bob only uses verified services
)

# What happens:
# 1. Bob's trust agent evaluates Alice (strict check)
# 2. Alice's trust agent evaluates Bob (test required)
# 3. Both must approve for connection to succeed
```

## Environment-Based Defaults

ConnectOnion automatically adjusts trust based on environment:

```python
# No trust parameter needed - auto-detected!
translator = need("translate")

# In development (localhost, Jupyter)
# → Defaults to trust="open"

# In test files (test_*.py)
# → Defaults to trust="tested"

# In production
# → Defaults to trust="strict"

# Override when needed
translator = need("translate", trust="open")  # Force open even in production
```

## Trust Functions

Trust agents use composable functions:

```python
# Basic trust functions (provided by ConnectOnion)
def check_whitelist(agent_id: str) -> bool:
    """Check if agent is whitelisted"""
    
def test_capability(agent, test_input, expected) -> bool:
    """Test if agent produces expected output"""
    
def measure_response_time(agent, timeout_ms) -> float:
    """Measure agent response time"""
    
def check_local_network(agent_ip: str) -> bool:
    """Check if agent is on local network"""

# Combine in your trust agent
my_trust = Agent(
    name="guardian",
    tools=[
        check_whitelist,
        test_capability,
        measure_response_time,
        check_local_network
    ]
)
```

## Whitelist Management

Simple text file at `~/.connectonion/trusted.txt`:

```
translator.api.com
analyzer.local
my-company.internal.net
192.168.1.*
```

Edit with any text editor or programmatically:

```python
# Add to whitelist
with open("~/.connectonion/trusted.txt", "a") as f:
    f.write("new-service.com\n")
```

## Progressive Trust Building

Trust grows through successful interactions:

```python
# First encounter - requires testing
translator = need("translate", trust="tested")
# → Agent is tested before use

# After successful interactions
# → Agent automatically added to "verified" list

# Future encounters
translator = need("translate", trust="tested")
# → Skip testing, already verified
```

## Common Patterns

### Development Mode
```python
# Trust everyone for rapid development
connectonion.set_default_trust("open")
```

### Production Mode
```python
# Strict verification for production
payment = need("payment processor", trust="strict")
sensitive = need("data processor", trust="strict")
```

### Mixed Trust
```python
# Different trust for different services
scraper = need("web scraper", trust="open")      # Low risk
analyzer = need("analyze data", trust="tested")   # Medium risk
payment = need("process payment", trust="strict") # High risk
```

### Custom Trust Logic
```python
# Trust based on context
def get_trust_level(service_type):
    if "payment" in service_type:
        return "strict"
    elif "read" in service_type:
        return "open"
    else:
        return "tested"

service = need("read data", trust=get_trust_level("read data"))
```

## Security Best Practices

1. **Production = Strict**: Always use `trust="strict"` in production
2. **Test Sensitive Operations**: Payment, data modification, etc.
3. **Whitelist Critical Services**: Manually verify and whitelist
4. **Monitor Trust Decisions**: Log all trust evaluations
5. **Regular Audits**: Review whitelist and trust policies

## FAQ

**Q: What's the default trust level?**
A: `"tested"` - agents are tested before first use

**Q: Can I change trust after agent creation?**
A: Yes: `agent.trust = new_trust_agent`

**Q: How do trust agents communicate?**
A: They're regular ConnectOnion agents - they talk naturally

**Q: What if both agents have strict trust?**
A: Both requirements must be met - most restrictive wins

**Q: Can I disable trust completely?**
A: Yes: `trust="open"` accepts everyone without checks