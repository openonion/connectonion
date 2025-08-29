# Design Decision: Choosing `llm()` as the Function Name

## Date
2024-01-29

## Status
Decided

## Context

We needed a simple, intuitive function for one-shot LLM calls with optional structured output. The function would:
- Make single-round LLM calls (no loops/iterations)
- Support both string and Pydantic model outputs
- Accept prompts as strings or file paths
- Be immediately understandable to developers

## Options Considered

### 1. `llm()` ✅ **CHOSEN**
```python
answer = llm("What's 2+2?")
data = llm(text, output=Report)
```

**Pros:**
- Most intuitive - developers immediately understand it's an LLM call
- Short (3 characters)
- Honest about what it does
- No new concepts to learn
- Follows Python convention (lowercase function vs uppercase LLM class)

**Cons:**
- Potential confusion with existing `LLM` class (but context makes it clear)
- Very generic name

### 2. `ask()`
```python
answer = ask("What's 2+2?")
```

**Pros:**
- Natural, conversational
- Zero learning curve
- No naming conflicts

**Cons:**
- Doesn't convey all use cases (formatting, extraction)
- Might imply Q&A only

### 3. `llm_oneshot()`
```python
result = llm_oneshot("Process this")
```

**Pros:**
- Explicitly describes behavior
- Zero ambiguity
- No conflicts

**Cons:**
- Verbose (12 characters)
- Feels like enterprise Java
- Not "cool" or Pythonic

### 4. `smart()`
```python
result = smart("Analyze this")
```

**Pros:**
- Implies intelligence
- Short and memorable

**Cons:**
- Vague - what does "smart" mean?
- Could be anything

### 5. `ai()`
```python
result = ai("Hello")
```

**Pros:**
- Short, modern
- Clear it uses AI

**Cons:**
- Too generic
- Could be confused with module/class

### 6. `gen()`
```python
result = gen("Write a poem")
```

**Pros:**
- Modern, aligns with "Gen AI" trend
- Short (3 characters)
- Versatile meaning

**Cons:**
- Implies generation, not analysis/extraction
- Less intuitive than `llm()`

### 7. `format()` ❌
```python
result = format(data, output=Model)
```

**Cons:**
- Conflicts with Python builtin!
- Misleading (does more than format)

### 8. `complete()`
```python
result = complete("The capital of France is")
```

**Pros:**
- Matches OpenAI terminology
- Technically accurate

**Cons:**
- Implies text completion, not Q&A
- Longer than `llm()`

## Decision

We chose **`llm()`** because:

1. **Most Intuitive**: Every developer understands `llm("question")` makes an LLM call
2. **No Learning Curve**: The name is self-documenting
3. **Flexible Semantics**: Works for asking, formatting, extracting, thinking - the name doesn't prescribe the action
4. **Clean Separation**: 
   - `llm()` = function (lowercase) 
   - `LLM` = class (uppercase)
   - `agent.llm` = instance variable
5. **Pythonic**: Follows conventions, short, clear

## Implementation Notes

```python
# Clear distinction in imports
from connectonion import llm  # Function
from connectonion.llm import LLM  # Class (if needed)

# No confusion in practice
result = llm("Quick question")      # Function call
agent.llm = OpenAILLM()             # Instance variable
response = agent.llm.complete(...)  # Method call
```

## Consequences

### Positive
- Developers immediately understand the function
- No need for documentation to explain the name
- Natural progression: `llm()` for simple, `Agent()` for complex
- Maintains simplicity principle

### Negative
- Slightly generic name
- Potential initial confusion with LLM class (but quickly resolved by context)

## Lessons Learned

1. **Intuitive > Clever**: `llm()` is boring but immediately understood
2. **Context Resolves Ambiguity**: Python conventions and usage patterns clarify any confusion
3. **Short Names Matter**: 3 characters vs 12 makes a difference in daily use
4. **Don't Overthink**: The obvious choice (`llm()`) was the right choice

## References

- [Principle: Simple things simple](../principles.md)
- [Python naming conventions](https://peps.python.org/pep-0008/)
- Similar patterns: `datetime.datetime`, `list()` function vs `List` type