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
- prefer_write_tool: Block bash file creation, soft-remind for file reading
- tool_approval: Approval flow for dangerous operations
- auto_compact: Context window management
- yolo: Approval-free autonomous N-turn sessions with continuation

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


PROMPTS_DIR = Path(__file__).parent / "prompts"
# Global .co directory for co ai (consistent logs/evals location)
GLOBAL_CO_DIR = Path.home() / ".co"


def create_coding_agent(
    model: str = "co/gemini-3.6-flash",
    max_iterations: int = 100,
    co_dir: Path = Path(".co"),
    yolo_turns: int | None = None,
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
        tool_approval,
        auto_compact,
        yolo,
        image_result_formatter,
        runtime_input,
    ]

    agent = Agent(
        name="oo",
        tools=tools,
        plugins=plugins,
        on_events=[],
        system_prompt=system_prompt,
        model=model,
        max_iterations=max_iterations,
        co_dir=co_dir,
    )
    # This browser helper blocks on stdin, which is wrong for co ai's websocket
    # chat runtime. Use browser tools plus frontend-mediated user handoffs.
    agent.tools.remove("wait_for_manual_login")

    if yolo_turns is not None:
        enable_yolo(agent, turns=yolo_turns)

    return agent
