# Trust Memory

Remember agents that worked well for you.

## Overview

After successfully using an agent, remember it. Next time you need the same thing, use the same agent. That's it.

## Usage

```python
# First time - discovers new agent
translator = need("translate to Spanish")
result = translator("Hello")  # "Hola"

# Next time - returns same agent
translator = need("translate to Spanish")  
# Automatically returns the one that worked
```

## What Gets Recorded

Just two things:
```python
{
    "translator": "worked",
    "analyzer": "worked",
    "processor": "didn't work"
}
```

That's literally it.

## How It Works

```python
def need(description):
    # Check if you've used something similar before
    if previous := find_in_memory(description):
        if previous.worked:
            return previous
    
    # Otherwise discover new
    return discover(description)
```

## Examples

### Building Trust
```python
# Monday
summarizer = need("summarize text")  # Finds new
summary = summarizer(article)  # Works well
# Remembers: "summarizer" → "worked"

# Tuesday  
summarizer = need("summarize text")  # Returns same one
# No discovery needed
```

### Avoiding Bad Agents
```python
# Try an agent
processor = need("process data")
result = processor(data)  # Fails or poor quality
# Remembers: "processor" → "didn't work"

# Next time
processor = need("process data")
# Finds a different one
```

## Simple Management

```python
# See what worked
my_memory()
"""
✓ translator - worked
✓ summarizer - worked  
✗ processor - didn't work
✓ analyzer - worked
"""

# Forget old memories
forget_old()  # Clears entries older than 30 days

# Start fresh
reset_memory()  # Clear everything
```

## Privacy

- Only stores: agent ID + worked/didn't work
- No data about what you processed
- No tracking of when/how often
- Just: "I used X and it worked"

## Why This Works

Like remembering a good restaurant:
- You don't track every meal
- You don't record what you ate
- You just remember: "That place was good"

Next time you want pizza, you go back to the good place.

## The Entire Implementation

```python
memory = {}

def remember(agent_id, worked):
    memory[agent_id] = worked

def check_memory(need):
    for agent_id, worked in memory.items():
        if matches(agent_id, need) and worked:
            return get_agent(agent_id)
    return None
```

That's the whole feature. Dead simple.