# Local First

Everything works offline after first use.

## Usage

```python
# First time - needs network
translator = discover("translate")
result = translator("Hello", to_lang="es")

# Second time - works offline
# (Agent cached locally)
result = translator("World", to_lang="es")
```

## Cache Management

```python
from connectonion import cache

# See what's cached
cache.list()
"""
Cached agents: 12
- translator (used 2h ago)
- analyzer (used 1d ago)
- summarizer (used 3d ago)
Total size: 45MB
"""

# Pre-cache agents
cache.download("sentiment analyzer")
cache.download("text processor")

# Clear old cache
cache.clean(older_than_days=30)
```

## Offline Mode

```python
from connectonion import offline_mode

# Force offline only
with offline_mode():
    # Only uses cached agents
    translator = discover("translate")  
    # Raises error if not cached
```

## Sync Strategy

```python
# Configure caching
from connectonion import configure

configure(
    cache_size_mb=500,
    cache_duration_days=7,
    auto_cache=True,  # Cache every used agent
    preload=["translate", "analyze"]  # Always keep these
)
```