# discover()

Find and use other agents by what they do.

## Usage

```python
from connectonion import discover

# Find an agent
translator = discover("translate text")

# Use it
result = translator("Hello", to_lang="es")
print(result)  # "Hola"
```

## Semantic Discovery

```python
# These all find the same agent
translator = discover("translate")
translator = discover("convert text to another language")
translator = discover("i need spanish translation")
```

## Discovery Options

```python
# Get all matches
translators = discover.all("translate")

# Set quality requirements
good_translator = discover("translate", min_quality=0.9)

# Prefer local agents
local = discover("analyze", prefer_local=True)
```

## Example

```python
# Inside your agent
@agent
def smart_analyzer(text: str) -> dict:
    """I analyze text in any language"""
    
    # Discover translator
    translator = discover("translate to english")
    english_text = translator(text, to_lang="en")
    
    # Discover sentiment analyzer
    analyzer = discover("detect emotions")
    return analyzer(english_text)
```