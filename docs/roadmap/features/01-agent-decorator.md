# @agent Decorator

Make any function discoverable by other agents.

## Usage

```python
from connectonion import agent

@agent
def translate(text: str, to_lang: str) -> str:
    """I translate text to any language"""
    return my_translation_logic(text, to_lang)
```

That's it. Your function is now discoverable.

## What It Does

- Makes your function available to other agents
- Automatically extracts capabilities from docstring
- Handles network communication
- Zero configuration

## Example

```python
# calculator.py
from connectonion import agent

@agent
def calculate(expression: str) -> float:
    """I solve math problems"""
    return eval(expression)  # Simple example

# Run it
# $ connectonion serve calculator.py
# Now other agents can discover "calculate"
```