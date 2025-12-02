"""
Purpose: Entry point for ConnectOnion CLI application using Typer framework with Rich formatting
LLM-Note:
  Dependencies: imports from [typer, rich.console, typing, __version__] | imported by [setup.py entry_points, __main__.py] | loads commands from [cli/commands/{init, create, deploy, auth, status, reset, doctor, browser}_commands.py] | tested by [tests/cli/test_cli_help.py]
  Data flow: cli() entry point → creates Typer app → registers command callbacks (init, create, deploy, auth, status, reset, doctor, browser) → Typer parses args → invokes corresponding handle_*() function from commands module → command outputs via rich.Console
  State/Effects: no persistent state | writes to stdout via rich.Console | lazy imports command handlers on invocation | registers typer.Option and typer.Argument decorators | uses typer.Exit() for early termination
  Integration: exposes cli() entry point registered in setup.py as 'co' command | app() is the Typer instance | commands: init, create, deploy, auth [google|microsoft], status, reset, doctor, browser | --version flag shows version | -b/--browser flag shortcuts browser command | no args shows custom help via _show_help()
  Performance: fast startup (lazy imports) | Typer arg parsing is O(n) args | Rich console initialization is lightweight
  Errors: typer.Exit() on --version or --browser | invalid commands show Typer error with suggestions | command-specific errors handled in respective handlers
"""

import typer
from rich.console import Console
from typing import Optional

from .. import __version__

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
    browser: Optional[str] = typer.Option(None, "-b", "--browser", help="Quick browser command"),
):
    """ConnectOnion - A simple Python framework for creating AI agents."""
    if browser:
        from .commands.browser_commands import handle_browser
        handle_browser(browser)
        raise typer.Exit()
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
    console.print("  [green]deploy[/green]            Deploy to ConnectOnion Cloud")
    console.print("  [green]auth[/green]              Authenticate for managed keys")
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
def browser(command: str = typer.Argument(..., help="Browser command")):
    """Browser automation."""
    from .commands.browser_commands import handle_browser
    handle_browser(command)


def cli():
    """Entry point."""
    app()


if __name__ == "__main__":
    cli()
