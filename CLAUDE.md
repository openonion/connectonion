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

# Run specific test file
python -m unittest tests.test_agent
```

### Package Installation (Development)
```bash
pip install -e .
```

## Built-in Tools

- **Calculator**: Safe mathematical expression evaluation with restricted character set
- **CurrentTime**: Date/time formatting with strftime support
- **ReadFile**: UTF-8 file reading with error handling

## Key Implementation Details

### Agent Execution Loop
Agents use a controlled iteration loop (max 10) to prevent infinite tool calling. Each iteration processes all tool calls from the LLM response before continuing.

### Tool Call Recording
Every tool execution is tracked with parameters, results, status, and call ID for complete behavior history.

### Error Handling
Tool errors are captured and passed back to the LLM as tool responses, allowing the agent to adapt or retry.

### OpenAI Integration
Uses OpenAI's function calling with proper message formatting for tool results and multi-turn conversations.