# Hook System Design Options

Four different API styles for hooks in ConnectOnion.

---

## Option 1: TypedDict Hooks

```python
from connectonion import Agent, HookEvents

def log_tokens(data):
    print(f"Tokens: {data['usage']['total_tokens']}")

def add_timestamp(data):
    from datetime import datetime
    data['messages'].append({
        'role': 'system',
        'content': f'Current time: {datetime.now()}'
    })
    return data

def cache_results(data):
    cache[data['tool_name']] = data['result']
    return data

agent = Agent(
    "assistant",
    tools=[search, analyze],

    # ✨ TypedDict provides IDE autocomplete + type checking
    on_event=dict(
        before_llm=[add_timestamp],
        after_llm=[log_tokens],
        after_tool=[cache_results],
    )
)

agent.input("Find Python info")
```

**Type Definition (in connectonion):**
```python
from typing import TypedDict, List, Callable

class HookEvents(TypedDict, total=False):
    """Type-safe hook event configuration.

    IDE will autocomplete event names and type checker will validate.
    All fields are optional - only specify the events you need.
    """
    before_llm: List[Callable]
    after_llm: List[Callable]
    before_tool: List[Callable]
    after_tool: List[Callable]
    on_error: List[Callable]
```

**With Type Annotation (for IDE hints):**
```python
# Option A: Inline annotation
on_event: HookEvents = dict(
    before_llm=[add_timestamp],
    after_llm=[log_tokens]  # ← IDE autocompletes event names!
)

# Option B: Without annotation (still works, less IDE help)
on_event=dict(
    before_llm=[add_timestamp],
    after_llm=[log_tokens]
)

agent = Agent("assistant", tools=[search], on_event=on_event)
```

**Reusable across agents:**
```python
from connectonion import HookEvents

common_hooks: HookEvents = dict(
    after_llm=[log_tokens],
    after_tool=[cache_results],
)

agent1 = Agent("assistant", tools=[search], on_event=common_hooks)
agent2 = Agent("analyst", tools=[analyze], on_event=common_hooks)
```

---

## Option 2: Event Wrappers

```python
from connectonion import Agent, before_llm, after_llm, after_tool

def log_tokens(data):
    print(f"Tokens: {data['usage']['total_tokens']}")

def add_timestamp(agent):
    from datetime import datetime
    agent.messages 
    data['messages'].append({
        'role': 'system',
        'content': f'Current time: {datetime.now()}'
    })
   

def cache_results(data):
    cache[data['tool_name']] = data['result']
    return data

agent = Agent(
    "assistant",
    tools=[search, analyze],
    hooks=[
        before_llm(add_timestamp),
        after_llm(log_tokens),
        after_tool(cache_results),
    ]
)

agent.input("Find Python info")
```

**With lambdas:**
```python
from connectonion import Agent, after_llm, after_tool

agent = Agent(
    "assistant",
    tools=[search],
    on_event=[
        after_llm(lambda d: print(f"Tokens: {d['usage']['total_tokens']}")),
        after_tool(lambda d: cache.set(d['tool_name'], d['result'])),
    ]
)
```

**Import and use patterns:**
```python
# connectonion/thinking.py
from connectonion import after_tool

def chain_of_thought():
    def hook(data, agent):
        thinking = agent.llm.complete([...])
        agent.current_session['messages'].append({'role': 'assistant', 'content': thinking})
    return after_tool(hook)

# User code
from connectonion import Agent
from connectonion.thinking import chain_of_thought

agent = Agent("assistant", tools=[search], on_event=[
    chain_of_thought()  # Just import and use!
])
```

---

## Option 3: Decorator Pattern

```python
from connectonion import Agent, hook

@hook('before_llm')
def add_timestamp(data):
    from datetime import datetime
    data['messages'].append({
        'role': 'system',
        'content': f'Current time: {datetime.now()}'
    })
    return data

@hook('after_llm')
def log_tokens(data):
    print(f"Tokens: {data['usage']['total_tokens']}")

@hook('after_tool')
def cache_results(data):
    cache[data['tool_name']] = data['result']
    return data

# Pass decorated hooks to agent
agent = Agent(
    "assistant",
    tools=[search, analyze],
    hooks=[add_timestamp, log_tokens, cache_results]  # Decorated functions
)

agent.input("Find Python info")
```

**Reusable module:**
```python
# hooks.py
from connectonion import hook

@hook('before_llm')
def add_timestamp(data):
    from datetime import datetime
    data['messages'].append({'role': 'system', 'content': f'{datetime.now()}'})
    return data

@hook('after_llm')
def log_tokens(data):
    print(f"Tokens: {data['usage']['total_tokens']}")

# main.py
from connectonion import Agent
from .hooks import add_timestamp, log_tokens

agent = Agent(
    "assistant",
    tools=[search],
    hooks=[add_timestamp, log_tokens]  # Import and pass decorated hooks
)
```

---

## Option 4: Event Emitter

```python
from connectonion import Agent

agent = Agent("assistant", tools=[search])

# Simple lambda
agent.on('after_llm', lambda d: print(f"Tokens: {d['usage']['total_tokens']}"))

# Decorator syntax
@agent.on('before_llm')
def add_timestamp(data):
    from datetime import datetime
    data['messages'].append({
        'role': 'system',
        'content': f'Current time: {datetime.now()}'
    })
    return data

@agent.on('after_tool')
def cache_results(data):
    cache[data['tool_name']] = data['result']
    return data

agent.input("Find Python info")
```

**Dynamic add/remove:**
```python
agent = Agent("assistant", tools=[search])

# Add hook
agent.on('after_llm', log_tokens)

# Later... remove hook
agent.off('after_llm', log_tokens)
```

---

## Common Use Cases

### Cost Tracking

```python
# Option 1: TypedDict
from connectonion import Agent, HookEvents

agent = Agent(
    "assistant",
    tools=[search],
    on_event=dict(
        after_llm=[lambda d: print(f"Cost: ${d['usage']['total_tokens'] * 0.00001:.4f}")]
    )
)

# Option 2: Event Wrappers
from connectonion import after_llm
agent = Agent("assistant", tools=[search], on_event=[
    after_llm(lambda d: print(f"Cost: ${d['usage']['total_tokens'] * 0.00001:.4f}"))
])

# Option 3: Decorator
@hook('after_llm')
def track_cost(data):
    print(f"Cost: ${data['usage']['total_tokens'] * 0.00001:.4f}")

# Option 4: Event Emitter
agent.on('after_llm', lambda d: print(f"Cost: ${d['usage']['total_tokens'] * 0.00001:.4f}"))
```

### Smart Caching

```python
cache = {}

def cache_tool(data):
    key = f"{data['tool_name']}:{hash(str(data['tool_args']))}"
    cache[key] = data['result']
    return data

# Option 1: TypedDict
agent = Agent("assistant", tools=[search], on_event=dict(after_tool=[cache_tool]))

# Option 2: Event Wrappers
agent = Agent("assistant", tools=[search], on_event=[after_tool(cache_tool)])

# Option 3: Decorator
@hook('after_tool')
def cache_tool(data): ...

# Option 4: Event Emitter
agent.on('after_tool', cache_tool)
```

### Custom Logging

```python
# Option 1: TypedDict
agent = Agent(
    "assistant",
    tools=[search],
    on_event=dict(
        before_tool=[lambda d: logger.info(f"Tool: {d['tool_name']}")],
        on_error=[lambda d: logger.error(f"Error: {d['error']}")]
    )
)

# Option 2: Event Wrappers
from connectonion import before_tool, on_error
agent = Agent("assistant", tools=[search], on_event=[
    before_tool(lambda d: logger.info(f"Tool: {d['tool_name']}")),
    on_error(lambda d: logger.error(f"Error: {d['error']}"))
])

# Option 3: Decorator
@hook('before_tool')
def log_tool(data):
    logger.info(f"Tool: {data['tool_name']}")

@hook('on_error')
def log_error(data):
    logger.error(f"Error: {data['error']}")

# Option 4: Event Emitter
agent.on('before_tool', lambda d: logger.info(f"Tool: {d['tool_name']}"))
agent.on('on_error', lambda d: logger.error(f"Error: {d['error']}"))
```

---

## Vote

Which option do you prefer?

👉 https://github.com/openonion/connectonion/issues/31
