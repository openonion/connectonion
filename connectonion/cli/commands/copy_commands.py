"""
Purpose: CLI command to copy built-in tools and plugins to user's project for customization
LLM-Note:
  Dependencies: imports from [shutil, pathlib, typing, rich] | imported by [cli/main.py via handle_copy()]
  Data flow: user runs `co copy <name>` → looks up name in TOOLS/PLUGINS registry → finds source via module.__file__ → copies to ./tools/ or ./plugins/
  State/Effects: creates tools/ or plugins/ directory if needed | copies .py files from installed package to user's project
  Integration: exposes handle_copy() for CLI | uses Python import system to find installed package location (cross-platform)
"""

import shutil
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.table import Table

console = Console()

# Registry of copyable tools
TOOLS = {
    "gmail": "gmail.py",
    "outlook": "outlook.py",
    "google_calendar": "google_calendar.py",
    "microsoft_calendar": "microsoft_calendar.py",
    "memory": "memory.py",
    "web_fetch": "web_fetch.py",
    "shell": "shell.py",
    "diff_writer": "diff_writer.py",
    "todo_list": "todo_list.py",
    "slash_command": "slash_command.py",
}

# Registry of copyable plugins
PLUGINS = {
    "re_act": "re_act.py",
    "eval": "eval.py",
    "image_result_formatter": "image_result_formatter.py",
    "shell_approval": "shell_approval.py",
    "gmail_plugin": "gmail_plugin.py",
    "calendar_plugin": "calendar_plugin.py",
}


def handle_copy(
    names: List[str],
    list_all: bool = False,
    path: Optional[str] = None,
    force: bool = False
):
    """Copy built-in tools and plugins to user's project."""

    # Show list if requested or no names provided
    if list_all or not names:
        show_available_items()
        return

    # Get source directories using import system (works for installed packages)
    import connectonion.useful_tools as tools_module
    import connectonion.useful_plugins as plugins_module

    useful_tools_dir = Path(tools_module.__file__).parent
    useful_plugins_dir = Path(plugins_module.__file__).parent

    current_dir = Path.cwd()

    for name in names:
        name_lower = name.lower()

        # Check if it's a tool
        if name_lower in TOOLS:
            source = useful_tools_dir / TOOLS[name_lower]
            dest_dir = Path(path) if path else current_dir / "tools"
            copy_file(source, dest_dir, force)

        # Check if it's a plugin
        elif name_lower in PLUGINS:
            source = useful_plugins_dir / PLUGINS[name_lower]
            dest_dir = Path(path) if path else current_dir / "plugins"
            copy_file(source, dest_dir, force)

        else:
            console.print(f"[red]Unknown: {name}[/red]")
            console.print("Use [cyan]co copy --list[/cyan] to see available items")


def copy_file(source: Path, dest_dir: Path, force: bool):
    """Copy a single file to destination."""
    if not source.exists():
        console.print(f"[red]Source not found: {source}[/red]")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.name

    if dest.exists() and not force:
        console.print(f"[yellow]Skipped: {dest} (exists, use --force)[/yellow]")
        return

    shutil.copy2(source, dest)
    console.print(f"[green]✓ Copied: {dest}[/green]")


def show_available_items():
    """Display available tools and plugins."""
    table = Table(title="Available Items to Copy")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("File")

    for name, file in sorted(TOOLS.items()):
        table.add_row(name, "tool", file)

    for name, file in sorted(PLUGINS.items()):
        table.add_row(name, "plugin", file)

    console.print(table)
    console.print("\n[dim]Usage: co copy <name> [--path ./custom/][/dim]")
