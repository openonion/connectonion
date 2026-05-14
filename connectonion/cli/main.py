"""
Purpose: Entry point for ConnectOnion CLI application using Typer framework with Rich formatting
LLM-Note:
  Dependencies: imports from [typer, rich.console, typing, __version__] | imported by [setup.py entry_points, __main__.py] | loads commands from [cli/commands/{init, create, deploy, auth, status, reset, doctor, browser}_commands.py] | tested by [tests/e2e/cli/test_cli_help.py]
  Data flow: cli() entry point → creates Typer app → registers command callbacks (init, create, deploy, auth, status, reset, doctor, browser) → Typer parses args → invokes corresponding handle_*() function from commands module → command outputs via rich.Console
  State/Effects: no persistent state | writes to stdout via rich.Console | lazy imports command handlers on invocation | registers typer.Option and typer.Argument decorators | uses typer.Exit() for early termination
  Integration: exposes cli() entry point registered in setup.py as 'co' command | app() is the Typer instance | commands: init, create, deploy, auth [google|microsoft], status, reset, doctor, browser | --version flag shows version | -b/--browser flag shortcuts browser command | no args shows custom help via _show_help()
  Performance: fast startup (lazy imports) | Typer arg parsing is O(n) args | Rich console initialization is lightweight
  Errors: typer.Exit() on --version or --browser | invalid commands show Typer error with suggestions | command-specific errors handled in respective handlers
"""

import typer
from pathlib import Path
from rich.console import Console
from typing import Optional, List
from dotenv import load_dotenv

from .. import __version__

# Load global keys.env for all CLI commands
_global_keys = Path.home() / ".co" / "keys.env"
if _global_keys.exists():
    load_dotenv(_global_keys)

console = Console()
app = typer.Typer(add_completion=False, no_args_is_help=False)


def version_callback(value: bool):
    if value:
        console.print(f"co {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", callback=version_callback, is_eager=True),
):
    """ConnectOnion - A simple Python framework for creating AI agents."""
    if ctx.invoked_subcommand is None:
        _show_help()


def _show_help():
    """Show help message."""
    console.print()
    console.print(f"[bold cyan]co[/bold cyan] - ConnectOnion v{__version__}")
    console.print()
    console.print("A simple Python framework for creating AI agents.")
    console.print()
    console.print("[bold]Quick Start:[/bold]")
    console.print("  [cyan]co create my-agent[/cyan]                Create new agent project")
    console.print("  [cyan]cd my-agent && python agent.py[/cyan]   Run your agent")
    console.print()
    console.print("[bold]Commands:[/bold]")
    console.print("  [green]create[/green]  <name>     Create new project")
    console.print("  [green]init[/green]              Initialize in current directory")
    console.print("  [green]copy[/green]   <name>     Copy tool/plugin source to project")
    console.print("  [green]eval[/green]              Run evals and show status")
    console.print("  [green]trust[/green]             Manage trust lists")
    console.print("  [green]deploy[/green]            Deploy to ConnectOnion Cloud")
    console.print("  [green]auth[/green]              Authenticate for managed keys")
    console.print("  [green]keys[/green]              Show agent keys and credentials")
    console.print("  [green]status[/green]            Check account balance")
    console.print("  [green]doctor[/green]            Diagnose installation")
    console.print()
    console.print("[bold]Docs:[/bold] https://docs.connectonion.com")
    console.print("[bold]Discord:[/bold] https://discord.gg/4xfD9k8AUF")
    console.print()


@app.command()
def init(
    template: Optional[str] = typer.Option(None, "-t", "--template", help="Template: minimal, playwright, custom"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip prompts"),
    key: Optional[str] = typer.Option(None, "--key", help="API key"),
    description: Optional[str] = typer.Option(None, "--description", help="Description for custom template"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
):
    """Initialize project in current directory."""
    from .commands.init import handle_init
    handle_init(ai=None, key=key, template=template, description=description, yes=yes, force=force)


@app.command()
def create(
    name: Optional[str] = typer.Argument(None, help="Project name"),
    template: Optional[str] = typer.Option(None, "-t", "--template", help="Template: minimal, playwright, custom"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip prompts"),
    key: Optional[str] = typer.Option(None, "--key", help="API key"),
    description: Optional[str] = typer.Option(None, "--description", help="Description for custom template"),
):
    """Create new project."""
    from .commands.create import handle_create
    handle_create(name=name, ai=None, key=key, template=template, description=description, yes=yes)


@app.command()
def deploy():
    """Deploy to ConnectOnion Cloud."""
    from .commands.deploy_commands import handle_deploy
    handle_deploy()


@app.command()
def auth(service: Optional[str] = typer.Argument(None, help="Service: google, microsoft")):
    """Authenticate with OpenOnion."""
    if service == "google":
        from .commands.auth_commands import handle_google_auth
        handle_google_auth()
    elif service == "microsoft":
        from .commands.auth_commands import handle_microsoft_auth
        handle_microsoft_auth()
    else:
        from .commands.auth_commands import handle_auth
        handle_auth()


@app.command()
def keys(
    reveal: bool = typer.Option(False, "--reveal", "-r", help="Show full key values"),
):
    """Show agent keys and credentials."""
    from .commands.keys_commands import handle_keys
    handle_keys(reveal=reveal)


@app.command()
def status():
    """Check account status."""
    from .commands.status_commands import handle_status
    handle_status()


@app.command()
def reset():
    """Reset account (destructive)."""
    from .commands.reset_commands import handle_reset
    handle_reset()


@app.command()
def doctor():
    """Diagnose installation."""
    from .commands.doctor_commands import handle_doctor
    handle_doctor()


@app.command()
def browser(
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser headless"),
    command: str = typer.Argument(..., help="Browser command"),
):
    """Browser automation."""
    from .commands.browser_commands import handle_browser
    handle_browser(command, headless=headless)


@app.command()
def ai(
    prompt: Optional[str] = typer.Argument(None, help="One-shot prompt (runs and exits)"),
    port: int = typer.Option(8000, "--port", "-p", help="Port for web server"),
    model: str = typer.Option("co/gemini-3-flash-preview", "--model", "-m", help="Model to use"),
    max_iterations: int = typer.Option(100, "--max-iterations", "-i", help="Max iterations"),
):
    """Start AI coding agent or run one-shot prompt."""
    from .commands.ai_commands import handle_ai
    handle_ai(prompt=prompt, port=port, model=model, max_iterations=max_iterations)


@app.command()
def copy(
    names: List[str] = typer.Argument(None, help="Tool or plugin names to copy"),
    list_all: bool = typer.Option(False, "--list", "-l", help="List available items"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Custom destination path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files"),
):
    """Copy built-in tools/plugins to customize."""
    from .commands.copy_commands import handle_copy
    handle_copy(names=names or [], list_all=list_all, path=path, force=force)


@app.command()
def eval(
    name: Optional[str] = typer.Argument(None, help="Specific eval name"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent file (overrides YAML)"),
):
    """Run evals and show results."""
    from .commands.eval_commands import handle_eval
    handle_eval(name=name, agent_file=agent)


@app.command()
def setup(
    bio: Optional[str] = typer.Option(None, "--bio", "-b", help="One-line bio for ~/.co/agent.json"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Alias/name for ~/.co/agent.json (default: $USER)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing ~/.co/agent.json (backs up to .bak)"),
    skip_skills: bool = typer.Option(False, "--no-skills", help="Skip ~/.co/skills/ library refresh"),
):
    """Set up your global ~/.co/ — identity, agent.json, and skill library."""
    from .commands.setup_commands import handle_setup
    handle_setup(name=name, bio=bio, force=force, skip_skills=skip_skills)


@app.command()
def announce(
    relay: Optional[str] = typer.Option(None, "--relay", "-r", help="Relay URL (default: wss://oo.openonion.ai)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the signed message, don't send"),
):
    """Publish ~/.co/agent.json + SKILL.md bodies (publish:true) to the relay."""
    from .commands.announce_commands import handle_announce
    handle_announce(relay=relay, dry_run=dry_run)


# Skills command group
skills_app = typer.Typer(help="Discover, copy, and list SKILL.md files from agent tool directories")
app.add_typer(skills_app, name="skills")


@skills_app.callback(invoke_without_command=True)
def skills_callback(ctx: typer.Context):
    """Skill discovery and management."""
    if ctx.invoked_subcommand is None:
        from .commands.skills_commands import handle_skills_list
        handle_skills_list()


@skills_app.command("discover")
def skills_discover(
    no_save: bool = typer.Option(False, "--no-save", help="Don't write ~/.co/skills/index.json"),
    json_out: bool = typer.Option(False, "--json", help="Print index as JSON"),
    include_namespaced: bool = typer.Option(False, "--include-namespaced", help="Include plugin-namespaced skills (names with ':')"),
):
    """Scan ~/.claude, ~/.codex, ~/.cursor, ~/.kiro, .co/skills for SKILL.md files."""
    from .commands.skills_commands import handle_skills_discover
    handle_skills_discover(save=not no_save, json_out=json_out, include_namespaced=include_namespaced)


@skills_app.command("copy")
def skills_copy(
    names: List[str] = typer.Argument(None, help="Skill names to copy into ~/.co/skills/"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Restrict to a specific source (claude, codex, cursor, kiro, co-user, co-project)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing skill"),
    all_: bool = typer.Option(False, "--all", "-a", help="Copy every discovered skill (dedupe by SOURCES priority)"),
):
    """Copy a discovered skill into ~/.co/skills/<name>/."""
    from .commands.skills_commands import handle_skills_copy
    handle_skills_copy(names=names or [], source=source, force=force, all_=all_)


@skills_app.command("manifest")
def skills_manifest(
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Skills directory to scan (default: ~/.co/skills/)"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Write to file (default: merge into ~/.co/agent.json); if path ends in agent.json, merge into its skills[] key"),
    stdout: bool = typer.Option(False, "--stdout", help="Print JSON to stdout instead of writing"),
):
    """Build skill metadata for oo-publish."""
    from .commands.skills_commands import handle_skills_manifest
    handle_skills_manifest(path=path, out=out, stdout=stdout)


@skills_app.command("list")
def skills_list():
    """List skills currently installed in ~/.co/skills/."""
    from .commands.skills_commands import handle_skills_list
    handle_skills_list()


# Trust command group
trust_app = typer.Typer(help="Manage trust lists (contacts, whitelist, blocklist, admins)")
app.add_typer(trust_app, name="trust")


@trust_app.callback(invoke_without_command=True)
def trust_callback(ctx: typer.Context):
    """Trust list management."""
    if ctx.invoked_subcommand is None:
        # Default to list
        from .commands.trust_commands import handle_trust_list
        handle_trust_list()


@trust_app.command("list")
def trust_list():
    """List all trust lists."""
    from .commands.trust_commands import handle_trust_list
    handle_trust_list()


@trust_app.command("level")
def trust_level(address: str = typer.Argument(..., help="Address to check")):
    """Check trust level of an address."""
    from .commands.trust_commands import handle_trust_level
    handle_trust_level(address)


@trust_app.command("add")
def trust_add(
    address: str = typer.Argument(..., help="Address to add"),
    whitelist: bool = typer.Option(False, "-w", "--whitelist", help="Add to whitelist instead of contacts"),
):
    """Add address to contacts (default) or whitelist."""
    from .commands.trust_commands import handle_trust_add
    handle_trust_add(address, whitelist)


@trust_app.command("remove")
def trust_remove(address: str = typer.Argument(..., help="Address to remove")):
    """Remove address from all lists (demote to stranger)."""
    from .commands.trust_commands import handle_trust_remove
    handle_trust_remove(address)


@trust_app.command("block")
def trust_block(
    address: str = typer.Argument(..., help="Address to block"),
    reason: str = typer.Option("", "-r", "--reason", help="Reason for blocking"),
):
    """Block an address."""
    from .commands.trust_commands import handle_trust_block
    handle_trust_block(address, reason)


@trust_app.command("unblock")
def trust_unblock(address: str = typer.Argument(..., help="Address to unblock")):
    """Unblock an address."""
    from .commands.trust_commands import handle_trust_unblock
    handle_trust_unblock(address)


# Admin subcommand group
admin_app = typer.Typer(help="Manage admins (super admin only)")
trust_app.add_typer(admin_app, name="admin")


@admin_app.command("add")
def admin_add(address: str = typer.Argument(..., help="Address to add as admin")):
    """Add an admin."""
    from .commands.trust_commands import handle_admin_add
    handle_admin_add(address)


@admin_app.command("remove")
def admin_remove(address: str = typer.Argument(..., help="Address to remove from admins")):
    """Remove an admin."""
    from .commands.trust_commands import handle_admin_remove
    handle_admin_remove(address)


# Subscription command group. `co sub` (no args) syncs every subscription.
# `co sub sync <addr>` syncs one. `list` and `remove` are the secondary verbs.
sub_app = typer.Typer(help="Subscribe to published agents — sync skills from the relay into your coding agents")
app.add_typer(sub_app, name="sub")


@sub_app.callback(invoke_without_command=True)
def sub_callback(
    ctx: typer.Context,
    relay: Optional[str] = typer.Option(None, "--relay", help="Relay URL (default: https://oo.openonion.ai)"),
):
    """With no subcommand, sync every subscription in ~/.co/subscriptions.txt."""
    if ctx.invoked_subcommand is None:
        from .commands.sub_commands import handle_sub_sync_all
        handle_sub_sync_all(relay=relay)


@sub_app.command("sync")
def sub_sync(
    target: str = typer.Argument(..., help="0x address (or locally-pinned alias) to sync"),
    relay: Optional[str] = typer.Option(None, "--relay", help="Relay URL (default: https://oo.openonion.ai)"),
):
    """Sync one publisher: fetch profile, mirror skills, fan out to coding agents."""
    from .commands.sub_commands import handle_sub_sync_one
    handle_sub_sync_one(target, relay=relay)


@sub_app.command("list")
def sub_list():
    """List subscriptions (local only — no relay calls)."""
    from .commands.sub_commands import handle_sub_list
    handle_sub_list()


@sub_app.command("remove")
def sub_remove(target: str = typer.Argument(..., help="Alias or 0x address to unsubscribe from")):
    """Unsubscribe: drop record, uninstall fanout, remove mirrored bundle."""
    from .commands.sub_commands import handle_sub_remove
    handle_sub_remove(target)


def cli():
    """Entry point."""
    app()


if __name__ == "__main__":
    cli()
