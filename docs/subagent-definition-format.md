# Sub-Agent Definition Format

## Design Goals

1. **Single file definition** - Config + prompt in one place
2. **Easy to create** - Simple YAML frontmatter + markdown
3. **Easy to load** - Standard format, auto-discovery
4. **Type-safe** - Clear schema for validation
5. **Self-documenting** - Examples embedded in the file

## File Format

```
subagents/
├── explore.md          # Exploration sub-agent
├── plan.md             # Planning sub-agent
├── debug.md            # Debug sub-agent
└── research.md         # Research sub-agent
```

Each file has:
1. **YAML frontmatter** - Configuration
2. **Markdown body** - System prompt

## Standard Format

```markdown
---
name: explore
description: Fast agent for exploring codebases and finding files
model: co/gemini-2.5-flash
max_iterations: 15
tools:
  - glob
  - grep
  - read_file
plugins: []
cost_optimization: true
read_only: true
examples:
  - prompt: "Find all API endpoints"
    expected_strategy: "glob for routes → grep for decorators → read handlers"
  - prompt: "How does authentication work?"
    expected_strategy: "grep for auth patterns → glob auth dirs → read key files"
---

# Explore Agent

You are a read-only exploration agent specialized in quickly understanding codebases.

## CRITICAL: READ-ONLY MODE

<system-reminder>
This is a READ-ONLY exploration agent. You are PROHIBITED from:
- Creating, modifying, or deleting files
- Moving, copying, or renaming files
- Creating temporary files
- Using redirect operators (>, >>)
- Any operation that changes the filesystem

You can ONLY use: glob, grep, read_file, and read-only bash commands.

This is a HARD CONSTRAINT, not a guideline.
</system-reminder>

## Your Mission

Find files, search code, and answer questions about codebase structure. Be fast and thorough.

## Strategy

1. **Start broad** - Use glob to find relevant files by pattern
2. **Narrow down** - Use grep to find specific content
3. **Read selectively** - Only read files that are directly relevant
4. **Summarize** - Return structured, actionable findings

## Output Format

Return your findings in a clear structure:

\```
## Files Found
- path/to/file1.py - Brief description
- path/to/file2.py - Brief description

## Key Findings
- Finding 1
- Finding 2

## Recommended Actions
- Action 1
- Action 2
\```

## Guidelines

- Be **fast** - Don't read every file, be selective
- Be **thorough** - Cover multiple search patterns
- Be **structured** - Return organized findings
- Be **concise** - No unnecessary explanation
- Be **read-only** - NEVER modify any files
```

## Loader Implementation

```python
# subagents/loader.py
"""Sub-agent definition loader with YAML frontmatter parsing."""

from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import re

@dataclass
class SubAgentDefinition:
    """Sub-agent configuration and prompt."""
    name: str
    description: str
    model: str
    max_iterations: int
    tools: List[str]
    plugins: List[str]
    system_prompt: str
    cost_optimization: bool = False
    read_only: bool = False
    examples: List[Dict[str, str]] = None

    def to_agent_config(self) -> Dict[str, Any]:
        """Convert to Agent constructor kwargs."""
        return {
            "name": f"subagent-{self.name}",
            "tools": self._resolve_tools(),
            "plugins": self._resolve_plugins(),
            "system_prompt": self.system_prompt,
            "model": self.model,
            "max_iterations": self.max_iterations,
        }

    def _resolve_tools(self) -> List:
        """Resolve tool names to actual tool functions."""
        from connectonion import glob, grep, read_file, write, edit, bash

        tool_registry = {
            "glob": glob,
            "grep": grep,
            "read_file": read_file,
            "write": write,
            "edit": edit,
            "bash": bash,
        }

        return [tool_registry[name] for name in self.tools if name in tool_registry]

    def _resolve_plugins(self) -> List:
        """Resolve plugin names to actual plugin objects."""
        # Plugins are always empty for sub-agents by design
        return []


def parse_subagent_file(file_path: Path) -> Optional[SubAgentDefinition]:
    """
    Parse a sub-agent definition file.

    Format:
        ---
        name: explore
        description: Fast codebase exploration
        model: co/gemini-2.5-flash
        max_iterations: 15
        tools: [glob, grep, read_file]
        plugins: []
        ---

        # System Prompt
        You are an exploration agent...
    """
    content = file_path.read_text(encoding="utf-8")

    # Match YAML frontmatter
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.+)', content, re.DOTALL)
    if not match:
        return None

    frontmatter_text, system_prompt = match.groups()

    # Parse YAML frontmatter (simple parser, no PyYAML dependency)
    config = {}
    for line in frontmatter_text.split('\n'):
        if ':' not in line:
            continue

        key, value = line.split(':', 1)
        key = key.strip()
        value = value.strip()

        # Handle lists: tools: [glob, grep, read_file]
        if value.startswith('[') and value.endswith(']'):
            items = value[1:-1].split(',')
            config[key] = [item.strip() for item in items]
        # Handle booleans
        elif value.lower() in ('true', 'false'):
            config[key] = value.lower() == 'true'
        # Handle integers
        elif value.isdigit():
            config[key] = int(value)
        else:
            config[key] = value

    return SubAgentDefinition(
        name=config.get('name', file_path.stem),
        description=config.get('description', ''),
        model=config.get('model', 'co/gemini-2.5-flash'),
        max_iterations=config.get('max_iterations', 15),
        tools=config.get('tools', []),
        plugins=config.get('plugins', []),
        system_prompt=system_prompt.strip(),
        cost_optimization=config.get('cost_optimization', False),
        read_only=config.get('read_only', False),
        examples=config.get('examples'),
    )


def discover_subagents(subagents_dir: Path) -> Dict[str, SubAgentDefinition]:
    """
    Discover all sub-agent definitions in directory.

    Returns:
        Dict mapping agent name to SubAgentDefinition
    """
    if not subagents_dir.exists():
        return {}

    definitions = {}

    for file_path in subagents_dir.glob("*.md"):
        definition = parse_subagent_file(file_path)
        if definition:
            definitions[definition.name] = definition

    return definitions


# Global registry
_SUBAGENT_DEFINITIONS: Dict[str, SubAgentDefinition] = {}


def load_subagents(subagents_dir: Optional[Path] = None) -> Dict[str, SubAgentDefinition]:
    """Load all sub-agent definitions."""
    global _SUBAGENT_DEFINITIONS

    if subagents_dir is None:
        # Default to package subagents directory
        subagents_dir = Path(__file__).parent / "definitions"

    _SUBAGENT_DEFINITIONS = discover_subagents(subagents_dir)
    return _SUBAGENT_DEFINITIONS


def get_subagent_definition(name: str) -> Optional[SubAgentDefinition]:
    """Get a sub-agent definition by name."""
    if not _SUBAGENT_DEFINITIONS:
        load_subagents()

    return _SUBAGENT_DEFINITIONS.get(name)
```

## Factory Implementation

```python
# subagents/factory.py
"""Sub-agent factory using definition files."""

from typing import Optional
from pathlib import Path
from connectonion import Agent
from .loader import load_subagents, get_subagent_definition


def create_subagent(agent_type: str) -> Optional[Agent]:
    """
    Create a sub-agent from definition file.

    Args:
        agent_type: Name of sub-agent (e.g., "explore", "plan")

    Returns:
        Configured Agent instance or None if not found
    """
    definition = get_subagent_definition(agent_type)

    if not definition:
        return None

    # Convert definition to Agent kwargs
    config = definition.to_agent_config()

    return Agent(**config)


# Initialize on import
load_subagents()
```

## Tool Interface

```python
# subagents/__init__.py
"""Sub-agent task delegation."""

from typing import Literal, get_args
from .factory import create_subagent
from .loader import load_subagents, _SUBAGENT_DEFINITIONS


def get_available_agent_types() -> tuple:
    """Get available sub-agent types dynamically."""
    if not _SUBAGENT_DEFINITIONS:
        load_subagents()
    return tuple(_SUBAGENT_DEFINITIONS.keys())


# Dynamic Literal type based on available definitions
AgentType = Literal[get_available_agent_types()]


def task(
    prompt: str,
    agent_type: str = "explore",  # Can't use AgentType here due to runtime limitation
) -> str:
    """
    Delegate a task to a specialized sub-agent.

    Available agent types are automatically discovered from subagents/definitions/*.md

    Args:
        prompt: Task description (must be self-contained with full context)
        agent_type: Type of sub-agent (see available types below)

    Returns:
        Sub-agent's response

    Available Types:
    """
    # Build docstring dynamically
    if not _SUBAGENT_DEFINITIONS:
        load_subagents()

    if agent_type not in _SUBAGENT_DEFINITIONS:
        available = ", ".join(_SUBAGENT_DEFINITIONS.keys())
        return f"Error: Unknown agent type '{agent_type}'. Available: {available}"

    subagent = create_subagent(agent_type)
    if subagent is None:
        return f"Error: Failed to create {agent_type} agent"

    # Optional: Add visual feedback
    definition = _SUBAGENT_DEFINITIONS[agent_type]
    print(f"  ▶ Task ({agent_type}): {definition.description}")
    print(f"    Model: {definition.model} | Cost optimized: {definition.cost_optimization}")

    result = subagent.input(prompt)

    print(f"  ◀ Task completed")

    return result


__all__ = ["task", "load_subagents", "get_available_agent_types"]
```

## Example Definitions

### explore.md
```markdown
---
name: explore
description: Fast agent for exploring codebases and finding files
model: co/gemini-2.5-flash
max_iterations: 15
tools: [glob, grep, read_file]
plugins: []
cost_optimization: true
read_only: true
---

# Explore Agent

You are a read-only exploration agent specialized in quickly understanding codebases.

[Full prompt as shown above...]
```

### plan.md
```markdown
---
name: plan
description: Design implementation plans and architecture strategies
model: co/gemini-2.5-pro
max_iterations: 10
tools: [glob, grep, read_file]
plugins: []
cost_optimization: false
read_only: true
---

# Plan Agent

You are a planning agent specialized in designing implementation strategies.

[Full prompt as shown above...]
```

### debug.md
```markdown
---
name: debug
description: Analyze errors and suggest fixes
model: co/gemini-2.5-pro
max_iterations: 20
tools: [glob, grep, read_file, bash]
plugins: []
cost_optimization: false
read_only: false
---

# Debug Agent

You are a debugging agent specialized in analyzing errors and suggesting fixes.

## Your Mission

Analyze error messages, trace execution, identify root causes, and suggest fixes.

## Tools Available

- `glob` - Find files by pattern
- `grep` - Search file contents
- `read_file` - Read file contents
- `bash` - Run read-only commands (git log, git diff, ls, cat)

## Strategy

1. **Understand the error** - Read the error message carefully
2. **Find relevant code** - Use grep and glob to locate related files
3. **Analyze context** - Read surrounding code
4. **Identify root cause** - Trace execution flow
5. **Suggest fix** - Provide specific code changes

## Output Format

\```
## Error Analysis
- What: Brief description of the error
- Where: File and line number
- Why: Root cause explanation

## Root Cause
Detailed explanation of what's causing the issue

## Suggested Fix
Specific code changes to resolve the issue

## Testing Strategy
How to verify the fix works
\```
```

### research.md
```markdown
---
name: research
description: Research topics using web search and documentation
model: co/gemini-2.5-pro
max_iterations: 20
tools: [WebFetch]
plugins: []
cost_optimization: false
read_only: true
---

# Research Agent

You are a research agent specialized in finding information from web sources.

## Your Mission

Search the web, read documentation, summarize findings, and provide actionable insights.

## Strategy

1. **Understand the question** - What exactly needs to be researched?
2. **Search broadly** - Use WebFetch to find multiple sources
3. **Read critically** - Evaluate source quality
4. **Synthesize** - Combine information from multiple sources
5. **Summarize** - Return clear, actionable findings

## Output Format

\```
## Summary
One-paragraph overview of findings

## Key Information
- Point 1
- Point 2
- Point 3

## Sources
- [Title](URL) - Brief description
- [Title](URL) - Brief description

## Recommendations
- Recommendation 1
- Recommendation 2
\```
```

## Usage Example

```python
from connectonion import Agent, task

# Create main agent with task tool
agent = Agent(
    name="coder",
    tools=[task, glob, grep, read_file, write, edit],
    system_prompt="You are a coding agent. Use task() for complex exploration.",
)

# Agent uses sub-agents automatically
agent.input("Find all authentication-related files")
# → Internally calls: task("Find all files with auth, login, session", "explore")

agent.input("How should I add refresh tokens?")
# → Internally calls: task("Design a plan to add refresh token mechanism", "plan")

agent.input("Why is my API returning 500 errors?")
# → Internally calls: task("Analyze 500 error in API endpoint", "debug")

agent.input("What are best practices for JWT security?")
# → Internally calls: task("Research JWT security best practices", "research")
```

## Benefits of This Format

1. **Single file** - Config + prompt together, easy to version control
2. **Auto-discovery** - Just drop a new .md file in subagents/definitions/
3. **No code changes** - Add new sub-agents without touching code
4. **Self-documenting** - Examples and description in frontmatter
5. **Type-safe** - YAML schema validation possible
6. **Easy to share** - Copy .md file to share sub-agent
7. **Git-friendly** - Text files, easy to diff and merge
8. **IDE support** - Syntax highlighting for markdown
9. **Hot reload** - Can reload definitions without restart
10. **Testable** - Examples in frontmatter can be automated tests

## Directory Structure

```
your_sdk/
├── subagents/
│   ├── __init__.py              # task() function
│   ├── loader.py                # Parse .md files
│   ├── factory.py               # Create Agent instances
│   └── definitions/             # Sub-agent definitions
│       ├── explore.md           # Exploration agent
│       ├── plan.md              # Planning agent
│       ├── debug.md             # Debug agent
│       └── research.md          # Research agent
└── __init__.py                  # Export task to public API
```

## Validation Schema

```python
# subagents/schema.py
"""Validation schema for sub-agent definitions."""

from typing import List, Optional
from pydantic import BaseModel, Field, validator


class Example(BaseModel):
    prompt: str
    expected_strategy: str


class SubAgentSchema(BaseModel):
    """Schema for sub-agent YAML frontmatter."""

    name: str = Field(..., description="Unique agent identifier")
    description: str = Field(..., description="One-line description")
    model: str = Field(default="co/gemini-2.5-flash", description="LLM model")
    max_iterations: int = Field(default=15, ge=1, le=100)
    tools: List[str] = Field(default_factory=list)
    plugins: List[str] = Field(default_factory=list)
    cost_optimization: bool = Field(default=False)
    read_only: bool = Field(default=False)
    examples: Optional[List[Example]] = None

    @validator('tools')
    def validate_tools(cls, v):
        """Validate tool names."""
        valid_tools = {'glob', 'grep', 'read_file', 'write', 'edit', 'bash', 'WebFetch'}
        invalid = set(v) - valid_tools
        if invalid:
            raise ValueError(f"Invalid tools: {invalid}")
        return v

    @validator('model')
    def validate_model(cls, v):
        """Validate model name."""
        valid_prefixes = ('co/', 'gpt-', 'claude-', 'gemini-')
        if not any(v.startswith(prefix) for prefix in valid_prefixes):
            raise ValueError(f"Invalid model: {v}")
        return v
```

## CLI Command

```bash
# List available sub-agents
co subagents list

# Output:
# Available sub-agents:
#   explore   - Fast agent for exploring codebases
#   plan      - Design implementation plans
#   debug     - Analyze errors and suggest fixes
#   research  - Research topics using web search

# Validate a sub-agent definition
co subagents validate subagents/definitions/explore.md

# Create new sub-agent from template
co subagents create my-agent

# Test a sub-agent
co subagents test explore "Find all API endpoints"
```

This format makes sub-agents **easy to create, share, and maintain** while keeping everything in standard markdown files.
