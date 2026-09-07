"""
Purpose: Load and execute slash commands from markdown files with YAML frontmatter
LLM-Note:
  Dependencies: imports from [yaml, pathlib, typing] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_slash_command.py]
  Data flow: SlashCommand.load(name) → searches .co/commands/*.md and commands/*.md → parses YAML frontmatter for metadata → extracts prompt body → SlashCommand.filter_tools() filters available tools → returns filtered tool list
  State/Effects: reads markdown files from filesystem | no persistent state | no network I/O | command files can specify tool restrictions
  Integration: exposes SlashCommand class with load(name), list_all(), filter_tools(tools) | command format: YAML frontmatter (name, description, tools) + markdown prompt body | used by CLI and agent for custom commands
  Performance: file I/O per load | YAML parsing is fast | list_all() scans directories once
  Errors: returns None if command not found | raises ValueError for invalid YAML | no other exceptions

SlashCommand - Load and execute slash commands from markdown files.

Usage:
    from connectonion import SlashCommand

    # Load command
    cmd = SlashCommand.load("today")

    # Get prompt and filter tools
    prompt = cmd.prompt
    filtered_tools = cmd.filter_tools(all_tools)

    # List all commands
    commands = SlashCommand.list_all()

Command file format (.co/commands/*.md or commands/*.md):
---
name: today
description: Daily email briefing
tools:
  - Gmail.search_emails    # Specific method
  - WebFetch               # Whole class
  - my_function            # Standalone function
---
Your command prompt here...
"""

from pathlib import Path
from typing import List, Optional

import yaml

from ..project import project_co_dir, project_root


class SlashCommand:
    """Represents a slash command loaded from a markdown file."""

    def __init__(self, name: str, description: str, prompt: str, tools: Optional[List[str]] = None, is_custom: bool = False):
        """Initialize a SlashCommand.

        Args:
            name: Command name
            description: Command description
            prompt: Command prompt template
            tools: List of allowed tools (None = all tools allowed)
            is_custom: Whether this is a user custom command
        """
        self.name = name
        self.description = description
        self.prompt = prompt
        self.tools = tools
        self.is_custom = is_custom

    @classmethod
    def load(cls, command_name: str) -> Optional["SlashCommand"]:
        """Load command from .co/commands/ (user) or commands/ (built-in).

        Args:
            command_name: Name of the command (without .md extension)

        Returns:
            SlashCommand instance or None if not found
        """
        # Check user custom first
        custom_path = project_co_dir() / "commands" / f"{command_name}.md"
        if custom_path.exists():
            return cls._parse_file(custom_path, is_custom=True)

        # Check built-in
        builtin_path = project_root() / "commands" / f"{command_name}.md"
        if builtin_path.exists():
            return cls._parse_file(builtin_path, is_custom=False)

        return None

    @classmethod
    def _parse_file(cls, filepath: Path, is_custom: bool = False) -> "SlashCommand":
        """Parse markdown file with YAML frontmatter.

        Args:
            filepath: Path to .md file
            is_custom: Whether this is a user custom command

        Returns:
            SlashCommand instance

        Raises:
            yaml.YAMLError: If frontmatter is invalid
            ValueError: If required fields missing
        """
        content = filepath.read_text(encoding="utf-8")

        # Split frontmatter and prompt
        if not content.startswith("---"):
            raise ValueError(f"Command file {filepath} missing YAML frontmatter")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Command file {filepath} has malformed frontmatter")

        # Parse YAML (let it raise naturally if invalid)
        frontmatter = yaml.safe_load(parts[1])
        prompt = parts[2].strip()

        # Validate required fields
        if "name" not in frontmatter:
            raise ValueError(f"Command file {filepath} missing 'name' field")
        if "description" not in frontmatter:
            raise ValueError(f"Command file {filepath} missing 'description' field")

        return cls(
            name=frontmatter["name"],
            description=frontmatter["description"],
            prompt=prompt,
            tools=frontmatter.get("tools"),
            is_custom=is_custom
        )

    def filter_tools(self, available_tools: List) -> List:
        """Filter tools based on allowed list from command file.

        Args:
            available_tools: List of all available tool instances or functions

        Returns:
            Filtered list of tools

        Example:
            tools = ["Gmail.search_emails", "Agent.input"]
            # Only allows Gmail.search_emails and Agent.input methods
        """
        if self.tools is None:
            return available_tools

        filtered = []

        for tool in available_tools:
            tool_name = getattr(tool, '__name__', None)

            # Handle class-based tools (have __self__ attribute)
            if hasattr(tool, '__self__'):
                class_name = tool.__self__.__class__.__name__
                method_name = tool.__name__
                full_name = f"{class_name}.{method_name}"

                # Check if specific method or whole class is allowed
                if full_name in self.tools or class_name in self.tools:
                    filtered.append(tool)

            # Handle function-based tools
            elif tool_name and tool_name in self.tools:
                filtered.append(tool)

        return filtered

    @classmethod
    def list_all(cls, report: bool = False):
        """List all available commands (built-in and custom).

        One bad file used to lose every good one. This is the menu, and
        `_parse_file` raises on a file without frontmatter, so a typo in a file
        the user may never have opened produced no commands at all and a
        traceback.

        A file that cannot be read is skipped and named. Silence would be its
        own bug — #629 exists because a dropped entry is indistinguishable from
        one that was never there — so `report=True` returns the reasons.

        Checked, not caught: `_why_the_command_cannot_be_read` asks the
        questions `_parse_file` would raise on, so a genuinely unexpected
        failure still surfaces instead of being swallowed as "malformed".

        Returns:
            Dict mapping command names to SlashCommand instances, or
            (commands, problems) when report=True. Custom commands override
            built-ins.
        """
        commands = {}
        problems = []

        for directory, is_custom in ((project_root() / "commands", False),
                                     (project_co_dir() / "commands", True)):
            if not directory.exists():
                continue
            for filepath in sorted(directory.glob("*.md")):
                reason = _why_the_command_cannot_be_read(filepath)
                if reason:
                    problems.append(f"{filepath.name}: {reason}")
                    continue
                cmd = cls._parse_file(filepath, is_custom=is_custom)
                commands[cmd.name] = cmd

        return (commands, problems) if report else commands

    @classmethod
    def is_custom(cls, command_name: str) -> bool:
        """Check if command is a custom override.

        Args:
            command_name: Name of the command

        Returns:
            True if custom command exists in .co/commands/
        """
        custom_path = project_co_dir() / "commands" / f"{command_name}.md"
        return custom_path.exists()


def _why_the_command_cannot_be_read(filepath: Path) -> Optional[str]:
    """The reason a command file cannot be loaded, or None if it is fine.

    The same questions `_parse_file` raises on, asked instead of caught, so the
    menu can skip one file without a try/except that would also hide a bug in
    the parser itself.

    Unlike a SKILL.md, a command with no frontmatter is not currently a valid
    simple command -- `_parse_file` requires `name` and `description`. Whether
    it *should* be (filename as name, whole file as prompt, the way #629 treats
    skills) is a format decision and is not made here. #668 records that the
    two subsystems disagree about identical input.
    """
    content = filepath.read_text(encoding="utf-8", errors="replace")

    if not content.strip():
        return "file is empty"
    if not content.startswith("---"):
        return "no YAML frontmatter (expected a '---' block at the top)"

    parts = content.split("---", 2)
    if len(parts) < 3:
        return "frontmatter is not closed by a second '---'"

    import yaml as _yaml
    try:
        frontmatter = _yaml.safe_load(parts[1])
    except _yaml.YAMLError as exc:
        # The one place catching is right: asking "is this valid YAML" without
        # running the parser means writing a second YAML parser.
        return f"frontmatter is not valid YAML: {str(exc).splitlines()[0]}"

    if not isinstance(frontmatter, dict):
        return "frontmatter is not a mapping"
    for field in ("name", "description"):
        if field not in frontmatter:
            return f"missing '{field}' field"
    return None
