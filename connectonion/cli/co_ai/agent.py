"""
LLM-Note: Factory function for creating the 'co ai' coding agent with all tools and plugins.

Key function:
- create_coding_agent(): Creates Agent with full tool suite and intelligent defaults

Tools included:
- File operations: glob, grep, read_file, edit, FileWriter
- Task management: task, TodoList
- Planning: enter_plan_mode, exit_plan_and_implement, write_plan
- Background tasks: run_background, task_output, kill_task
- User interaction: ask_user, skill, load_guide
- Shell: bash (with approval flow)

Plugins included:
- eval: Session persistence for debugging
- system_reminder: Contextual hints
- prefer_write_tool: Nudges toward using Write over Edit
- tool_approval: Approval flow for dangerous operations
- auto_compact: Context window management
- ulw: Ultra work mode (autonomous N-turn sessions with continuation)

Architecture:
- Uses prompt assembly from prompts/assembler.py
- Tool name must match prompts/tools/{tool_name}.md for the doc to be included
- Loads project context from CLAUDE.md, NIGHT_RUNNER_PROGRESS.md, etc.
- Global .co directory at ~/.co for consistent logs/evals
- MODE_AUTO vs MODE_NORMAL for FileWriter (web vs CLI)

Debug:
- To inspect the assembled system prompt: python tests/cli/show_co_ai_prompt.py
"""

from pathlib import Path

from .context import load_project_context
from .prompts.assembler import assemble_prompt
from .tools import (
    FileTools,
    enter_plan_mode, exit_plan_and_implement, write_plan,
    ask_user,
    run_background, task_output, kill_task,
    load_guide,
)
from .skills import skill
from .plugins import system_reminder
from connectonion import Agent, bash, TodoList
from connectonion.useful_plugins import eval, tool_approval, auto_compact, prefer_write_tool, ulw, subagents


PROMPTS_DIR = Path(__file__).parent / "prompts"
# Global .co directory for co ai (consistent logs/evals location)
GLOBAL_CO_DIR = Path.home() / ".co"


def create_coding_agent(
    model: str = "co/claude-opus-4-5",
    max_iterations: int = 100,
    auto_approve: bool = False,
) -> Agent:
    todo = TodoList()
    file_tools = FileTools()

    tools = [
        file_tools,
        bash,
        # task is now provided by subagents plugin (no need to import from .tools)
        enter_plan_mode,
        exit_plan_and_implement,
        write_plan,
        todo,
        skill,
        run_background,
        task_output,
        kill_task,
        load_guide,
        ask_user,
    ]

    base_prompt = assemble_prompt(
        prompts_dir=str(PROMPTS_DIR),
        tools=tools,
    )

    project_context = load_project_context()
    system_prompt = base_prompt
    if project_context:
        system_prompt += f"\n\n---\n\n{project_context}"

    # Use SDK's subagents plugin instead of custom task implementation
    plugins = [subagents, eval, system_reminder, prefer_write_tool, tool_approval, auto_compact, ulw]

    agent = Agent(
        name="oo",
        tools=tools,
        plugins=plugins,
        on_events=[],
        system_prompt=system_prompt,
        model=model,
        max_iterations=max_iterations,
        co_dir=GLOBAL_CO_DIR,
    )

    return agent
