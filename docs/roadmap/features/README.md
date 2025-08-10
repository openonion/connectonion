# ConnectOnion Features

Simple features for agent developers.

## Core Features

1. **[Share & Find](01-share-and-find.md)** - Share functions and find what you need with natural language
2. **[Test before trust](03-test-before-trust.md)** - Try functions safely

## Trust & Reliability

3. **[Reliability & Offline](06-reliability-and-offline.md)** - Experience, memory, and offline cache

## Analytics

4. (reserved)

## Design Principles

- One line to share functions
- Natural language to find what you need
- Everything else automatic
- No configuration needed
- Trust through experience

## Getting Started

```python
# 1. Share your function
from connectonion import share

def translate(text: str, to_lang: str = "en") -> str:
    return my_translation(text, to_lang)

share(translate)  # One line to share

# 2. Find what you need
from connectonion import need

summarizer = need("make this text shorter")
summary = summarizer(long_text)

# That's it!
```

See **[Share & Find](01-share-and-find.md)** for complete examples and advanced options.