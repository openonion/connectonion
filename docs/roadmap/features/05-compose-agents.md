# Compose Agents

Chain agents together like functions.

## Usage

```python
@agent
def research_assistant(topic: str) -> str:
    """I research any topic thoroughly"""
    
    # Find agents
    search = discover("web search")
    summarize = discover("summarize")
    factcheck = discover("verify facts")
    
    # Compose them
    results = search(topic)
    summary = summarize(results)
    verified = factcheck(summary)
    
    return verified
```

## Pipeline Operator

```python
from connectonion import discover, pipeline

# Create a pipeline
translate_and_analyze = pipeline(
    discover("translate to english"),
    discover("sentiment analysis"),
    discover("extract key points")
)

# Use it
result = translate_and_analyze(foreign_text)
```

## Simple Composition

```python
# Compose with | operator
translator = discover("translate")
analyzer = discover("analyze")

result = translator("Bonjour", to_lang="en") | analyzer
# Translator output feeds into analyzer
```

## Error Handling

```python
@agent
def safe_pipeline(data):
    """I handle failures gracefully"""
    
    try:
        # Primary pipeline
        processor = discover("advanced processor")
        enhancer = discover("enhance quality")
        return enhancer(processor(data))
    except:
        # Fallback pipeline
        basic = discover("basic processor")
        return basic(data)
```