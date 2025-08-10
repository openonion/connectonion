# Share and Find Functions

Share your functions and find what you need with natural language.

## Share Your Functions

Share any function with one line - no decorators needed.

```python
from connectonion import share

# Any function can be shared
def translate(text: str, to_lang: str = "en") -> str:
    """I translate text to any language"""
    return my_translation_logic(text, to_lang)

def analyze_sentiment(text: str) -> str:
    """I detect emotions in text"""
    return sentiment_analysis(text)

# One line to share each
share(translate)
share(analyze_sentiment)

# That's it! Others can now find your functions
```

### Share Multiple with Agent (optional)

If you prefer a single entry point, bundle functions with a tiny Agent helper.

```python
from connectonion import Agent

agent = Agent(
    name="writer-a1",
    share=[translate, analyze_sentiment]  # functions only; names default to fn.__name__
).start()

# Discovery stays the same
translator = need("translate to spanish")
```

## Find What You Need

Use natural language to describe what you need - no function names required.

```python
from connectonion import need

# Just describe what you need
translator = need("translate text to spanish")
result = translator("Hello")  # "Hola"

# Any natural description works
analyzer = need("figure out if this review is positive")
sentiment = analyzer("I love this product!")  # "positive"

summarizer = need("make this text shorter")
calculator = need("solve math problems")
```

## Natural Language Magic

### Works in Any Language
```python
# English
processor = need("analyze customer feedback")

# Spanish
procesador = need("analizar comentarios de clientes")

# Chinese
处理器 = need("分析客户反馈")

# All find the same capability!
```

### Understands Variations
```python
# All of these find translation
translator = need("translate text")
translator = need("convert to another language")
translator = need("I don't understand this foreign text")
translator = need("help me read spanish")
```

### Context Aware
```python
# Same description, different context
helper = need("analyze this")

# Understands from your data
result1 = helper("I love it!")        # Sentiment analysis
result2 = helper([1,2,3,4,5])         # Statistical analysis  
result3 = helper(image_data)          # Image analysis
```

## Complete Example

```python
from connectonion import share, need

# 1. Share your function
def my_translator(text: str, target_lang: str = "en") -> str:
    """I translate text between languages"""
    return translate_logic(text, target_lang)

share(my_translator)

# 2. Find what you need
sentiment_analyzer = need("detect emotions in text")
summarizer = need("make long text shorter")

# 3. Use them together
def process_review(foreign_review: str) -> dict:
    # Translate first
    english = my_translator(foreign_review, "en")
    
    # Then analyze
    sentiment = sentiment_analyzer(english)
    summary = summarizer(english)
    
    return {
        "sentiment": sentiment,
        "summary": summary,
        "original": foreign_review
    }

# 4. Use it
result = process_review("¡Este producto es increíble!")
```

## Advanced Options

### Find Multiple Options
```python
# Get all available translators
translators = need.all("translate text")

# Try each one
for translator in translators:
    try:
        result = translator("Hello")
        if result:  # Found a working one
            break
    except:
        continue
```

### Quality Requirements
```python
# Only high-quality functions
translator = need("translate text", min_quality=0.9)

# Prefer local functions
local_analyzer = need("analyze data", prefer_local=True)

# Prefer fast functions
quick_processor = need("process image", max_response_time=100)
```

### Test Before Use
```python
# Test a function before trusting it
translator = need("translate to spanish")

# Test with known input/output
if translator.test("Hello", expected="Hola"):
    # It works, use it
    result = translator("Good morning")
```

## Sharing Options

### Share with Metadata
```python
share(
    my_function,
    description="Custom description",
    tags=["fast", "reliable"],
    max_concurrent=10
)
```

### Share Multiple Functions
```python
# Share all functions from a module
import my_tools
share.module(my_tools)

# Share specific functions
share.functions([translate, analyze, summarize])
```

### Temporary Sharing
```python
# Share for limited time
share(my_function, ttl=3600)  # 1 hour

# Share only to specific network
share(my_function, network="local")
```

## Network Discovery

Functions are automatically discovered across:
- Local network (same WiFi/LAN)
- Trusted peers
- Public networks (opt-in)

```python
# See what's available
available = need.list()
print(f"Found {len(available)} functions")

# Search by capability
translators = need.search("translation")
analyzers = need.search("analysis")
```

## Error Handling

```python
def safe_processing(data):
    try:
        # Try advanced processor
        processor = need("advanced data processing")
        return processor(data)
    except:
        # Fallback to basic
        basic = need("basic data processing")
        return basic(data)
```

## The Beauty

**Zero configuration.** Just:
1. `share(function)` - One line to share
2. `need("what you want")` - Natural language to find
3. Use it like any Python function

No decorators, no setup, no configuration files. It just works.