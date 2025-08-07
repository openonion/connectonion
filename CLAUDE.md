# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ConnectOnion is a Python framework for creating AI agents with behavior tracking. It's designed as an MVP with intentional simplicity, focusing on core agent functionality with OpenAI integration and automatic behavior recording.

## Architecture

### Core Components

- **Agent** (`connectonion/agent.py:10`): Main orchestrator that combines LLM calls with tool execution
- **Tool** (`connectonion/tools.py:9`): Abstract base class for all agent tools with built-in implementations
- **LLM** (`connectonion/llm.py:31`): Abstract interface with OpenAI implementation
- **History** (`connectonion/history.py:24`): Automatic behavior tracking and persistence

### Key Design Patterns

- **Tool Function Schema**: Tools automatically convert to OpenAI function calling format via `to_function_schema()`
- **Message Flow**: Agent maintains conversation history with tool results for multi-turn interactions
- **Automatic Persistence**: All agent behaviors save to `~/.connectonion/agents/{name}/behavior.json`
- **Tool Mapping**: Agents maintain internal `tool_map` for O(1) tool lookup during execution

## Development Commands

### Installation
```bash
pip install -r requirements.txt
```

### Testing
```bash
# Run all tests
python -m pytest tests/

# Run specific test categories with markers
python -m pytest -m unit          # Unit tests only
python -m pytest -m integration   # Integration tests only
python -m pytest -m benchmark     # Performance benchmarks
python -m pytest -m "not real_api"  # Skip tests requiring API keys

# Run specific test file
python -m unittest tests.test_agent

# Run tests with coverage (if pytest-cov installed)
python -m pytest --cov=connectonion --cov-report=term-missing
```

### Package Installation (Development)
```bash
pip install -e .
```

## Tool System Architecture

### Function-Based Tools (Recommended)
ConnectOnion's primary tool approach converts regular Python functions into agent tools automatically:

```python
def my_tool(param: str, optional_param: int = 10) -> str:
    """This docstring becomes the tool description."""
    return f"Processed {param} with value {optional_param}"

# Auto-conversion via create_tool_from_function()
agent = Agent("assistant", tools=[my_tool])
```

The `create_tool_from_function()` utility (`connectonion/tools.py:16`) inspects function signatures and type hints to generate OpenAI-compatible schemas.

### Traditional Tool Classes (Legacy Support)
Class-based tools inherit from the abstract `Tool` base class and implement `run()` method and parameter schemas.

## Key Implementation Details

### Agent Execution Loop (`connectonion/agent.py:47`)
Agents use a controlled iteration loop (max 10) to prevent infinite tool calling. Each iteration:
1. Calls LLM with current message history and tool schemas
2. Processes ALL tool calls from the response in parallel
3. Adds tool results to message history
4. Continues until no more tool calls or max iterations reached

### Function Tool Auto-Conversion (`connectonion/tools.py:16`)
The `create_tool_from_function()` utility:
- Inspects function signatures using `inspect.signature()`
- Maps Python types to JSON Schema types via `TYPE_MAP`
- Generates OpenAI-compatible function schemas
- Attaches `.name`, `.description`, `.run()`, and `.to_function_schema()` attributes

### Tool Call Recording (`connectonion/history.py:43`)
Every tool execution is tracked with:
- Parameters passed to the tool
- Results (success/error/not_found status)
- Call ID for correlation
- Complete behavior history in `~/.connectonion/agents/{name}/behavior.json`

### Error Handling
Tool errors are captured and passed back to the LLM as tool responses, allowing the agent to adapt or retry. Missing tools return "not_found" status.

### OpenAI Integration (`connectonion/llm.py:51`)
Uses OpenAI's function calling with proper message formatting:
- Assistant messages include all tool_calls
- Individual tool responses use tool_call_id for correlation
- Supports multi-turn conversations with tool context

## Design Considerations

- **Page Design Approach**: 
  - For each page, we should customize the design based on the specific document content
  - We will not use the same template for all docs
- **Doc Site Page Feature Design**:
  - For each feature of doc site page, we should according to content to design the page
  - All pages should have a button to copy all content in markdown format, so users can easily send to their AI platform

## Collaboration Guidelines

- When discussing the new design of the agent/features:
  - Always show how the user experience looks like first
  - Discuss the UX details before making any code updates
  - Only proceed with code updates after user agreement on the UX design

## Common Errors and Troubleshooting

### Frontend Parsing Errors
- When using JSX/TSX, be careful with special characters like `>` in template literals or code snippets
  - Use `&gt;` or `{'>'}` instead of raw `>` to avoid parsing errors in `./app/xray/page.tsx`
  - Specifically for code display, ensure proper escaping of special characters
  - Example error source: Unexpected token parsing near code display blocks with unescaped `>` symbol