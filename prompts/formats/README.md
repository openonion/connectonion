# Format Examples

This directory demonstrates that ConnectOnion supports **any text file format** for system prompts. The same prompt is provided in multiple formats to show the flexibility.

## Same Prompt, Different Formats

All these files contain the **exact same assistant prompt** in different formats:

- `assistant.md` - Markdown format (structured with headers)
- `assistant.yaml` - YAML format (key-value pairs)
- `assistant.json` - JSON format (structured data)
- `assistant.txt` - Plain text format
- `assistant` - No extension (still works!)

## Usage

You can use ANY of these files interchangeably:

```python
from connectonion import Agent

# All of these create the SAME agent with identical behavior:
agent1 = Agent("bot", system_prompt="prompts/formats/assistant.md")
agent2 = Agent("bot", system_prompt="prompts/formats/assistant.yaml")
agent3 = Agent("bot", system_prompt="prompts/formats/assistant.json")
agent4 = Agent("bot", system_prompt="prompts/formats/assistant.txt")
agent5 = Agent("bot", system_prompt="prompts/formats/assistant")  # No extension!
```

## Key Point

ConnectOnion **doesn't parse** these formats - it simply reads the text content and passes it to the LLM. This means:

- ✅ **Any text format works** - Use what you prefer
- ✅ **No parsing errors** - It's just text
- ✅ **Future-proof** - New formats work automatically
- ✅ **Simple** - No complex configuration schemas

The LLM interprets the content, whether it's structured (YAML/JSON) or narrative (Markdown/text).

## When to Use Each Format

- **Markdown (`.md`)** - Best for human-readable prompts with sections
- **YAML (`.yaml`)** - Good for configuration-style prompts
- **JSON (`.json`)** - Useful for programmatic generation or version control
- **Plain text (`.txt`)** - Simple, no-frills prompts
- **No extension** - Clean, minimal approach

Choose based on your team's preferences and tooling!