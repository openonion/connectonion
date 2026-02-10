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
from connectonion import Agent, bash, FileWriter, MODE_AUTO, MODE_NORMAL, TodoList
from connectonion.useful_plugins import eval, tool_approval, auto_compact, prefer_write_tool


PROMPTS_DIR = Path(__file__).parent / "prompts"
# Global .co directory for co ai (consistent logs/evals location)
GLOBAL_CO_DIR = Path.home() / ".co"


def create_coding_agent(
    model: str = "co/claude-opus-4-5",
    max_iterations: int = 100,
    auto_approve: bool = False,
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

    plugins = [eval, system_reminder, prefer_write_tool, tool_approval, auto_compact]

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

    agent.writer = writer
    return agent
