# One-shot LLM Calls

Make direct LLM calls with optional structured output.

## Quick Start

```python
from connectonion import llm_do

answer = llm_do("What's 2+2?")  
print(answer)  # "4"
```

That's it! One function for any LLM task.

## With Structured Output

```python
from pydantic import BaseModel

class Analysis(BaseModel):
    sentiment: str
    confidence: float
    keywords: list[str]

result = llm_do(
    "I absolutely love this product! Best purchase ever!",
    output=Analysis
)
print(result.sentiment)    # "positive"
print(result.confidence)   # 0.98
print(result.keywords)     # ["love", "best", "ever"]
```

## Real Examples

### Extract Data from Text

```python
class Invoice(BaseModel):
    invoice_number: str
    total_amount: float
    due_date: str

invoice_text = """
Invoice #INV-2024-001
Total: $1,234.56
Due: January 15, 2024
"""

invoice = llm_do(invoice_text, output=Invoice)
print(invoice.total_amount)  # 1234.56
```

### Use Custom Prompts

```python
# With prompt file
summary = llm_do(
    long_article,
    system_prompt="prompts/summarizer.md"  # Loads from file
)

# With inline prompt
translation = llm_do(
    "Hello world",
    system_prompt="You are a translator. Translate to Spanish only."
)
print(translation)  # "Hola mundo"
```

### Quick Analysis Tool

```python
def analyze_feedback(text: str) -> str:
    """Analyze customer feedback with structured output."""
    
    class FeedbackAnalysis(BaseModel):
        category: str  # bug, feature, praise, complaint
        priority: str  # high, medium, low
        summary: str
        action_required: bool
    
    analysis = llm_do(text, output=FeedbackAnalysis)
    
    if analysis.action_required:
        return f"🚨 {analysis.priority.upper()}: {analysis.summary}"
    return f"📝 {analysis.category}: {analysis.summary}"

# Use in an agent
from connectonion import Agent
agent = Agent("support", tools=[analyze_feedback])
```

## Advanced Usage

```python
result = llm_do(
    input="Your text here",
    output=YourModel,              # Optional: Pydantic model for structure
    system_prompt="instructions", # Optional: String or file path
    model="gpt-4o-mini",              # Optional: Default is "gpt-4o-mini"
    temperature=0.7,               # Optional: Default is 0.1 (consistent)
)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input` | str | required | The input text/question |
| `output` | BaseModel | None | Pydantic model for structured output |
| `system_prompt` | str\|Path | None | System prompt (string or file path) |
| `model` | str | "gpt-4o-mini" | OpenAI model to use (fast & cheap by default) |
| `temperature` | float | 0.1 | Randomness (0=deterministic, 2=creative) |

## What You Get

- ✅ **One-shot execution** - Single LLM round, no loops
- ✅ **Type safety** - Full IDE autocomplete with Pydantic
- ✅ **Flexible prompts** - Inline strings or external files
- ✅ **Smart defaults** - Fast model, low temperature
- ✅ **Clean errors** - Clear messages when things go wrong

## Common Patterns

### Data Extraction
```python
class Person(BaseModel):
    name: str
    age: int
    occupation: str

person = llm_do("John Doe, 30, software engineer", output=Person)
```

### Quick Decisions
```python
is_urgent = llm_do("Customer says: My server is down!") 
if "urgent" in is_urgent.lower():
    escalate()
```

### Format Conversion
```python
class JSONData(BaseModel):
    data: dict

json_result = llm_do("Convert to JSON: name=John age=30", output=JSONData)
print(json_result.data)  # {"name": "John", "age": 30}
```

### Validation
```python
def validate_input(user_text: str) -> bool:
    result = llm_do(
        f"Is this valid SQL? Reply yes/no only: {user_text}",
        temperature=0  # Maximum consistency
    )
    return result.strip().lower() == "yes"
```

## Tips

1. **Use low temperature (0-0.3) for consistent results**
2. **Provide examples in your prompt for better accuracy**
3. **Use Pydantic models for anything structured**
4. **Cache prompts in files for reusability**

## Comparison with Agent

| Feature | `llm_do()` | `Agent()` |
|---------|---------|-----------|
| Purpose | One-shot calls | Multi-step workflows |
| Tools | No | Yes |
| Iterations | Always 1 | Up to max_iterations |
| State | Stateless | Maintains history |
| Best for | Quick tasks | Complex automation |

```python
# Use llm_do() for simple tasks
answer = llm_do("What's the capital of France?")

# Use Agent for multi-step workflows
agent = Agent("assistant", tools=[search, calculate])
result = agent.input("Find the population and calculate density")
```

## Error Handling

```python
from connectonion import llm_do
from pydantic import ValidationError

try:
    result = llm_do("Analyze this", output=ComplexModel)
except ValidationError as e:
    print(f"Output didn't match model: {e}")
except Exception as e:
    print(f"LLM call failed: {e}")
```

## Next Steps

- Learn about [Agents](agents.md) for multi-step workflows
- Explore [Tools](tools.md) for extending agents
- See [xray](xray.md) for debugging
