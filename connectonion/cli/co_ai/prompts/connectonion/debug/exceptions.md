# Auto Debug Exception - AI-Powered Exception Debugger

**Debugs ONLY uncaught exceptions** - crashes, raised exceptions, and failed assertions.

When your Python program **encounters an uncaught exception**, ConnectOnion's `auto_debug_exception()` gives the AI **live access to your program's runtime state**. The AI can execute code, inspect objects, and test fixes using the actual data. No more guessing - get verified solutions that actually work.

> **Important:** This only works for uncaught exceptions. For logic errors that don't crash, use `raise` or `assert` to convert them to exceptions!

## Quick Start

```python
from connectonion import auto_debug_exception

# Enable AI debugging with runtime inspection
auto_debug_exception()

# Your code - any crash triggers deep AI analysis
data = {"users": []}
average = sum(u["age"] for u in data["users"]) / len(data["users"])  # Crashes!
```

When this crashes, the AI will:
1. Show the normal Python traceback first
2. Execute code in the crashed context to understand what happened
3. Test potential fixes with your actual data
4. Provide a working solution you can copy-paste

## What Makes This Special

### 🔬 Live Runtime Access
The AI isn't just reading your code - it has access to the actual runtime state when the crash occurred. It can:
- Execute any Python expression using your variables
- See the real values that caused the problem
- Test fixes before suggesting them

### ✅ Verified Solutions
Every fix is tested with your actual data before being suggested. No more "this might work" - only proven solutions.

### 🎯 Precise Analysis
The AI can explore your data structures, check types, validate assumptions, and trace variables through the call stack.

## Real-World Examples

### Example 1: Empty Collection Crash

```python
from connectonion import auto_debug_exception
auto_debug_exception()

def calculate_metrics(scores):
    return {
        'average': sum(scores) / len(scores),  # Crashes if empty!
        'maximum': max(scores),
        'minimum': min(scores)
    }

result = calculate_metrics([])  # 💥 Multiple issues!
```

**AI Runtime Debug Analysis:**

What I found:
- Executed: len(scores) → 0
- Executed: sum(scores) → 0
- The division 0/0 causes ZeroDivisionError
- Also tested: max([]) raises ValueError

Why it failed:
Empty list causes division by zero and max()/min() to fail

Verified fix (tested with your data):
```python
def calculate_metrics(scores):
    if not scores:
        return {
            'average': 0,
            'maximum': None,
            'minimum': None
        }
    return {
        'average': sum(scores) / len(scores),
        'maximum': max(scores),
        'minimum': min(scores)
    }

```

### Example 2: Nested Dictionary Access

```python
from connectonion import auto_debug_exception
auto_debug_exception()

# API response with unexpected structure
response = {
    'data': {
        'user': {
            'profile': {'name': 'Alice'}
            # Missing 'settings' key!
        }
    }
}

# Your code expects different structure
theme = response['data']['user']['profile']['settings']['theme']  # 💥
```

**AI Runtime Debug Analysis:**
```
What I found:
- Executed: list(response['data']['user']['profile'].keys()) → ['name']
- No 'settings' key exists in profile
- Tested: response['data']['user']['profile'].get('settings') → None

Why it failed:
KeyError because 'settings' doesn't exist in the profile dictionary

Verified fix (tested with your data):
```python
# Safe navigation with defaults
profile = response['data']['user']['profile']
theme = profile.get('settings', {}).get('theme', 'light')

# Or check before accessing
if 'settings' in profile and 'theme' in profile['settings']:
    theme = profile['settings']['theme']
else:
    theme = 'light'  # default
```
```

### Example 3: Type Mismatch

```python
from connectonion import auto_debug_exception
auto_debug_exception()

def process_items(items):
    # Expects list, might get dict or string
    for item in items:
        print(f"Processing: {item['id']}")

# API returned dict instead of list
api_data = {'item1': {...}, 'item2': {...}}
process_items(api_data)  # 💥
```

**AI Runtime Debug Analysis:**
```
What I found:
- Executed: type(items) → <class 'dict'>
- Iterating over dict gives keys, not items
- Executed: list(items.keys()) → ['item1', 'item2']
- item (the key) is a string, not dict with 'id'

Why it failed:
TypeError because you're iterating over dict keys (strings), not dict values

Verified fix (tested with your data):
```python
def process_items(items):
    # Handle both list and dict
    if isinstance(items, dict):
        items = items.values()

    for item in items:
        print(f"Processing: {item['id']}")
```
```

## Power Features

### 1. Execute Code in Crashed Context
The AI can run any Python code using your actual variables:
```python
# AI explores your data:
execute_in_frame("type(data)")  # → <class 'dict'>
execute_in_frame("list(data.keys())")  # → ['users', 'config']
execute_in_frame("len(data['users'])")  # → 0
```

### 2. Deep Object Inspection
See everything about an object - type, attributes, methods, values:
```python
# AI inspects complex objects:
inspect_object("response")
# → Type: dict
# → Keys: ['data', 'meta', 'errors']
# → Methods: get, items, keys, values...
```

### 3. Test Fixes Before Suggesting
The AI tests solutions with your actual data:
```python
# AI tests potential fixes:
test_fix(
    "data['missing']",  # Original (fails)
    "data.get('missing', 'default')"  # Fixed (works)
)
# → Original: ✗ KeyError
# → Fixed: ✓ Returns 'default'
```

### 4. Validate Assumptions
Test any hypothesis about your data:
```python
# AI validates assumptions:
validate_assumption("isinstance(data, dict)")  # → ✓ TRUE
validate_assumption("len(users) > 0")  # → ✗ FALSE
validate_assumption("'id' in user")  # → Shows available keys
```

### 5. Trace Variables Through Stack
See how variables changed across function calls:
```python
# AI traces variable through call stack:
trace_variable("user_data")
# → Frame 1: process() - user_data = {...}
# → Frame 2: validate() - user_data = {...}
# → Frame 3: save() - user_data = None (modified!)
```

## Configuration

### Choose Your Model

```python
# Use a specific model
auto_debug(model="gpt-4")  # More thorough analysis
auto_debug(model="o4-mini")  # Faster, default
```

### Disable via Environment

In your `.env` file:
```bash
# Disable auto_debug completely
CONNECTONION_AUTO_DEBUG=false
```

Or temporarily:
```bash
CONNECTONION_AUTO_DEBUG=false python your_script.py
```

## Best Practices

### When to Use

✅ **Perfect for:**
- Development and debugging
- Understanding unfamiliar codebases
- Complex data structure issues
- Learning from mistakes
- Debugging production issues locally

❌ **Not recommended for:**
- Production environments (exposes runtime data)
- Performance-critical code (adds overhead)
- Simple syntax errors (overkill)

### Tips for Best Results

1. **Let it crash** - Don't wrap in try/except, let auto_debug catch it
2. **Use descriptive variable names** - Helps AI understand context
3. **Keep sensitive data out** - AI sees all variables in crashed scope

## How It Works

1. **Exception Hook**: Intercepts uncaught exceptions via `sys.excepthook`
2. **Frame Capture**: Captures the exception frame with all variables
3. **Runtime Inspector**: Creates a `RuntimeInspector` with crashed state
4. **AI Analysis**: Provides tools for the AI to explore and test
5. **Solution Verification**: Tests fixes before suggesting them

## Limitations

- **Only uncaught exceptions** - Caught exceptions aren't analyzed
- **Frame access** - Some built-in objects may not be fully inspectable
- **API dependency** - Requires OpenAI/Anthropic API access
- **Performance** - Adds overhead, not for production

## Security Notes

⚠️ **The AI can see all variables in the crashed scope**, including:
- API keys in variables (use environment variables instead)
- User data
- Database credentials
- Any sensitive information in memory

For production, always set `CONNECTONION_AUTO_DEBUG=false`.

## Coming Soon

Based on user feedback, we're considering:
- **Automatic fix application** - Apply the verified fix automatically
- **Historical analysis** - Learn from past crashes
- **Team sharing** - Share crash analysis with team
- **Custom prompts** - Tailor analysis to your needs
- **Offline mode** - Save crash state for later analysis

## See Also

- [Getting Started](quickstart.md) - ConnectOnion basics
- [RuntimeInspector](runtime_inspector.md) - Technical details of runtime tools
- [Debug Agent](debug_agent.md) - How the debug agent works
- [Examples](examples.md#auto-debug) - More auto_debug examples