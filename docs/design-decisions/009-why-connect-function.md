# Why We Chose `connect()` for Remote Agents

*The journey to finding the right interface for connecting to remote agents*

## The Problem

When developers want to use a remote AI agent, they need a simple, intuitive way to establish that connection. The challenge was finding the right verb that:
- Clearly indicates remote interaction
- Returns an object to interact with
- Feels familiar to developers
- Distinguishes from local agent creation

## What We Considered

### Option 1: `RemoteAgent()` Class
```python
translator = RemoteAgent("0x3d40...")
```
✅ Crystal clear it's remote
❌ Verbose (11 extra characters)
❌ Exposes implementation details

### Option 2: `client()` Function
```python
translator = client("0x3d40...")
```
✅ Follows database patterns (MongoClient, RedisClient)
❌ It's a noun, not a verb - feels awkward
❌ Implies client/server architecture

### Option 3: `get()` Function
```python
translator = get("0x3d40...")
```
✅ Shortest (3 characters)
✅ Familiar from REST APIs
❌ Too generic - get what exactly?

### Option 4: `use()` Function
```python
translator = use("0x3d40...")
```
✅ Natural language
✅ Very short
❌ Too vague about what's happening

### Option 5: `reach()` Function
```python
translator = reach("0x3d40...")
```
✅ Implies remote interaction
✅ Natural English
❌ Unfamiliar pattern in programming

## Why `connect()` Won

```python
from connectonion import connect

translator = connect("0x3d40...")
result = translator.input("Translate hello")
```

### 1. Familiar Pattern
Developers already use `connect()` everywhere:
```python
# Databases
db = psycopg2.connect("postgresql://...")
redis = redis.connect("redis://...")

# Our pattern
agent = connect("0x3d40...")
```

### 2. Clear Semantics
The word "connect" immediately tells developers:
- This is a network operation
- You're establishing a connection to something remote
- It returns something you can interact with

### 3. No Confusion with Local Agents
```python
# Creating local agent - uses class
my_agent = Agent("translator", tools=[...])

# Connecting to remote - uses function
their_agent = connect("0x3d40...")
```

Clear distinction: `Agent` class for creation, `connect` function for remote access.

### 4. Verb Returns Noun
`connect()` is a verb that returns a connection object - this is a natural pattern:
- The action (connect) returns the result (connected agent interface)
- You connect and get back something to use
- No ambiguity about what you're getting

### 5. Handles Everything Automatically
When you call `connect()`, the framework:
1. Connects to relay at `wss://oo.openonion.ai`
2. Queries agent information
3. Attempts direct TCP connection
4. Falls back to relay if needed
5. Returns ready-to-use interface

The developer doesn't see this complexity - they just get a working agent.

## The Developer Experience

### Simple and Natural
```python
# The thought process
"I need to use that translator agent"
"I'll connect to it"
"Now I can use it"

# The code matches the thought
translator = connect("0x3d40...")
result = translator.input("Translate this")
```

### Extensible
```python
# Basic usage
agent = connect("0x3d40...")

# Future extensions feel natural
agent = connect(find="translator")
agent = connect(need="something that translates")
```

### Clear Error Messages
```python
# If connection fails
"Failed to connect to agent at 0x3d40..."
# Immediately understandable
```

## What `connect()` Returns

The `connect()` function returns a limited interface - not the full agent:

```python
class ConnectedAgent:
    def input(self, prompt: str) -> str:
        """Send input to remote agent"""

    @property
    def address(self) -> str:
        """The agent's address"""

    def is_online(self) -> bool:
        """Check if agent is reachable"""
```

This makes it clear you're working with a remote interface, not the agent itself.

## Conclusion

`connect()` strikes the perfect balance:
- **Familiar**: Developers know this pattern from databases
- **Clear**: Obviously a network operation
- **Simple**: Just 7 characters
- **Accurate**: You're connecting to get an interface
- **Extensible**: Can grow with the framework

The choice of `connect()` makes ConnectOnion feel instantly familiar while accurately representing what's happening under the hood.