# Fallback

Handle failures gracefully with automatic alternatives.

## Usage

```python
from connectonion import fallback

@agent
def reliable_translator(text: str) -> str:
    """I never fail - I find alternatives"""
    
    result = fallback(
        lambda: discover("premium translator")(text),
        lambda: discover("basic translator")(text),
        lambda: f"Translation unavailable for: {text[:20]}..."
    )
    
    return result
```

## Multiple Fallbacks

```python
@agent
def resilient_analyzer(data):
    """I try multiple approaches"""
    
    # Try agents in order until one works
    for agent_type in ["advanced analyzer", "standard analyzer", "basic analyzer"]:
        try:
            analyzer = discover(agent_type)
            return analyzer(data)
        except:
            continue
    
    # Final fallback
    return {"error": "All analyzers unavailable"}
```

## Fallback with Conditions

```python
def smart_processing(data, quality_needed=0.9):
    # Try high quality first
    try:
        premium = discover("premium processor", min_quality=quality_needed)
        return premium(data)
    except:
        # Accept lower quality if needed
        basic = discover("processor", min_quality=0.7)
        return basic(data)
```

## Transparent Fallbacks

```python
result = fallback(
    primary=lambda: expensive_agent(data),
    secondary=lambda: cheap_agent(data),
    track=True  # Record which was used
)

print(result.value)  # The actual result
print(result.used)   # "secondary" (which agent was used)
print(result.reason) # "primary timeout after 1000ms"
```