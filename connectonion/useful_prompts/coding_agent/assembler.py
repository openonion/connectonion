"""
Purpose: Modular prompt assembly for coding agents from main.md + tool-specific prompts + project context
LLM-Note:
  Dependencies: imports from [pathlib, typing] | imported by [examples/coding_agent/, user code] | tested by [tests/prompts/test_assembler.py]
  Data flow: assemble_prompt(prompts_dir, tools, context_file) → reads prompts/main.md → for each tool reads prompts/tools/{tool_name}.md → optionally reads context_file (.co/AGENT.md) → concatenates with separators → returns assembled prompt
  State/Effects: reads markdown files from filesystem | no persistent state
  Integration: exposes assemble_prompt(prompts_dir, tools, context_file) → str | expects directory structure: prompts/main.md, prompts/tools/*.md | tool name extracted from tool.__name__ or tool.name | user customizable (copy to project and modify)
  Performance: file I/O only (fast for typical prompt files) | lazy loading (only reads requested tool prompts)
  Errors: skips missing tool prompt files silently | raises if main.md missing | context_file optional
Prompt Assembler - Copy this to your project and customize!

This is NOT a framework class. It's an example you can modify freely.
The assembled prompt combines:
  - Main prompt (core agent behavior)
  - Tool descriptions (for each tool you use)
  - Project context (optional .co/AGENT.md)

Usage:
    from assembler import assemble_prompt

    prompt = assemble_prompt(
        tools=[shell, read_file, writer],
        context_file=".co/AGENT.md"  # optional
    )

    agent = Agent("my-agent", system_prompt=prompt, tools=tools)
"""

from pathlib import Path
from typing import List, Any, Optional


def assemble_prompt(
    prompts_dir: str = "prompts",
    tools: Optional[List[Any]] = None,
    context_file: Optional[str] = None,
) -> str:
    """
    Assemble a system prompt from modular files.

    Directory structure:
        prompts/
        ├── main.md          # Core agent behavior
        └── tools/           # Tool-specific guidance
            ├── shell.md
            ├── read.md
            └── write.md

    Args:
        prompts_dir: Path to prompts directory
        tools: List of tool objects/functions (loads matching .md files)
        context_file: Optional project-specific context file

    Returns:
        Assembled prompt string
    """
    prompts_path = Path(prompts_dir)
    parts = []

    # 1. Main prompt (required)
    main_file = prompts_path / "main.md"
    if main_file.exists():
        parts.append(main_file.read_text())

    # 2. Tool descriptions (for each available tool)
    tools_dir = prompts_path / "tools"
    if tools_dir.exists() and tools:
        for tool in tools:
            tool_name = _get_tool_name(tool).lower()
            tool_file = tools_dir / f"{tool_name}.md"
            if tool_file.exists():
                parts.append(tool_file.read_text())

    # 3. Project context (optional)
    if context_file:
        context_path = Path(context_file)
        if context_path.exists():
            parts.append(f"# Project Context\n\n{context_path.read_text()}")

    return "\n\n---\n\n".join(parts)


def _get_tool_name(tool: Any) -> str:
    """Extract tool name from function or class instance."""
    # Function
    if callable(tool) and hasattr(tool, "__name__"):
        return tool.__name__

    # Class instance with name attribute
    if hasattr(tool, "name"):
        return tool.name

    # Class instance - use class name
    return tool.__class__.__name__


# Example usage
if __name__ == "__main__":
    from connectonion import Agent
    from connectonion.useful_tools import bash, DiffWriter, TodoList

    # Define tools
    def read_file(path: str) -> str:
        """Read file contents."""
        return Path(path).read_text()

    writer = DiffWriter()
    todo = TodoList()
    tools = [bash, read_file, writer, todo]

    # Assemble prompt
    prompt = assemble_prompt(
        prompts_dir="prompts",
        tools=tools,
        context_file=".co/AGENT.md"
    )

    print(f"Assembled prompt ({len(prompt)} chars):\n")
    print(prompt[:500] + "...")

    # Create agent
    # agent = Agent("coding-agent", system_prompt=prompt, tools=tools)
    # agent.run()
