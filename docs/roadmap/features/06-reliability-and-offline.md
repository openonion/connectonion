# Reliability & Offline (Experience, Memory, Local First)

Make results reliable over time and keep working offline. This combines three simple ideas:
- Personal experience with functions (my_experience)
- Trust memory (prefer what worked before)
- Local-first (cache to work offline)

## Quick Start

```python
from connectonion import share, need

# Share once
def translate(text: str, to_lang: str = "es") -> str:
    return my_translation(text, to_lang)
share(translate)

# Use naturally
translator = need("translate to Spanish")
print(translator("Hello"))  # "Hola"

# Next time, need() prefers the same one that worked
translator = need("translate to Spanish")
```

---

## Personal Experience (my_experience)

Track your own history automatically and prefer what worked for you.

```python
translator = need("translate text")

# Use it a few times
translator("Hello", to_lang="es")
translator("World", to_lang="es")

# Check your experience
print(translator.my_experience)
"""
{
  "uses": 2,
  "success_rate": 1.0,
  "avg_time_ms": 47,
  "last_used": "2024-01-10T10:30:00"
}
"""

# Prefer trusted automatically
best = need("translate text", prefer_trusted=True)
```

See recent interactions and manage experience.

```python
analyzer = need("analyze text")
experience = analyzer.my_experience
print(f"Success rate: {experience.success_rate:.1%}")
print(f"Average time: {experience.avg_time_ms}ms")
print(f"Total uses: {experience.uses}")

for interaction in experience.recent(5):
    print(f"{interaction.time}: {interaction.result}")

# Reset or forget
analyzer.reset_experience()
```

---

## Trust Memory (Prefer What Worked)

Remember what worked and reuse it next time. Dead simple.

```python
# First time - discovers new
summarizer = need("summarize text")
summary = summarizer(article)  # Works → remembered as "worked"

# Next time - returns the same one that worked
summarizer = need("summarize text")
```

Avoid bad options automatically.

```python
processor = need("process data")
result = processor(data)  # Fails → remembered as "didn't work"

# Next time, returns a different one
processor = need("process data")
```

Minimal mental model:

```python
def need(description):
    previous = find_in_memory(description)
    if previous and previous.worked:
        return previous
    return discover(description)  # internal detail; you just call need()
```

Simple visibility and maintenance:

```python
# See what worked for you
my_memory()
"""
✓ translator - worked
✓ summarizer - worked  
✗ processor - didn't work
✓ analyzer - worked
"""

# Clean up old entries
forget_old()      # Clears entries older than 30 days
reset_memory()    # Start fresh
```

Privacy by default:
- Only stores: minimal ID + worked/didn't work
- No data about your inputs
- No frequency tracking

---

## Local First (Cache & Offline)

Everything keeps working offline after first use.

```python
# First time - needs network
translator = need("translate text")
print(translator("Hello"))  # "Hola"

# Second time - works offline (cached)
print(translator("World"))  # Uses local cache
```

Cache management made simple.

```python
from connectonion import cache

# See what's cached
cache.list()
"""
Cached functions: 12
- translator (used 2h ago)
- analyzer (used 1d ago)
- summarizer (used 3d ago)
Total size: 45MB
"""

# Pre-cache common needs
cache.download("sentiment analyzer")
cache.download("text processor")

# Clear old cache
cache.clean(older_than_days=30)
```

Force offline mode when needed.

```python
from connectonion import offline_mode

# Only use cached functions
with offline_mode():
    translator = need("translate text")
    # Raises error if not cached
```

Basic sync configuration (optional).

```python
from connectonion import configure

configure(
    cache_size_mb=500,
    cache_duration_days=7,
    auto_cache=True,          # Cache everything you use
    preload=["translate", "analyze"]  # Keep these ready
)
```

---

## Why This Works

- Your own experience is the best trust signal
- Simple memory beats complex reputation systems
- Local caching gives speed, reliability, and offline capability

Keep it simple: need() chooses, memory remembers, cache keeps you running.