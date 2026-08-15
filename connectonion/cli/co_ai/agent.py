"""
LLM-Note: Factory function for creating the 'co ai' agent with all tools and plugins.

Key function:
- create_agent(): Creates Agent with full tool suite and intelligent defaults
- create_coding_agent: back-compat alias for create_agent

Tools included:
- File operations: glob, grep, read_file, edit, FileWriter
- Task management: task, TodoList
- Background tasks: run_background, task_output, kill_task
- User interaction: ask_user, skill, load_guide
- Shell: bash (with approval flow)

Plugins included:
- eval: Session persistence for debugging
- system_reminder: Contextual hints
- prefer_write_tool: Block bash file creation, soft-remind for file reading
- tool_approval: Approval flow for dangerous operations
- auto_compact: Context window management
- yolo: Approval-free autonomous N-turn sessions with continuation

Architecture:
- Uses prompt assembly from prompts/assembler.py: main.md (domain-neutral) +
  roles/{role}.md (what this agent works on; 'coding' for `co ai`)
- Tool name must match prompts/tools/{tool_name}.md for the doc to be included
- Loads project context from CLAUDE.md, NIGHT_RUNNER_PROGRESS.md, etc.
- Global .co directory at ~/.co for consistent logs/evals
- MODE_AUTO vs MODE_NORMAL for FileWriter (web vs CLI)

Debug:
- To inspect the assembled system prompt: python tests/e2e/cli/show_co_ai_prompt.py
"""

from pathlib import Path

from connectonion import Agent, TodoList, bash
from connectonion.core.events import after_user_input
from connectonion.core.usage import DEFAULT_MODEL
from connectonion.useful_plugins import (
    auto_compact,
    enable_yolo,
    eval,
    image_result_formatter,
    prefer_write_tool,
    runtime_input,
    subagents,
    tool_approval,
    yolo,
)
from connectonion.useful_plugins.skills import skills as skills_plugin

from .context import load_project_context
from .plugins import system_reminder
from .prompts.assembler import assemble_prompt
from .skills import skill
from .tools import (
    FileTools,
    acp_agent,
    ask_user,
    claude_code,
    codex,
    kill_task,
    load_guide,
    run_background,
    task_output,
)

PROMPTS_DIR = Path(__file__).parent / "prompts"
# Global .co directory for co ai (consistent logs/evals location)
GLOBAL_CO_DIR = Path.home() / ".co"


@after_user_input
def grant_managed_delegation_permissions(agent: Agent) -> None:
    """Explicitly permit co ai wrappers that enforce their own inner policy.

    Keep these grants local to co ai's LLM loop. Putting them in host.yaml's
    shared defaults would also expose the wrappers to direct remote EXEC.
    """
    permissions = agent.current_session.setdefault('permissions', {})
    for tool_name in ('codex', 'claude_code', 'acp_agent'):
        permissions.setdefault(tool_name, {
            'allowed': True,
            'source': 'safe',
            'reason': 'managed delegation owns inner approval',
            'expires': {'type': 'never'},
        })


def agent_name(co_dir: Path = Path(".co")) -> str:
    """What this agent is called, according to its own host.yaml.

    co-ai is the only template, so a hardcoded name meant every agent anyone
    deployed announced itself identically. The author already wrote the name
    they chose, in `.co/host.yaml`, in a field called `name` — it just was not
    being read.

    Falls back to "oo" when there is no host.yaml, no `name` in it, or it does
    not parse. A name is not worth failing a startup over; a broken host.yaml
    is reported for what it is elsewhere.
    """
    host_yaml = co_dir / "host.yaml"
    if not host_yaml.exists():
        return "oo"
    try:
        import yaml
        config = yaml.safe_load(host_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return "oo"
    name = config.get("name") if isinstance(config, dict) else None
    return name if isinstance(name, str) and name.strip() else "oo"


def create_agent(
    model: str = DEFAULT_MODEL,
    max_iterations: int = 100,
    co_dir: Path = Path(".co"),
    yolo_turns: int | None = None,
    role: str | None = "coding",
    background_tools: bool = True,
    state_dir: Path | None = None,
) -> Agent:
    """Build the co-ai agent.

    `role` picks which roles/{role}.md is appended to the domain-neutral
    main.md. `co ai` keeps the default "coding"; a deployed agent that is a
    support bot or a poster passes its own role, or None for no role at all.
    """
    todo = TodoList()
    file_tools = FileTools()

    tools = [
        file_tools,
        bash,
        # task is now provided by subagents plugin (no need to import from .tools)
        todo,
        skill,
        *([run_background, task_output, kill_task] if background_tools else []),
        load_guide,
        ask_user,
        # Codex owns approval for its concrete inner actions. The co ai wrapper
        # derives that policy from the current mode instead of exposing it to
        # the planner model as another set of permission switches.
        codex,
        claude_code,
        acp_agent,
    ]

    base_prompt = assemble_prompt(
        prompts_dir=str(PROMPTS_DIR),
        tools=tools,
        role=role,
    )

    project_context = load_project_context()
    system_prompt = base_prompt
    if project_context:
        system_prompt += f"\n\n---\n\n{project_context}"

    # The browser is driven through the `co browser` CLI (see prompts/browser.md),
    # not an in-process BrowserAutomation: one daemon owns the profile and the tabs,
    # so panels no longer share a page and 40 tool schemas leave the request.
    # image_result_formatter stays — it turns the screenshot path the CLI prints
    # back into an image the model and the user can actually see.
    plugins = [
        skills_plugin,
        subagents,
        eval,
        system_reminder,
        prefer_write_tool,
        [grant_managed_delegation_permissions],
        tool_approval,
        auto_compact,
        yolo,
        image_result_formatter,
        runtime_input,
    ]

    agent = Agent(
        name=agent_name(co_dir),
        tools=tools,
        plugins=plugins,
        on_events=[],
        system_prompt=system_prompt,
        model=model,
        max_iterations=max_iterations,
        co_dir=co_dir,
        state_dir=state_dir,
    )
    agent._delegation_workspace = Path.cwd().resolve()
    # This browser helper blocks on stdin, which is wrong for co ai's websocket
    # chat runtime. Use browser tools plus frontend-mediated user handoffs.
    agent.tools.remove("wait_for_manual_login")

    if yolo_turns is not None:
        enable_yolo(agent, turns=yolo_turns)

    return agent


# Older name, from when co-ai was coding-only. Kept so existing imports keep
# working; new code should call create_agent().
create_coding_agent = create_agent
