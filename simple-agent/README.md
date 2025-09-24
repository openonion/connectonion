# Simple ConnectOnion Agent Example

This is a minimal example of using ConnectOnion with the OpenOnion managed keys.

## Quick Start

### Option 1: Using OpenOnion Managed Keys (Recommended)

1. Authenticate with OpenOnion:
```bash
co auth
```

2. Run the agent (will automatically use co/o4-mini):
```bash
python agent.py
```

### Option 2: Using Your Own API Keys

1. Set your OpenAI API key:
```bash
export OPENAI_API_KEY="sk-..."
```

2. Run the agent:
```bash
python agent.py
```

## Available Models

When using OpenOnion managed keys (after `co auth`):
- `co/gpt-4o` - GPT-4 Optimized
- `co/o4-mini` - OpenAI's newest reasoning model (default)
- `co/claude-3-haiku` - Claude 3 Haiku
- And more...

When using your own API keys:
- `gpt-4o` - GPT-4 Optimized
- `gpt-4o-mini` - GPT-4 Optimized Mini (default)
- `claude-3-5-sonnet-20241022` - Claude 3.5 Sonnet
- And more...

## Customizing the Model

You can override the model using the MODEL environment variable:

```bash
# Use a specific OpenOnion model
MODEL="co/gpt-4o" python agent.py

# Use your own API key with a specific model
OPENAI_API_KEY="sk-..." MODEL="gpt-4-turbo" python agent.py
```

## Features Demonstrated

- Creating an agent with tools
- Using function-based tools
- Making LLM calls with `llm_do`
- Automatic model selection based on authentication

## Notes

- The agent will automatically detect if you have OpenOnion authentication and use managed keys
- All agent behaviors are tracked in `~/.connectonion/agents/minimal-agent/`
- The `co/o4-mini` model requires special parameters (max_completion_tokens, temperature=1)