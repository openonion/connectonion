# Sub-Agent System

Simple, file-based sub-agent definitions using markdown with YAML frontmatter.

## Quick Start

### Define a Sub-Agent

Create a `.md` file in `subagents/`:

```markdown
---
name: explore
description: Fast agent for exploring codebases
model: co/gemini-2.5-flash
max_iterations: 15
tools:
  - glob
  - grep
  - read_file
read_only: true
---

# Explore Agent

You are a read-only exploration agent...
```

### Use in Code

```python
from connectonion import task

# Delegate to sub-agent
result = task("Find all API endpoints", "explore")
```

## File Format

### YAML Frontmatter (Config)

```yaml
---
name: explore                          # Required: unique identifier
description: Fast codebase exploration  # Required: one-line description
model: co/gemini-2.5-flash             # Required: LLM model
max_iterations: 15                      # Required: max iteration limit
tools:                                  # Required: list of tool names
  - glob
  - grep
  - read_file
read_only: true                         # Optional: read-only flag (default: false)
---
```

### Markdown Body (System Prompt)

Everything after `---` is the system prompt sent to the agent.

## Available Tools

- `glob` - Find files by pattern
- `grep` - Search file contents
- `read_file` - Read file contents

## Data Structure

```python
@dataclass
class SubAgentDefinition:
    name: str               # "explore"
    description: str        # "Fast codebase exploration"
    model: str             # "co/gemini-2.5-flash"
    max_iterations: int    # 15
    tools: List[str]       # ["glob", "grep", "read_file"]
    system_prompt: str     # Full markdown body
    read_only: bool        # True
    file_path: Path        # Path to .md file
```

## Architecture

```
subagents/
├── __init__.py         # task() function
├── loader.py           # Parse .md files
├── factory.py          # Create Agent instances
├── explore.md          # Exploration sub-agent
├── plan.md             # Planning sub-agent
└── README.md           # This file
```

### Loader (`loader.py`)

- `parse_yaml_frontmatter(content)` - Parse YAML + markdown
- `parse_subagent_file(path)` - Load single definition
- `discover_subagents(dir)` - Find all .md files
- `load_subagents()` - Initialize global registry
- `get_subagent_definition(name)` - Get by name

### Factory (`factory.py`)

- `create_subagent(type)` - Create Agent instance from definition

### Task Interface (`__init__.py`)

- `task(prompt, agent_type)` - Delegate to sub-agent

## Design Principles

1. **Single file** - Config + prompt in one place
2. **Auto-discovery** - Drop .md file, it's available
3. **No code changes** - Add sub-agents without touching code
4. **Git-friendly** - Text files, easy to diff
5. **Self-documenting** - Markdown format
6. **Stateless** - Fresh agent per call
7. **Isolated** - No shared state with parent
8. **Simple** - No plugins, minimal config

## Examples

### explore.md

Fast, cheap exploration agent using Flash model:

```yaml
---
name: explore
model: co/gemini-2.5-flash  # 100x cheaper than Opus
max_iterations: 15
tools: [glob, grep, read_file]
read_only: true
---
```

### plan.md

Smart planning agent using Pro model:

```yaml
---
name: plan
model: co/gemini-2.5-pro    # Smart but still 6x cheaper than Opus
max_iterations: 10
tools: [glob, grep, read_file]
read_only: true
---
```

## Cost Optimization

| Agent Type | Model | Input Cost | Output Cost | Use Case |
|------------|-------|------------|-------------|----------|
| Main | opus-4-5 | $15/1M | $75/1M | Complex reasoning |
| Explore | flash | $0.15/1M | $0.60/1M | Fast file finding |
| Plan | pro | $2.50/1M | $10/1M | Smart planning |

**Savings**: Using sub-agents for exploration = **100x cheaper** than Opus!

## Testing

```bash
# Test YAML parser
python -c "from subagents.loader import parse_yaml_frontmatter; ..."

# Test loading definition
python -c "from subagents.loader import parse_subagent_file; ..."

# Test full workflow
python -c "from subagents import task; result = task('Find all files', 'explore')"
```

## Adding New Sub-Agents

1. Create `subagents/myagent.md`
2. Add YAML frontmatter with config
3. Add markdown body with system prompt
4. Done! Auto-discovered on next import

No code changes needed.

## Validation

Simple schema validation available:

```python
from subagents.loader import SubAgentDefinition

# Validates:
- name: unique identifier (required)
- description: one-line text (required)
- model: valid model name (required)
- max_iterations: 1-100 (required)
- tools: valid tool names (required)
- read_only: boolean (optional)
```

## Future Enhancements

Possible additions without breaking changes:

- `cost_optimization: true` - Flag for cost-optimized agents
- `timeout: 30` - Max execution time in seconds
- `retry: 3` - Retry failed tool calls
- `cache: true` - Cache results for identical prompts
- `examples: [...]` - Example prompts for testing

All optional, backward compatible.
