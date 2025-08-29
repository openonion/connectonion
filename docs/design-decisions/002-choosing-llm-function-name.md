# Design Decision: Choosing `llm_do()` as the Function Name

## Date
2024-01-29 (Updated: 2024-01-30)

## Status
Decided → Revised

## Context

We needed a simple, intuitive function for one-shot LLM calls with optional structured output. The function would:
- Make single-round LLM calls (no loops/iterations)
- Support both string and Pydantic model outputs
- Accept prompts as strings or file paths
- Be immediately understandable to developers

## Initial Decision: `llm()`

We initially chose `llm()` for its simplicity. However, user feedback revealed a critical issue:
- **`llm` reads as a noun, not a verb**
- Functions should be actions (verbs)
- Users were confused about what `llm()` does at a glance

## Final Decision: `llm_do()`

After extensive analysis, we chose `llm_do()` because:

1. **Has a clear verb**: "do" is the most versatile action word
2. **Works for all use cases**:
   ```python
   answer = llm_do("What's 2+2?")  # Do the calculation
   invoice = llm_do(text, output=Invoice)  # Do the extraction
   translation = llm_do("Hello", prompt="Translate")  # Do the translation
   ```
3. **Immediately clear**: Users understand it's performing an action
4. **Still short**: Only 6 characters

## Options We Considered

### 1. `llm_do()` ✅ **CHOSEN**
```python
answer = llm_do("What's 2+2?")
data = llm_do(text, output=Report)
```

**Pros:**
- Clear verb that implies action
- Works naturally for ALL use cases
- Professional yet simple
- Only 6 characters

**Cons:**
- Slightly longer than `llm()`

### 2. `llm()` (Original)
```python
answer = llm("What's 2+2?")
```

**Pros:**
- Shortest possible (3 chars)
- Clean look

**Cons:**
- **Reads as noun, not verb**
- Unclear what action it performs
- Users confused at first glance

### 3. `llm_oneshot()`
```python
result = llm_oneshot("Process this")
```

**Pros:**
- Explicitly describes behavior
- Zero ambiguity

**Cons:**
- Too verbose (11 characters)
- Feels like enterprise Java
- Not elegant

### 4. `llm_tap()`
```python
answer = llm_tap("What's 2+2?")
```

**Pros:**
- Elegant, modern feel
- Short (7 chars)

**Cons:**
- Only sounds good for questions
- Weird for extraction/conversion tasks

### 5. `llm_go()`
```python
answer = llm_go("What's 2+2?")
```

**Pros:**
- Very short (6 chars)
- Simple verb

**Cons:**
- Too vague ("go where?")
- Doesn't indicate what happens

### 6. `llm_gen()`
```python
answer = llm_gen("What's 2+2?")
```

**Pros:**
- "gen" is a clear verb (generate)
- Modern (Gen AI)

**Cons:**
- Implies generation only
- Not intuitive for extraction tasks

### 7. `llm_call()`
```python
answer = llm_call("What's 2+2?")
```

**Pros:**
- "Call" implies single execution
- Natural phrasing

**Cons:**
- Could be confused with function calls
- Less versatile than "do"

### 8. `ask()`
```python
answer = ask("What's 2+2?")
```

**Pros:**
- Natural, conversational
- Very short

**Cons:**
- Doesn't convey all use cases
- Too informal for extraction/analysis

## Implementation

```python
from connectonion import llm_do

# Clear distinction in usage
result = llm_do("Quick question")      # Verb makes action clear
agent.llm = OpenAILLM()                # Noun for the instance
response = agent.llm.complete(...)     # Method on the instance
```

## Testing Against Real Use Cases

Looking at our documentation examples:

```python
# Data Extraction
invoice = llm_do(invoice_text, output=Invoice)  # ✅ "Do the extraction"

# Analysis
analysis = llm_do(text, output=FeedbackAnalysis)  # ✅ "Do the analysis"

# Translation
translation = llm_do("Hello", prompt="Translate")  # ✅ "Do the translation"

# Validation
is_valid = llm_do("Is this SQL valid?")  # ✅ "Do the validation"
```

`llm_do()` reads naturally across all use cases, while alternatives like `llm_tap()` only work for some.

## Consequences

### Positive
- Users immediately understand it's an action
- Works naturally for all use cases
- Clear contrast with `Agent()` for complex workflows
- Follows function naming best practices (verb-based)

### Negative
- Slightly longer than original `llm()` (6 vs 3 chars)
- Need to update all documentation and examples

## Lessons Learned

1. **Functions need verbs**: Even if shorter, noun-based function names confuse users
2. **Versatility matters**: The verb must work for ALL use cases, not just some
3. **User feedback is crucial**: The confusion with `llm()` only became clear through usage
4. **"Do" is the ultimate verb**: It's the most versatile action word in English

## References

- [Principle: Simple things simple](../principles.md)
- [Python naming conventions](https://peps.python.org/pep-0008/)
- Similar patterns: `requests.get()`, `json.loads()`, `pd.read_csv()`