"""Main coding agent module."""

from pathlib import Path

from .context import load_project_context
from .prompts.assembler import assemble_prompt
from .tools import (
    glob, grep, edit, read_file, task,
    enter_plan_mode, exit_plan_mode, write_plan,
    ask_user,
    run_background, task_output, kill_task,
    load_guide,
)
from .skills import skill
from .plugins import system_reminder
from connectonion import Agent, bash, after_user_input, FileWriter, MODE_AUTO, MODE_NORMAL, TodoList
from connectonion.useful_plugins import eval, tool_approval


PROMPTS_DIR = Path(__file__).parent / "prompts"


@after_user_input
def _sync_tool_io(agent) -> None:
    io = getattr(agent, "io", None) or getattr(agent, "connection", None)
    if not io:
        return
    # ToolRegistry does not expose instances publicly; use best-effort access.
    instances = getattr(agent.tools, "_instances", {})
    for instance in instances.values():
        if hasattr(instance, "io"):
            instance.io = io


def create_coding_agent(
    model: str = "co/claude-opus-4-5",
    max_iterations: int = 20,
    auto_approve: bool = False,
    web_mode: bool = False,
) -> Agent:
    writer = FileWriter(mode=MODE_AUTO if auto_approve else MODE_NORMAL)
    todo = TodoList()

    tools = [
        glob,
        grep,
        read_file,
        edit,
        writer,
        bash,
        task,
        enter_plan_mode,
        exit_plan_mode,
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

    plugins = [eval, system_reminder, tool_approval]

    agent = Agent(
        name="oo",
        tools=tools,
        plugins=plugins,
        on_events=[_sync_tool_io],
        system_prompt=system_prompt,
        model=model,
        max_iterations=max_iterations,
    )

    agent.writer = writer
    return agent
