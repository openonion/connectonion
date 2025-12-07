# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ConnectOnion is a Python framework for creating AI agents with automatic activity logging, interactive debugging, and multi-agent collaboration. Philosophy: **"Keep simple things simple, make complicated things possible"** - simple 2-line agent creation, but production-ready with trust verification, event system, and plugin architecture.

## Architecture

### Core Components

- **Agent** (`connectonion/agent.py:29`): Main orchestrator with LLM integration, tool execution, event system, and trust verification
- **LLM** (`connectonion/llm.py:11`): Unified abstraction supporting OpenAI, Anthropic, Gemini, and managed keys via factory pattern
- **Tool Executor** (`connectonion/tool_executor.py:24`): Executes tools with xray context injection, timing, error handling, and trace recording
- **Tool Factory** (`connectonion/tool_factory.py`): Converts Python functions to OpenAI-compatible tool schemas automatically
- **Logger** (`connectonion/logger.py`): Unified logging facade (terminal + plain text + YAML sessions) with `quiet` and `log` parameters
- **Console** (`connectonion/console.py`): Low-level terminal output with Rich formatting (used internally by Logger)
- **Events** (`connectonion/events.py:11`): Lifecycle hooks (after_user_input, before_llm, after_llm, before_each_tool, before_tools, after_each_tool, after_tools, on_error, on_complete)
- **Trust System** (`connectonion/trust.py:42`): Three-level verification (open/careful/strict) with custom policy support
- **XRay Debug** (`connectonion/xray.py:32`): Runtime context injection for interactive debugging with `@xray` decorator

### Key Design Patterns

#### Tool System
- **Function-based (recommended)**: Regular Python functions auto-convert to tools via type hints and docstrings
- **Class-based (legacy)**: Inherit from `Tool` base class with explicit schemas
- Auto-conversion: `create_tool_from_function()` inspects signatures and generates OpenAI schemas

#### Agent Execution Loop (`connectonion/agent.py:input()`)
1. Initialize/extend session with user input
2. Fire `after_user_input` event
3. Loop (max_iterations times):
   - Fire `before_llm` event
   - Call LLM with messages and tool schemas
   - Fire `after_llm` event
   - If tool_calls: execute via `tool_executor.execute_and_record_tools()`
   - Fire `before_tools` event ONCE before ALL tools execute
   - Fire `before_each_tool` and `after_each_tool` events per individual tool
   - Fire `after_tools` event ONCE after ALL tools complete (safe for adding messages)
   - Add results to messages, continue
4. Return final response or iteration limit message

#### Multi-LLM Provider Architecture (`connectonion/llm.py`)
- Factory pattern: `create_llm(model, api_key)` routes to provider classes
- OpenAI format as lingua franca (all providers convert to/from)
- Structured output: Each provider uses native API (OpenAI's `parse()`, Anthropic's forced tool calling, Gemini's `response_schema`)
- Tool calling: Unified `ToolCall` dataclass format across all providers

#### Event System & Plugins (`connectonion/events.py`)
- Wrapper functions tag handlers with `_event_type` attribute
- Plugins are lists of event handlers bundled together
- Handlers receive `agent` instance, can modify `current_session`
- Built-in plugins: reflection, ReAct, image_result_formatter

#### Trust Verification (`connectonion/trust.py`)
- Three levels: "open" (dev), "careful" (staging), "strict" (prod)
- Custom policies: markdown files or inline text describing verification rules
- Custom agents: Pass your own Agent instance with verification tools
- Environment-based defaults: `CONNECTONION_ENV` sets trust level automatically

#### XRay Debugging (`connectonion/xray.py`)
- `@xray` decorator injects context: `xray.agent`, `xray.task`, `xray.messages`, `xray.iteration`
- `xray.trace()` displays formatted execution history
- `inject_xray_context()` in `tool_executor.py:24` provides runtime context
- Enables interactive debugging with `agent.auto_debug()`

## Development Commands

### Installation
```bash
pip install -r requirements.txt
pip install -e .  # Development mode
```

### Testing
```bash
# Run all tests except real API calls (default)
python -m pytest

# Run specific test categories
python -m pytest tests/unit           # Unit tests (fast, mocked)
python -m pytest tests/integration    # Integration tests (no external APIs)
python -m pytest tests/cli            # CLI tests
python -m pytest tests/e2e            # End-to-end example agent

# Run real API tests (requires keys)
python -m pytest tests/real_api -m real_api

# Run with coverage
python -m pytest --cov=connectonion --cov-report=term-missing

# Run single test file
python -m pytest tests/unit/test_agent.py
python -m pytest tests/unit/test_agent.py::test_specific_function
```

### CLI Commands
```bash
# Create new agent project
co create my-agent                    # Minimal template (default)
co create my-bot --template playwright    # Browser automation
co create emailer --template email-agent  # Email automation

# Available templates: minimal, playwright, email-agent, meta-agent, web-research

# Initialize in existing directory
co init                               # Add .co folder only
co init --template minimal           # Add full template

# Authentication (for managed keys)
co auth login                         # Interactive login
co auth status                        # Check auth status
co auth logout                        # Logout

# OAuth integrations (for email/calendar tools)
co auth google                        # Connect Google (Gmail, Calendar)
co auth microsoft                     # Connect Microsoft (Outlook, Calendar)

# Browser automation
co browser                            # Launch browser agent

# Diagnostics
co doctor                             # Check installation
co status                             # Show project status
```

### Building & Publishing
```bash
# Build package
python setup.py sdist bdist_wheel

# Publish to PyPI
twine upload dist/*

# Version update (see VERSIONING.md)
# Current: 0.4.1
# Strategy: increment PATCH (0.4.1 → 0.4.2), roll to MINOR at .10 (0.4.10 → 0.5.0)
```

## Project Structure

```
connectonion/
├── connectonion/
│   ├── __init__.py                 # Main exports
│   ├── agent.py                    # Agent class with event system
│   ├── llm.py                      # Multi-provider LLM abstraction
│   ├── tool_executor.py            # Tool execution with xray
│   ├── tool_factory.py             # Function → tool conversion
│   ├── logger.py                   # Unified logging facade (terminal + file + YAML sessions)
│   ├── console.py                  # Low-level terminal output with Rich
│   ├── events.py                   # Event system
│   ├── trust.py                    # Trust system coordinator
│   ├── trust_agents.py             # Trust prompts
│   ├── trust_functions.py          # Trust verification tools
│   ├── xray.py                     # XRay debugging
│   ├── decorators.py               # @replay, @xray_replay
│   ├── llm_do.py                   # One-shot LLM function
│   ├── prompts.py                  # Prompt loading utilities
│   ├── connect.py                  # Multi-agent networking
│   ├── relay.py                    # Agent relay server
│   ├── announce.py                 # Service announcement
│   ├── address.py                  # Agent addressing
│   ├── auto_debug_exception.py     # Exception debugging
│   ├── cli/
│   │   ├── main.py                 # CLI entry point
│   │   ├── commands/               # CLI command implementations
│   │   └── templates/              # Agent templates
│   │       ├── minimal/
│   │       ├── playwright/
│   │       ├── email-agent/
│   │       ├── meta-agent/
│   │       └── web-research/
│   ├── useful_tools/               # Built-in tools
│   │   ├── send_email.py
│   │   └── get_emails.py
│   ├── useful_plugins/             # Built-in plugins
│   │   ├── reflection.py
│   │   ├── react.py
│   │   └── image_result_formatter.py
│   ├── debug_agent/                # Interactive debugger
│   ├── debug_explainer/            # Debug explanation agent
│   └── execution_analyzer/         # Execution analysis
├── tests/
│   ├── unit/                       # Fast, isolated tests
│   ├── integration/                # Multi-component tests
│   ├── real_api/                   # Tests requiring API keys
│   ├── cli/                        # CLI command tests
│   └── e2e/                        # End-to-end examples
├── docs/                           # Markdown documentation
├── wiki/                           # GitHub Wiki (nested repo)
├── docs-site/                      # Next.js docs site (nested repo, private)
├── examples/                       # Example agents
├── prompts/                        # System prompt templates
├── setup.py                        # Package configuration
├── pytest.ini                      # Test configuration
└── requirements.txt                # Dependencies
```

## Key Implementation Details

### Agent Session Management (`connectonion/agent.py`)
- `current_session`: Runtime-only context with `messages`, `trace`, `turn`, `iteration`
- Session persists across turns for multi-turn conversations
- `tools`: ToolRegistry with O(1) lookup via `.get()` or attribute access (`agent.tools.tool_name`)
- Class instances accessible via `agent.tools.instance_name` (e.g., `agent.tools.gmail`)
- Default model: `co/o4-mini` (managed keys via OpenOnion proxy)

### LLM Provider Routing (`connectonion/llm.py:create_llm()`)
- Model prefix determines provider:
  - `gpt-*` → OpenAI
  - `claude-*` or `anthropic.*` → Anthropic
  - `gemini-*` or `models/gemini-*` → Google
  - `co/*` → OpenOnion managed keys (OpenAI proxy)
- API keys from environment or parameter
- Structured output via provider-native APIs

### Tool Execution Flow (`connectonion/tool_executor.py`)
1. Add assistant message with tool_calls to session
2. For each tool:
   - `inject_xray_context()` provides runtime context
   - Execute tool function with arguments
   - Record timing and result in trace
   - Clear xray context
   - Add tool result message
3. Fire `before_each_tool` and `after_each_tool` events per tool, then `after_tools` once after all
4. Handle errors: capture in trace, return to LLM for retry

### Trust Verification (`connectonion/trust.py`)
- Environment defaults: `CONNECTONION_ENV=development` → trust="open"
- Custom policies loaded from markdown files or inline strings
- Trust agent created lazily when trust parameter provided
- Prevents infinite recursion: trust agents don't have their own trust agents

### XRay Context Injection (`connectonion/xray.py`)
- Stores context in `builtins.xray` global object
- Thread-safe via thread-local storage
- Tools access: `xray.agent`, `xray.task`, `xray.messages`, `xray.iteration`, `xray.previous_tools`
- `xray.trace()` displays Rich-formatted execution history

### Logging System (`connectonion/logger.py`)
- **Logger class**: Unified facade for terminal output + plain text + YAML sessions
- **Console output**: Rich-formatted terminal output (unless `quiet=True`)
- **Plain text logs**: `.co/logs/{agent_name}.log` (automatic audit trail)
- **YAML sessions**: `.co/sessions/{agent_name}_{timestamp}.yaml` (for eval/replay)
- **Parameters**:
  - `quiet=True`: Suppress console output, keep session logging
  - `log=False`: Disable all logging (console still shows)
  - `log="path/to/file.log"`: Custom log file path
- Environment variable: `CONNECTONION_LOG` (highest priority)
- Session format: Per-turn tracking with input, model, duration_ms, tokens, cost, tools_called, result, messages (JSON)
- Use cases:
  - Development (default): `Agent("name")` - everything on
  - Eval/testing: `Agent("name", quiet=True)` - sessions only
  - Benchmarking: `Agent("name", log=False)` - nothing

## Test Organization

### Folder Structure (see `tests/TEST_ORGANIZATION.md`)
- `tests/unit/` - One test file per source file, mocked dependencies, fast (<1s)
- `tests/integration/` - Multi-component tests, no external APIs, medium speed
- `tests/real_api/` - Actual API calls, requires keys, slow (5-30s), costs money
- `tests/cli/` - CLI command tests, file system operations
- `tests/e2e/` - Complete example agent (living documentation)

### Running Tests
```bash
# Fast feedback loop (unit + integration only)
pytest -m "not real_api"

# Test specific module
pytest tests/unit/test_agent.py

# Real API tests (set API keys first)
export OPENAI_API_KEY=sk-...
pytest tests/real_api/test_real_openai.py -m real_api

# All tests except real API (default, for CI)
pytest
```

### Test Markers
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.real_api` - Requires API keys
- `@pytest.mark.cli` - CLI tests
- `@pytest.mark.slow` - Takes >10 seconds
- `@pytest.mark.network` - Requires network/relay

## Documentation Architecture

### Three-Layer Strategy
1. **GitHub Wiki** (public, SEO-focused): Nested repo at `wiki/`, targets search keywords
2. **Docs Website** (private during dev): Nested repo at `docs-site/`, Next.js site at https://docs.connectonion.com
3. **Main Repo Docs** (public): Markdown files in `docs/` folder

### Nested Repository Pattern
Both wiki and docs-site are separate Git repositories inside the main repo:

```bash
# Wiki editing (public)
cd wiki/
git add .
git commit -m "Update tutorial"
git push origin master

# Docs site editing (private)
cd docs-site/
git add .
git commit -m "Update agent page"
git push origin main

# Main repo (ignores both)
cd connectonion/
git add .
git commit -m "Add feature"
git push
```

**Important:** Both `wiki/` and `docs-site/` are in `.gitignore` - they are independent repos.

### Documentation Guidelines
- Start with minimal examples, progressively add complexity
- Show real working code with actual output
- One concept per page (progressive disclosure)
- Mobile-friendly, scannable structure
- Command blocks use `CommandBlock` component (no $ in copy text)
- Each page has "copy all as markdown" button

## Common Development Tasks

### Adding a New Tool
1. Write function with type hints and docstring
2. Pass to Agent: `agent = Agent("name", tools=[my_tool])`
3. Tool auto-converts via `create_tool_from_function()`

### Adding a New Event Handler
1. Import wrapper: `from connectonion import after_tools`
2. Define handler: `def my_handler(agent): ...`
3. Register: `agent = Agent("name", on_events=[after_tools(my_handler)])`

### Creating a Plugin
1. Define event handlers
2. Bundle in list: `my_plugin = [after_tools(handler1), before_llm(handler2)]`
3. Use: `agent = Agent("name", plugins=[my_plugin])`

### Adding a CLI Command
1. Create command in `connectonion/cli/commands/`
2. Import in `connectonion/cli/main.py`
3. Add to CLI group with `@cli.command()`

### Adding a CLI Template
1. Create folder in `connectonion/cli/templates/{template-name}/`
2. Add `agent.py`, `.env.example`, prompt files
3. Update `setup.py` package_data to include template files
4. Test: `co create test-project --template {template-name}`

### Adding LLM Provider Support
1. Implement class inheriting from `LLM` in `connectonion/llm.py`
2. Implement `complete()` and `structured_complete()` methods
3. Add routing logic to `create_llm()` factory function
4. Add tests in `tests/real_api/test_real_{provider}.py`

## Version Numbering Strategy

**Current Version:** 0.4.1 (Production Ready)

**Strategy:** Semantic versioning with specific rollover rules
- Increment PATCH: 0.4.1 → 0.4.2 → ... → 0.4.9
- At .10, roll to MINOR: 0.4.10 → 0.5.0
- At .10.0, roll to MAJOR: 0.10.0 → 1.0.0

**Update Checklist:** See `VERSIONING.md` for complete steps (update `setup.py`, `__init__.py`, create git tag, update CHANGELOG.md)

## Philosophy & Principles

### Core Philosophy
**"Keep simple things simple, make complicated things possible"**
- Simple: 2-line agent creation (`Agent("name").input("query")`)
- Complicated: Trust verification, multi-agent networking, custom LLM providers, plugin system

### Design Principles
1. **Function as Primitive**: Everything is a function (agents, tools, trust, events)
2. **The 100-Line Test**: If a feature needs >100 lines, it's too complex
3. **Behavior Over Identity**: Trust earned through action, not authority
4. **Simplicity Enables Robustness**: Complex systems are fragile

### Code Quality Standards
- **Single responsibility** per function/class
- **Avoid premature abstractions** - wait until you need it 3 times
- **No clever tricks** - choose the boring solution
- **Explicit over implicit** - clear data flow and dependencies
- **Test behavior, not implementation**

### Error Handling Philosophy
- **Fail fast** with descriptive messages
- **Include context** for debugging
- **Let errors bubble** to agent for retry
- **Never silently swallow exceptions**
- **No try-except-pass** unless explicitly required

### Process Guidelines
1. **Planning**: Break complex work into 3-5 stages in IMPLEMENTATION_PLAN.md
2. **Implementation**: Test first (red) → Minimal code (green) → Refactor → Commit
3. **When Stuck**: Max 3 attempts, then document failures and try different approach
4. **Definition of Done**: Tests pass, follows conventions, no TODOs, documentation updated

## Important Reminders

### NEVER
- Use `--no-verify` to bypass commit hooks
- Disable tests instead of fixing them
- Commit code that doesn't compile
- Add try-except-pass without explicit requirement
- Use utils.py or helper.py (keep helpers with features)

### ALWAYS
- Commit working code incrementally
- Let programs crash to see errors (avoid try-except)
- Keep functions under 30 lines when possible
- Use existing test patterns from codebase
- Remind user to update documentation for user-facing features:
  - GitHub Wiki: `cd wiki/ && git commit && git push`
  - Docs Website: `cd docs-site/ && git commit && git push`
  - Main docs: `docs/` folder

### Code Organization Preferences
- Avoid `utils.py` - keep helper functions with their features
- Default model for agents: `co/o4-mini` (production), `o4-mini` (testing)
- No co-authoring with Claude Code in commit messages
- Function-based tools over class-based tools
- Events/plugins over subclassing Agent

## Community & Support

- **Documentation**: https://docs.connectonion.com
- **Discord**: https://discord.gg/4xfD9k8AUF
- **GitHub**: https://github.com/openonion/connectonion
- **PyPI**: https://pypi.org/project/connectonion/
