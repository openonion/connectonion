# subagents

Spawn specialized sub-agents to handle specific tasks. The parent agent delegates work — the sub-agent runs with its own tools, model, and system prompt, then returns the result.

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import subagents

agent = Agent("main", plugins=[subagents])
agent.input("explore the codebase and summarize the architecture")
# Internally: task(prompt="...", agent_type="explore")
```

## How it works

On agent startup (`on_agent_ready`), the plugin:
1. Discovers available agent definitions
2. Registers a `task()` tool on the parent agent
3. Injects the available agents list into the system prompt

The parent agent then calls `task()` to delegate work to sub-agents.

## Agent Discovery

Agents are loaded from (in priority order):

```
.co/agents/{name}/AGENT.md      # Project-level (highest priority)
~/.co/agents/{name}/AGENT.md    # User-level
builtin/{name}/AGENT.md         # Built-in agents
```

## AGENT.md Format

```yaml
---
name: explore
description: Fast codebase exploration agent
model: co/gemini-2.5-flash
max_iterations: 15
tools:
  - glob
  - grep
  - read_file
---

You are an explore agent specialized in quickly understanding codebases.
Find patterns, summarize architecture, and explain what code does.
```

### Available tool names

`glob`, `grep`, `read_file`, `edit`, `multi_edit`, `write`, `bash`, `WebFetch`, `Memory`, `Browser`

## Creating a custom sub-agent

```bash
mkdir -p .co/agents/reviewer
cat > .co/agents/reviewer/AGENT.md << 'EOF'
---
name: reviewer
description: Code reviewer that checks for bugs and style issues
model: co/claude-opus-4-5
max_iterations: 10
tools:
  - glob
  - grep
  - read_file
---

You are a code reviewer. Find bugs, style issues, and improvements.
Return a structured report with findings.
EOF
```

Then use it:

```python
agent.input("review all Python files in src/")
# Agent calls: task(prompt="Review all Python files...", agent_type="reviewer")
```

## Built-in agents

The plugin ships with built-in agents for `co ai`. When using `co ai`, you have access to agents like `explore` and `plan` out of the box.

## Events used

| Event | Handler | Purpose |
|-------|---------|---------|
| `on_agent_ready` | `initialize_subagents` | Discover agents, register task() tool |

## Source

```
connectonion/useful_plugins/subagents.py
connectonion/useful_plugins/builtin_agents/
```
