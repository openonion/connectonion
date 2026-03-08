"""
Purpose: Subagents plugin - Spawn specialized agents for specific tasks
LLM-Note:
  Dependencies: imports from [core/events.py, core/agent.py] | imported by [useful_plugins/__init__.py]
  Data flow: @on_agent_ready discovers agents → registers task() tool → injects available agents into system_prompt
  State/Effects: Dynamically adds task() tool to agent | Modifies system_prompt to list available agents
  Integration: Uses AGENT.md format (YAML frontmatter + system prompt) | Discovery from .co/agents/, ~/.co/agents/, builtin/

Subagents Plugin - Spawn specialized agents to handle specific tasks.

Discovery:
1. .co/agents/agent-name/AGENT.md    (project-level, highest priority)
2. ~/.co/agents/agent-name/AGENT.md  (user-level)
3. builtin/agent-name/AGENT.md       (built-in, lowest priority)

AGENT.md Format:
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
```
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, Any, List

from ..core.events import on_agent_ready

if TYPE_CHECKING:
    from ..core.agent import Agent


# =============================================================================
# AGENT DISCOVERY (following skills.py pattern)
# =============================================================================

def _get_agent_paths(agent_name: str) -> List[Path]:
    """Get potential paths for an agent in priority order."""
    paths = []

    # 1. Project-level
    paths.append(Path.cwd() / '.co' / 'agents' / agent_name / 'AGENT.md')

    # 2. User-level
    paths.append(Path.home() / '.co' / 'agents' / agent_name / 'AGENT.md')

    # 3. Built-in
    builtin_base = Path(__file__).parent / 'builtin_agents'
    paths.append(builtin_base / agent_name / 'AGENT.md')

    return paths


def _load_agent(agent_name: str) -> Optional[Dict[str, Any]]:
    """Load agent configuration from filesystem."""
    for path in _get_agent_paths(agent_name):
        if path.exists():
            content = path.read_text()
            frontmatter, system_prompt = _parse_agent_content(content)
            return {
                'path': str(path),
                'frontmatter': frontmatter,
                'system_prompt': system_prompt
            }
    return None


def _parse_agent_content(content: str) -> tuple[Dict[str, Any], str]:
    """Parse AGENT.md content into frontmatter and system prompt."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)

    if not match:
        return {}, content.strip()

    yaml_text = match.group(1)
    system_prompt = match.group(2).strip()

    import yaml
    try:
        frontmatter = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, system_prompt


def _discover_all_agents() -> List[Dict[str, str]]:
    """Discover all available agents for system prompt."""
    agents = []
    seen_names = set()

    for location, base_path in [
        ('project', Path.cwd() / '.co' / 'agents'),
        ('user', Path.home() / '.co' / 'agents'),
        ('builtin', Path(__file__).parent / 'builtin_agents')
    ]:
        if not base_path.exists():
            continue

        for agent_dir in base_path.iterdir():
            if not agent_dir.is_dir():
                continue

            agent_file = agent_dir / 'AGENT.md'
            if not agent_file.exists():
                continue

            agent_name = agent_dir.name
            if agent_name in seen_names:
                continue

            seen_names.add(agent_name)

            content = agent_file.read_text()
            frontmatter, _ = _parse_agent_content(content)
            description = frontmatter.get('description', 'No description')

            agents.append({
                'name': agent_name,
                'description': description,
                'location': location
            })

    return agents


# =============================================================================
# TASK TOOL (Main API - will be registered dynamically)
# =============================================================================

def task(agent, prompt: str, agent_type: str) -> str:
    """Spawn a specialized sub-agent to handle a task.

    Args:
        agent: Parent agent instance (Agent type)
        prompt: Task description for the sub-agent
        agent_type: Type of agent to spawn (e.g., "explore", "plan")

    Returns:
        Sub-agent's final response after completing the task
    """
    # Import here to avoid circular dependency
    from ..core.agent import Agent

    # Load agent configuration
    config = _load_agent(agent_type)
    if not config:
        available = _discover_all_agents()
        agent_list = "\n".join(f"- {a['name']}: {a['description']}" for a in available)
        return f"Agent type '{agent_type}' not found. Available agents:\n{agent_list}"

    # Extract configuration
    frontmatter = config['frontmatter']
    system_prompt = config['system_prompt']
    model = frontmatter.get('model', 'co/gemini-2.5-pro')
    max_iterations = frontmatter.get('max_iterations', 10)
    tool_names = frontmatter.get('tools', [])

    # Resolve tool names to actual functions
    tools = _resolve_tools(tool_names, agent_type)

    # Create sub-agent
    sub_agent = Agent(
        name=f"sub-{agent_type}",
        tools=tools,
        system_prompt=system_prompt,
        model=model,
        max_iterations=max_iterations,
        plugins=[]
    )

    # Execute task
    result = sub_agent.input(prompt)

    return result


def _resolve_tools(tool_names: List[str], agent_name: str) -> List:
    """Resolve tool names to actual tool functions/classes."""
    from ..useful_tools import glob, grep, read_file, edit, multi_edit, write, bash, WebFetch, Memory
    from ..useful_tools.browser_tools import BrowserAutomation

    tool_map = {
        'glob': glob,
        'grep': grep,
        'read_file': read_file,
        'edit': edit,
        'multi_edit': multi_edit,
        'write': write,
        'bash': bash,
        'WebFetch': WebFetch,
        'Memory': Memory,
        'Browser': BrowserAutomation,  # Simpler name
        'BrowserAutomation': BrowserAutomation,  # Keep full name for backwards compat
    }

    tools = []
    for tool_name in tool_names:
        if tool_name in tool_map:
            tool = tool_map[tool_name]
            # If it's a class, instantiate it
            if isinstance(tool, type):
                tools.append(tool())
            else:
                tools.append(tool)

    return tools


# =============================================================================
# PLUGIN INITIALIZATION
# =============================================================================

@on_agent_ready
def initialize_subagents(agent: 'Agent') -> None:
    """Register task() tool and inject available agents into system prompt."""
    # 1. Dynamically register task tool
    agent.add_tool(task)

    # 2. Discover available agent types
    available_agents = _discover_all_agents()

    if not available_agents:
        return

    # 3. Inject into system prompt
    agents_list = ", ".join(a['name'] for a in available_agents)
    agent_descriptions = "\n".join(f"- `{a['name']}`: {a['description']}" for a in available_agents)

    agent.system_prompt += f"""

# Available Sub-Agents

You can spawn specialized sub-agents to handle specific tasks using the `task()` tool.

**Available agents:** {agents_list}

{agent_descriptions}

**Usage:**
```python
task(prompt="Find all authentication code", agent_type="explore")
```

Sub-agents run in isolation with their own context and return results when complete.
"""


# Export as plugin
subagents = [initialize_subagents]

__all__ = ['subagents', 'task']
