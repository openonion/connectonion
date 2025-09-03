# Naming is Hard: Why We Chose "Address" Over "Identity"

*September 3, 2025*

There's a famous quote in computer science: "There are only two hard things in Computer Science: cache invalidation and naming things." Today, we're talking about the second one.

## The Naming Dilemma

When implementing key generation for ConnectOnion agents, we had a seemingly simple decision: what do we call this thing that uniquely identifies an agent?

Our first draft:
```python
# connectonion/crypto.py
def generate_agent_identity():
    """Generate cryptographic identity for agent."""
    ...
```

It felt sophisticated. Technical. Important. It also felt... wrong.

## The Options We Considered

### Option 1: Identity
```python
identity = generate_agent_identity()
print(f"Agent identity: {identity}")
```

**Pros:**
- Sounds comprehensive
- Technically accurate (it IS an identity)
- Used by many identity systems

**Cons:**
- Abstract and vague
- Makes users think "identity management" (scary!)
- Overloaded term in software

### Option 2: ID
```python
agent_id = generate_agent_id()
print(f"Agent ID: {agent_id}")
```

**Pros:**
- Short and simple
- Familiar from databases

**Cons:**
- Too generic
- Doesn't convey that it's cryptographic
- Confusion with database IDs

### Option 3: Key
```python
agent_key = generate_agent_key()
print(f"Agent key: {agent_key}")
```

**Pros:**
- Technically accurate
- Developers understand keys

**Cons:**
- Which key? Public? Private?
- Sounds like API keys
- Implementation detail, not user concept

### Option 4: Address
```python
address = generate_address()
print(f"Agent address: {address}")
```

**Pros:**
- Immediately understood
- Familiar from email, web, crypto
- Concrete and specific
- Matches user mental model

**Cons:**
- ...actually, none?

## The Winner: Address

We chose "address" because it just makes sense. Everyone understands addresses:
- Email has addresses
- Websites have addresses  
- Ethereum has addresses
- Even physical mail has addresses

When you tell someone "this is your agent's address," they immediately understand it's how others can reach that agent.

## The Ripple Effect

Once we chose "address," everything else fell into place:

```python
# Before (confusing)
from connectonion.crypto import generate_agent_identity
identity = generate_agent_identity()
save_identity(identity)

# After (clear)
from connectonion.address import generate
address = generate()
save(address)
```

The file name became obvious too:
- ❌ `crypto.py` - Scary, too broad
- ❌ `identity.py` - Abstract
- ❌ `keys.py` - Implementation detail
- ✅ `address.py` - Perfect!

## Function Names Got Simpler Too

When the module name provides context, function names can be simpler:

```python
# connectonion/address.py

def generate() -> dict:
    """Generate new agent address."""
    
def recover(seed_phrase: str) -> dict:
    """Recover address from seed phrase."""
    
def save(address_data: dict, path: Path):
    """Save address keys."""
    
def load(path: Path) -> dict:
    """Load address keys."""
    
def verify(address: str, message: bytes, signature: bytes) -> bool:
    """Verify signature from address."""
```

No need to repeat "address" in every function - the module name makes it clear.

## The Lesson: Use Familiar Words

We developers love to invent new terminology. It makes us feel smart. But users don't care about our clever naming - they just want things to make sense.

Consider these transformations:
- "Cryptographic identity" → "Address"
- "Mnemonic seed phrase" → "Recovery phrase"  
- "Ed25519 public key" → "Agent address"
- "Signing key" → "Private key"

The right side is always clearer.

## A Real Conversation

This actual conversation happened during code review:

"What should we call the thing that identifies an agent?"
"What does it do?"
"Other agents use it to send messages to this agent."
"So... an address?"
"Oh. Yeah. An address."

Sometimes the obvious answer is the right answer.

## The Bigger Pattern

This decision reflects a broader pattern in ConnectOnion:

1. **Use existing mental models** - Don't make users learn new concepts
2. **Prefer concrete over abstract** - "Address" not "Identity"
3. **Choose familiar over precise** - "Recovery phrase" not "BIP39 mnemonic"
4. **Name from the user's perspective** - Not from the implementation

## The Implementation

Here's what we ended up with:

```python
from connectonion import address

# Generate new agent (simple!)
my_address = address.generate()
print(f"Agent address: {my_address['address']}")

# Save it (obvious!)
address.save(my_address, Path(".co"))

# Load it later (clear!)
my_address = address.load(Path(".co"))
```

No confusion. No abstraction. Just addresses.

## Counter-Examples: When We Got It Wrong

We're not perfect. Here are times we chose poorly:

**Bad:** `llm_do()` - What does "do" mean?
**Better:** `llm_function()` or `llm_tool()`

**Bad:** `co init` - Init what?
**Better:** Could have been `co create` or `co new`

We keep these as reminders that naming is hard, and we don't always get it right the first time.

## The Test: Explain It To Someone

The ultimate test for naming: explain it to someone unfamiliar with your project.

"Your agent has an address. Other agents use it to send messages."

vs

"Your agent has a cryptographic identity derived from an Ed25519 keypair that serves as a unique identifier in the network protocol."

Which would you rather hear?

## Conclusion

Good naming isn't about being clever or technically precise. It's about being clear. When in doubt, choose the boring, familiar word that everyone already understands.

That's why every ConnectOnion agent has an address, not an identity. It's why you have a recovery phrase, not a mnemonic seed. It's why you run `co init`, not `co scaffold-project-structure`.

Keep it simple. Use words people know. Save the cleverness for the implementation, not the interface.

---

*P.S. We spent 30 minutes debating "address" vs "identity". Those 30 minutes were worth it. Good naming pays dividends forever.*