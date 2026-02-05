"""
Purpose: CLI command to copy built-in tools, plugins, and prompts to user's project for customization
LLM-Note:
  Dependencies: imports from [shutil, pathlib, typing, rich] | imported by [cli/main.py via handle_copy()]
  Data flow: user runs `co copy <name>` → looks up name in TOOLS/PLUGINS/PROMPTS registry → finds source via module.__file__ → copies to ./tools/, ./plugins/, or ./prompts/
  State/Effects: creates tools/, plugins/, or prompts/ directory if needed | copies files/directories from installed package to user's project
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
    "ask_user": "ask_user.py",
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
    "system_reminder": "system_reminder.py",
}

# Plugins that also need prompts copied
PLUGIN_PROMPTS = {
    "system_reminder": "system-reminders",
}

# Registry of copyable TUI components
TUI = {
    "chat": "chat.py",
    "fuzzy": "fuzzy.py",
    "divider": "divider.py",
    "footer": "footer.py",
    "status_bar": "status_bar.py",
    "dropdown": "dropdown.py",
    "pick": "pick.py",
    "keys": "keys.py",
}

# Registry of copyable prompt templates (directories)
PROMPTS = {
    "coding_agent": "coding_agent",
}

# Registry of copyable trust policies
TRUST = {
    "open": "open.md",
    "careful": "careful.md",
    "strict": "strict.md",
}


def handle_copy(
    names: List[str],
    list_all: bool = False,
    path: Optional[str] = None,
    force: bool = False
):
    """Copy built-in tools, plugins, and prompts to user's project."""

    # Show list if requested or no names provided
    if list_all or not names:
        show_available_items()
        return

    # Get source directories using import system (works for installed packages)
    import connectonion.useful_tools as tools_module
    import connectonion.useful_plugins as plugins_module
    import connectonion.tui as tui_module
    import connectonion.useful_prompts as prompts_module
    import connectonion

    useful_tools_dir = Path(tools_module.__file__).parent
    useful_plugins_dir = Path(plugins_module.__file__).parent
    tui_dir = Path(tui_module.__file__).parent
    useful_prompts_dir = Path(prompts_module.__file__).parent
    # Trust policies are in the main package's prompts/trust/ directory
    trust_dir = Path(connectonion.__file__).parent.parent / "prompts" / "trust"

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

            # Also copy associated prompts if any
            if name_lower in PLUGIN_PROMPTS:
                prompt_source = useful_prompts_dir / PLUGIN_PROMPTS[name_lower]
                prompt_dest = Path(path) if path else current_dir / "prompts"
                copy_directory(prompt_source, prompt_dest, force)

        # Check if it's a TUI component
        elif name_lower in TUI:
            source = tui_dir / TUI[name_lower]
            dest_dir = Path(path) if path else current_dir / "tui"
            copy_file(source, dest_dir, force)

        # Check if it's a prompt template
        elif name_lower in PROMPTS:
            source = useful_prompts_dir / PROMPTS[name_lower]
            dest_dir = Path(path) if path else current_dir / "prompts"
            copy_directory(source, dest_dir, force)

        # Check if it's a trust policy (support both "careful" and "trust/careful")
        elif name_lower in TRUST or (name_lower.startswith("trust/") and name_lower[6:] in TRUST):
            policy_name = name_lower[6:] if name_lower.startswith("trust/") else name_lower
            source = trust_dir / TRUST[policy_name]
            dest_dir = Path(path) if path else current_dir / "prompts" / "trust"
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


def copy_directory(source: Path, dest_dir: Path, force: bool):
    """Copy an entire directory to destination."""
    if not source.exists():
        console.print(f"[red]Source not found: {source}[/red]")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.name

    if dest.exists():
        if not force:
            console.print(f"[yellow]Skipped: {dest} (exists, use --force)[/yellow]")
            return
        shutil.rmtree(dest)

    shutil.copytree(source, dest)
    console.print(f"[green]✓ Copied: {dest}/[/green]")


def show_available_items():
    """Display available tools, plugins, prompts, and TUI components."""
    table = Table(title="Available Items to Copy")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Path")

    for name, file in sorted(TOOLS.items()):
        table.add_row(name, "tool", file)

    for name, file in sorted(PLUGINS.items()):
        table.add_row(name, "plugin", file)

    for name, dir_name in sorted(PROMPTS.items()):
        table.add_row(name, "prompt", f"{dir_name}/")

    for name, file in sorted(TRUST.items()):
        table.add_row(f"trust/{name}", "trust", file)

    for name, file in sorted(TUI.items()):
        table.add_row(name, "tui", file)

    console.print(table)
    console.print("\n[dim]Usage: co copy <name> [--path ./custom/][/dim]")
    console.print("[dim]Prompts are copied as directories to ./prompts/<name>/[/dim]")
    console.print("[dim]Trust policies are copied to ./prompts/trust/<name>.md[/dim]")
