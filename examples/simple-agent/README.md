# Simple ConnectOnion Agent Example

This is a minimal example of using ConnectOnion with the OpenOnion managed keys.

## Quick Start

### Try Debug Mode in 10 Seconds

```bash
# Run the default debug demo - no configuration needed!
python agent_debug.py
```

This runs a default example task with breakpoints, showing you:
- How the debugger pauses at `@xray` decorated tools
- The execution context and results
- **The LLM's next planned action** (new feature!)

## Getting Started

### Running the Basic Agent

#### Option 1: Using OpenOnion Managed Keys (Recommended)

1. Authenticate with OpenOnion:
```bash
co auth
```

2. Run the agent (will automatically use co/o4-mini):
```bash
python agent.py
```

#### Option 2: Using Your Own API Keys

1. Set your OpenAI API key:
```bash
export OPENAI_API_KEY="sk-..."
```

2. Run the agent:
```bash
python agent.py
```

### Running the Debug Example

#### Default Example (no arguments)
Run without arguments to debug a default example task:
```bash
python agent_debug.py
# Runs: "Search for information about Python and format it"
```

#### Custom Task Mode
Pass your own task to debug:
```bash
python agent_debug.py "Search for debugging tips and save them"
```

#### Interactive Mode
Use the interactive flag for multiple tasks:
```bash
python agent_debug.py --interactive
# or
python agent_debug.py -i
```

Features:
- The agent will pause at tools decorated with `@xray`
- You can inspect tool arguments and results
- Interactive menu with arrow navigation
- Keyboard shortcuts: Press c/e/q + Enter for quick selection
- See the LLM's next planned action in real-time
- Interactive mode: Type 'quit' to exit
- Single task mode: Exits automatically after completion

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

### agent.py
- Creating an agent with tools
- Using function-based tools
- Making LLM calls with `llm_do`
- Automatic model selection based on authentication

### agent_debug.py
- Interactive debugging with `agent.auto_debug()`
- Using `@xray` decorator to mark breakpoint tools
- Default task when run without arguments
- Custom task mode with command line arguments
- Interactive mode with `--interactive` flag
- **NEW**: Real-time preview of LLM's next planned action
- Interactive menu with arrow navigation
- Edit tool results before continuing
- Shows complete execution flow from user prompt to result

## Testing

All tests are organized in the `tests/` directory:

### Debug Features Tests
```bash
# Run all debug tests
python tests/test_debug_features.py

# Run specific test
python tests/test_debug_features.py --test breakpoints
python tests/test_debug_features.py --test post-analysis
python tests/test_debug_features.py --test menu
python tests/test_debug_features.py --test preview

# Run demos
python tests/test_debug_features.py --demo quick
python tests/test_debug_features.py --demo preview
```

### API Integration Tests
```bash
# Run all API tests
python tests/test_api_integration.py

# Run specific test
python tests/test_api_integration.py --test auth
python tests/test_api_integration.py --test co-o4-mini
python tests/test_api_integration.py --test co-gpt4o
python tests/test_api_integration.py --test full
```

### Model-Specific Tests
```bash
# Run all model tests
python tests/test_models.py

# Run specific test
python tests/test_models.py --test gemini
python tests/test_models.py --test mock
python tests/test_models.py --test template
```

## Notes

- The agent will automatically detect if you have OpenOnion authentication and use managed keys
- All agent behaviors are tracked in `~/.connectonion/agents/minimal-agent/`
- The `co/o4-mini` model requires special parameters (max_completion_tokens, temperature=1)