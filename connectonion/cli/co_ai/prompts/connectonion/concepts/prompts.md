# System Prompts - File Format Support

ConnectOnion can load system prompts from **any text file format**. Use whatever format your team prefers.

## Supported Formats

**All text files work** - ConnectOnion simply reads the content:

```python
from connectonion import Agent

# All of these work identically:
agent = Agent("bot", system_prompt="prompts/assistant.md")     # Markdown
agent = Agent("bot", system_prompt="prompts/assistant.yaml")   # YAML
agent = Agent("bot", system_prompt="prompts/assistant.json")   # JSON
agent = Agent("bot", system_prompt="prompts/assistant.txt")    # Plain text
agent = Agent("bot", system_prompt="prompts/assistant")        # No extension
agent = Agent("bot", system_prompt="prompts/assistant.prompt") # Custom extension
```

## Loading Methods

### 1. String (Auto-Detection)
```python
agent = Agent("bot", system_prompt="prompts/my_prompt.md")
# ✅ Loads file if it exists
# ✅ Uses as literal text if file doesn't exist
```

### 2. Path Object (Explicit)
```python
from pathlib import Path
agent = Agent("bot", system_prompt=Path("prompts/my_prompt.yaml"))
# ✅ Must be a valid file path
# ❌ Raises error if file doesn't exist
```

### 3. Direct String
```python
agent = Agent("bot", system_prompt="You are a helpful assistant.")
# ✅ Uses the text directly
```

## File Format Examples

### Markdown Format (`assistant.md`)
```markdown
# AI Assistant
You are a helpful assistant who provides clear, concise answers.
```

### YAML Format (`assistant.yaml`)
```yaml
role: AI Assistant
instructions: You are a helpful assistant who provides clear, concise answers.
```

### JSON Format (`assistant.json`)
```json
{
  "role": "AI Assistant",
  "instructions": "You are a helpful assistant who provides clear, concise answers."
}
```

### Plain Text (`assistant.txt`)
```
You are a helpful assistant who provides clear, concise answers.
```

### No Extension (`assistant`)
```
You are a helpful assistant who provides clear, concise answers.
```

## Key Points

- **No parsing** - ConnectOnion just reads the text content
- **Any extension** - `.md`, `.yaml`, `.json`, `.txt`, `.prompt`, or none
- **Simple** - No special configuration required
- **Flexible** - Change formats without changing code

## Environment-Based Loading

```python
import os

# Use different prompts for different environments
env = os.getenv("ENV", "dev")
agent = Agent("bot", system_prompt=f"prompts/{env}/assistant.md")
```

## Dynamic Loading

```python
from pathlib import Path

def create_agent(name: str, prompt_file: str):
    path = Path(prompt_file)
    if path.exists():
        return Agent(name, system_prompt=path)
    else:
        # Fallback to default
        return Agent(name, system_prompt="You are a helpful assistant.")
```

## Error Handling

```python
from pathlib import Path
from connectonion.prompts import load_system_prompt

try:
    prompt = load_system_prompt(Path("prompts/missing.md"))
except FileNotFoundError:
    print("Prompt file not found, using default")
    prompt = "You are a helpful assistant."

agent = Agent("bot", system_prompt=prompt)
```

That's it! ConnectOnion makes it simple - just point to any text file and it works.