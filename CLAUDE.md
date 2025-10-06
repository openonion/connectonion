# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ConnectOnion is a Python framework for creating AI agents with behavior tracking. It's designed as an MVP with intentional simplicity, focusing on core agent functionality with OpenAI integration and automatic behavior recording.

## Architecture

### Core Components

- **Agent** (`connectonion/agent.py:10`): Main orchestrator that combines LLM calls with tool execution
- **Tool** (`connectonion/tools.py:9`): Abstract base class for all agent tools with built-in implementations
- **LLM** (`connectonion/llm.py:31`): Abstract interface with OpenAI implementation
- **Console** (`connectonion/console.py:15`): Terminal output and file logging

### Key Design Patterns

- **Tool Function Schema**: Tools automatically convert to OpenAI function calling format via `to_function_schema()`
- **Message Flow**: Agent maintains conversation history with tool results for multi-turn interactions
- **Automatic Logging**: All agent activities log to `.co/logs/{name}.log` by default (customizable)
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

## Documentation Architecture

### GitHub Wiki (SEO Strategy)

ConnectOnion uses a **nested Git repository** for the GitHub Wiki to gain SEO benefits from GitHub's high domain authority (DA ~95).

**Structure:**
```
connectonion/                    # Main repo
├── .git/                        # Main repo Git
├── .gitignore                   # Contains: wiki/
├── src/
├── docs/
└── wiki/                        # ← Ignored by main repo
    ├── .git/                    # ← Wiki repo Git (separate!)
    ├── Home.md
    ├── Quick-Start.md
    ├── Tutorials/
    ├── How-To/
    ├── Examples/
    ├── FAQ.md
    ├── Troubleshooting.md
    └── _Sidebar.md
```

**How It Works:**
- `wiki/` folder is added to `.gitignore` in main repo
- Wiki content is a completely separate Git repository cloned inside `wiki/`
- Each repo has independent history, remotes, and commits
- No sync scripts needed - each folder IS its own Git repo

**Editing Wiki Content:**
```bash
cd connectonion/wiki/
# Edit any wiki page
vim Quick-Start.md
# Commit to wiki repo
git add .
git commit -m "Update quick start guide"
git push origin master
```

**Working on Main Repo:**
```bash
cd connectonion/
# Edit code
vim connectonion/agent.py
# Commit to main repo (wiki/ is ignored!)
git add .
git commit -m "Add new feature"
git push
```

**SEO Benefits:**
- Multiple SERP entries: main repo + wiki + docs site (https://docs.connectonion.com)
- Fast indexing (hours vs weeks for new domains)
- High domain authority from github.com
- Cross-linking power between wiki and docs site
- Keyword coverage: 13 pages targeting different search intents

**Wiki URL:** https://github.com/wu-changxing/connectonion/wiki

### Docs Site (Private Repository)

ConnectOnion uses a **nested Git repository** for the documentation website to keep it private during development while maintaining convenience.

**Structure:**
```
connectonion/                    # Main repo (public)
├── .git/                        # Main repo Git
├── .gitignore                   # Contains: wiki/, docs-site/
├── src/
├── docs/
├── wiki/                        # ← Public wiki (nested repo)
└── docs-site/                   # ← Private docs site (nested repo)
    ├── .git/                    # ← Docs site repo Git (separate, private!)
    ├── app/
    ├── components/
    ├── public/
    ├── package.json
    └── next.config.ts
```

**How It Works:**
- `docs-site/` folder is added to `.gitignore` in main repo
- Docs site is a completely separate **private** Git repository
- Each repo has independent history, remotes, and commits
- No sync scripts needed - each folder IS its own Git repo

**Editing Docs Site:**
```bash
cd connectonion/docs-site/
# Edit any page
vim app/agent/page.tsx
# Commit to private docs-site repo
git add .
git commit -m "Update agent documentation"
git push origin main
```

**Working on Main Repo:**
```bash
cd connectonion/
# Edit code (docs-site/ is ignored!)
vim connectonion/agent.py
git add .
git commit -m "Add new feature"
git push
```

**Nested Repos Summary:**
- Main repo: `connectonion` (public) - Framework code
- Wiki repo: `connectonion.wiki` (public) - SEO-focused tutorials
- Docs site repo: `connectonion-docs-site` (private) - Full documentation website

**Docs site URL:** https://docs.connectonion.com
**Docs site repo:** https://github.com/wu-changxing/connectonion-docs-site (private)

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

### Tool Call Logging (`connectonion/console.py:45`)
Every tool execution is logged with:
- Timestamp and parameters passed to the tool
- Results (success/error/not_found status)
- Execution timing
- Complete activity log in `.co/logs/{name}.log` (default) or custom location

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
- **Doc Website UI Considerations**:
  - The doc website UI should always be one single column for user easy to read

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

## Documentation Guidelines

- When in the doc site introduce features, it always should start from core simple examples to add more things to it, think about a world-class tutorial, make it perfect
  - Focus on building tutorials that progressively introduce complexity
  - Start with the most minimal, straightforward use case
  - Gradually build up to more advanced scenarios
  - Ensure each step is clear, concise, and builds upon previous knowledge

## Version Numbering Strategy

**Version Strategy: Now in Production (0.0.4)**
- Current production version: 0.0.4
- Follow semantic versioning: increment PATCH by 1 until 10, then roll to MINOR
- See VERSIONING.md for detailed versioning rules and update checklist

### Command Block UI Pattern

When displaying terminal commands in the documentation site:

1. **Use the CommandBlock component** (`docs-site/components/CommandBlock.tsx`) for all terminal commands
2. **Never include $ signs in the copyable text** - the $ sign should be displayed visually but marked as `select-none`
3. **Implementation pattern**:
   ```tsx
   import { CommandBlock } from '../../components/CommandBlock'
   
   // Single command
   <CommandBlock commands={['pip install connectonion']} />
   
   // Multiple commands
   <CommandBlock 
     commands={[
       'mkdir my-project',
       'cd my-project',
       'co init'
     ]}
   />
   ```

4. **Visual design**:
   - $ signs are displayed in gray (`text-gray-500`) and non-selectable (`select-none`)
   - Commands have hover effect (`hover:bg-white/5`) to show interactivity
   - Copy button copies all commands without $ signs, joined with newlines
   - Shows green checkmark when successfully copied

5. **User benefits**:
   - Users can click copy button to get clean commands ready for terminal
   - Manual text selection won't accidentally grab $ signs
   - Multi-line commands are properly formatted for pasting

## Core Beliefs and Process Guidelines

### Core Beliefs
- Incremental progress over big bangs - Small changes that compile and pass tests
- Learning from existing code - Study and plan before implementing
- Pragmatic over dogmatic - Adapt to project reality
- Clear intent over clever code - Be boring and obvious

### Simplicity Means
- Single responsibility per function/class
- Avoid premature abstractions
- No clever tricks - choose the boring solution
- If you need to explain it, it's too complex

### Process
1. **Planning & Staging**
   - Break complex work into 3-5 stages
   - Document in IMPLEMENTATION_PLAN.md with clear goals, success criteria, and tests
   - Update status as progress is made
   - Remove file when all stages are complete

2. **Implementation Flow**
   - Understand - Study existing patterns in codebase
   - Test - Write test first (red)
   - Implement - Minimal code to pass (green)
   - Refactor - Clean up with tests passing
   - Commit - With clear message linking to plan

3. **When Stuck (After 3 Attempts)**
   - CRITICAL: Maximum 3 attempts per issue, then STOP
   - Document failures:
     * What was tried
     * Specific error messages
     * Hypothesized failure reasons
   - Research alternatives:
     * Find 2-3 similar implementations
     * Note different approaches
   - Question fundamentals:
     * Is this the right abstraction level?
     * Can this be split into smaller problems?
     * Is there a simpler approach?
   - Try different angles:
     * Different library/framework feature?
     * Different architectural pattern?
     * Remove abstraction instead of adding?

### Technical Standards
#### Architecture Principles
- Composition over inheritance - Use dependency injection
- Interfaces over singletons - Enable testing and flexibility
- Explicit over implicit - Clear data flow and dependencies
- Test-driven when possible - Never disable tests, fix them

#### Code Quality
- Every commit must:
  * Compile successfully
  * Pass all existing tests
  * Include tests for new functionality
  * Follow project formatting/linting
- Before committing:
  * Run formatters/linters
  * Self-review changes
  * Ensure commit message explains "why"

#### Error Handling
- Fail fast with descriptive messages
- Include context for debugging
- Handle errors at appropriate level
- Never silently swallow exceptions

### Decision Framework
When multiple valid approaches exist, choose based on:
- Testability - Can I easily test this?
- Readability - Will someone understand this in 6 months?
- Consistency - Does this match project patterns?
- Simplicity - Is this the simplest solution that works?
- Reversibility - How hard to change later?

### Project Integration
#### Learning the Codebase
- Find 3 similar features/components
- Identify common patterns and conventions
- Use same libraries/utilities when possible
- Follow existing test patterns

#### Tooling
- Use project's existing build system
- Use project's test framework
- Use project's formatter/linter settings
- Don't introduce new tools without strong justification

### Quality Gates
#### Definition of Done
- Tests written and passing
- Code follows project conventions
- No linter/formatter warnings
- Commit messages are clear
- Implementation matches plan
- No TODOs without issue numbers

#### Test Guidelines
- Test behavior, not implementation
- One assertion per test when possible
- Clear test names describing scenario
- Use existing test utilities/helpers
- Tests should be deterministic

### Important Reminders
#### NEVER
- Use --no-verify to bypass commit hooks
- Disable tests instead of fixing them
- Commit code that doesn't compile
- Make assumptions - verify with existing code

#### ALWAYS
- Commit working code incrementally
- Update plan documentation as you go
- Learn from existing implementations
- Stop after 3 failed attempts and reassess
- for the UI, always remember that:
Each code block, the left side is the code, and the right side is after running the code block. What's the result it will be?So basically, a left side called right side running result.