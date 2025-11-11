"""
Purpose: CLI argument parser and command router for ConnectOnion framework
LLM-Note:
  Dependencies: imports from [argparse, rich.console, rich.panel, rich.text, __version__, commands/{init,create,auth_commands,reset_commands,status_commands,browser_commands}] | imported by [tests/cli/test_cli.py, tests/cli/test_cli_init.py, tests/cli/test_cli_create.py] | entry point defined in pyproject.toml [project.scripts]
  Data flow: receives sys.argv from shell → create_parser() builds argparse.ArgumentParser with 6 subcommands (init, create, auth, reset, status, browser) + --version + --browser flags → cli() parses args and routes to command handlers → command handlers execute and return exit code → main() wraps cli() with exception handling → sys.exit(code)
  State/Effects: no persistent state | dynamically imports command modules on demand (lazy loading) | writes to stdout/stderr via rich.Console | calls sys.exit() with code (1=error, 0=success) | KeyboardInterrupt exits with code 1 and "Cancelled by user" message
  Integration: exposes cli() and main() entry points | routes to 6 command handlers: init.handle_init(ai, key, template, description, yes, force), create.handle_create(name, ai, key, template, description, yes), auth_commands.handle_auth(), reset_commands.handle_reset(), status_commands.handle_status(), browser_commands.handle_browser(command) | shows Rich-formatted help via show_help() when no args provided | version display via --version flag
  Performance: lazy imports command modules (not loaded until subcommand invoked) | argument parsing is O(n) where n=number of args | show_help() renders static Rich Panel on each call
  Errors: catches KeyboardInterrupt (prints "Cancelled by user" and exits 1) | catches generic Exception (prints error to console and exits 1) | argparse handles --help and invalid arguments automatically | missing subcommand shows help via show_help()
"""

import sys
import argparse
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .. import __version__

console = Console()


def create_parser():
    """Create the main argument parser."""
    # Main parser with examples in epilog
    main_epilog = """
Examples:
  co init                              Initialize current directory
  co create my-agent                   Create named project
  co init --template playwright        Use browser automation template
  co auth                              Authenticate for managed keys
  co -b "screenshot localhost:3000"    Quick browser command

Documentation: https://docs.connectonion.com
Discord: https://discord.gg/4xfD9k8AUF
"""

    parser = argparse.ArgumentParser(
        prog='co',
        description='A simple Python framework for creating AI agents.',
        epilog=main_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    parser.add_argument(
        '-b', '--browser',
        metavar='CMD',
        help='Quick browser command (e.g., "screenshot localhost:3000")'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Init command
    init_epilog = """
Examples:
  co init                                      Interactive setup
  co init --template playwright                Use template without prompts
  co init --yes                                Use defaults, no prompts
  co init --ai --key sk-xxx                   Provide API key directly
  co init --template custom --description "..." AI-generated template

Files Created:
  agent.py           Main agent file
  .env               Environment variables
  .co/config.toml    Project configuration
  .gitignore         Git ignore rules

Documentation: https://docs.connectonion.com/cli/init
"""

    init_parser = subparsers.add_parser(
        'init',
        help='Initialize a ConnectOnion project in current directory',
        description='Initialize a ConnectOnion project in the current directory.',
        epilog=init_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    init_parser.add_argument(
        '--template', '-t',
        choices=['minimal', 'playwright', 'custom'],
        metavar='NAME',
        help='Template: minimal, playwright, custom'
    )
    init_parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip prompts, use defaults'
    )
    init_parser.add_argument(
        '--ai', '--no-ai',
        dest='ai',
        action='store',
        nargs='?',
        const=True,
        default=None,
        help='Enable or disable AI features'
    )
    init_parser.add_argument(
        '--key',
        metavar='KEY',
        help='API key for AI provider (or use .env)'
    )
    init_parser.add_argument(
        '--description',
        metavar='TEXT',
        help='Description for custom template (requires --ai)'
    )
    init_parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing files without confirmation'
    )

    # Create command
    create_epilog = """
Examples:
  co create my-agent                           Interactive setup
  co create my-agent --template playwright     Use template
  co create my-agent --yes                     Use defaults, no prompts
  co create email-bot --ai --key sk-xxx       Provide API key

Files Created:
  my-agent/agent.py           Main agent file
  my-agent/.env               Environment variables
  my-agent/.co/config.toml    Project configuration
  my-agent/.gitignore         Git ignore rules

Documentation: https://docs.connectonion.com/cli/create
"""

    create_parser = subparsers.add_parser(
        'create',
        help='Create a new ConnectOnion project in a new directory',
        description='Create a new ConnectOnion project in a new directory.',
        epilog=create_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    create_parser.add_argument(
        'name',
        nargs='?',
        help='Project name'
    )
    create_parser.add_argument(
        '--template', '-t',
        choices=['minimal', 'playwright', 'custom'],
        metavar='NAME',
        help='Template: minimal, playwright, custom'
    )
    create_parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip prompts, use defaults'
    )
    create_parser.add_argument(
        '--ai', '--no-ai',
        dest='ai',
        action='store',
        nargs='?',
        const=True,
        default=None,
        help='Enable or disable AI features'
    )
    create_parser.add_argument(
        '--key',
        metavar='KEY',
        help='API key for AI provider (or use .env)'
    )
    create_parser.add_argument(
        '--description',
        metavar='TEXT',
        help='Description for custom template (requires --ai)'
    )

    # Auth command
    auth_epilog = """
Examples:
  co auth    Authenticate with OpenOnion for managed keys

This command will:
  1. Load your agent's keys from .co/keys/
  2. Sign an authentication message
  3. Authenticate directly with the backend
  4. Save the token for future use

Documentation: https://docs.connectonion.com/cli/auth
"""

    auth_parser = subparsers.add_parser(
        'auth',
        help='Authenticate with OpenOnion for managed keys (co/ models)',
        description='Authenticate with OpenOnion for managed keys (co/ models).',
        epilog=auth_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Status command
    status_epilog = """
Examples:
  co status    Check your account balance and usage

Shows your balance, usage, and account information without re-authenticating.

Documentation: https://docs.connectonion.com/cli/status
"""

    status_parser = subparsers.add_parser(
        'status',
        help='Check account status and balance',
        description='Check your ConnectOnion account status.',
        epilog=status_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Reset command
    reset_epilog = """
Examples:
  co reset    Reset your account and create a new one

WARNING: This will delete all your data and create a new account.
You will lose your balance and transaction history.

Documentation: https://docs.connectonion.com/cli/reset
"""

    reset_parser = subparsers.add_parser(
        'reset',
        help='Reset account and create new one [destructive]',
        description='Reset your ConnectOnion account.',
        epilog=reset_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Browser command
    browser_epilog = """
Examples:
  co browser "screenshot localhost:3000"
  co browser "click on login button"
  co -b "fill form with test data"

Documentation: https://docs.connectonion.com/cli/browser
"""

    browser_parser = subparsers.add_parser(
        'browser',
        help='Execute browser automation commands',
        description='Execute browser automation commands.',
        epilog=browser_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    browser_parser.add_argument(
        'command',
        help='Browser command to execute'
    )

    # Doctor command
    doctor_epilog = """
Examples:
  co doctor    Run diagnostics on ConnectOnion installation

Checks:
  • System info (version, Python, paths)
  • Configuration files
  • API keys
  • Backend connectivity

Documentation: https://docs.connectonion.com/cli/doctor
"""

    doctor_parser = subparsers.add_parser(
        'doctor',
        help='Diagnose installation and configuration issues',
        description='Run comprehensive diagnostics on your ConnectOnion setup.',
        epilog=doctor_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    return parser


def show_help():
    """Display brief help information using Rich formatting (examples first)."""
    console.print()
    console.print(f"[bold cyan]co[/bold cyan] - ConnectOnion v{__version__}")
    console.print()
    console.print("A simple Python framework for creating AI agents.")
    console.print()

    console.print("[bold]Quick Start:[/bold]")
    console.print("  [cyan]co create my-agent[/cyan]                Create new agent project")
    console.print("  [cyan]cd my-agent && python agent.py[/cyan]   Run your agent")
    console.print()

    console.print("[bold]Project Commands:[/bold]")
    console.print("  [green]create[/green]  [dim]<name>[/dim]     Create new project in new directory")
    console.print("  [green]init[/green]              Initialize project in current directory")
    console.print()

    console.print("[bold]Authentication & Account:[/bold]")
    console.print("  [green]auth[/green]              Authenticate for managed keys (co/ models)")
    console.print("  [green]status[/green]            Check account balance and usage")
    console.print("  [yellow]reset[/yellow]             Reset account (destructive - deletes data)")
    console.print()

    console.print("[bold]Utilities:[/bold]")
    console.print("  [cyan]doctor[/cyan]            Diagnose installation and config issues")
    console.print("  [cyan]browser[/cyan] [dim]<cmd>[/dim]     Execute browser automation commands")
    console.print()

    console.print("[bold]Options:[/bold]")
    console.print("  [cyan]-h, --help[/cyan]       Show this help message")
    console.print("  [cyan]--version[/cyan]        Show version number")
    console.print("  [cyan]-b, --browser[/cyan]    Quick browser shortcut (e.g., co -b \"screenshot url\")")
    console.print()

    console.print("[bold]Examples:[/bold]")
    console.print("  [dim]co create my-agent                     # Create new project[/dim]")
    console.print("  [dim]co init --template playwright          # Add to existing directory[/dim]")
    console.print("  [dim]co auth                                 # Get managed keys[/dim]")
    console.print("  [dim]co doctor                               # Check your setup[/dim]")
    console.print("  [dim]co -b \"screenshot localhost:3000\"      # Quick browser command[/dim]")
    console.print()

    console.print("[dim]Run 'co <command> --help' for detailed info on a command.[/dim]")
    console.print()
    console.print("[bold]Documentation:[/bold] https://docs.connectonion.com")
    console.print("[bold]Discord:[/bold] https://discord.gg/4xfD9k8AUF")
    console.print()


def cli():
    """Main CLI entry point."""
    parser = create_parser()

    # If no arguments provided, show help
    if len(sys.argv) == 1:
        show_help()
        return

    args = parser.parse_args()

    # Handle browser shortcut flag
    if args.browser:
        from .commands.browser_commands import handle_browser
        handle_browser(args.browser)
        return

    # Handle commands
    if args.command == 'init':
        from .commands.init import handle_init
        handle_init(
            ai=args.ai,
            key=args.key,
            template=args.template,
            description=args.description,
            yes=args.yes,
            force=args.force
        )
    elif args.command == 'create':
        from .commands.create import handle_create
        handle_create(
            name=args.name,
            ai=args.ai,
            key=args.key,
            template=args.template,
            description=args.description,
            yes=args.yes
        )
    elif args.command == 'auth':
        from .commands.auth_commands import handle_auth
        handle_auth()
    elif args.command == 'reset':
        from .commands.reset_commands import handle_reset
        handle_reset()
    elif args.command == 'status':
        from .commands.status_commands import handle_status
        handle_status()
    elif args.command == 'browser':
        from .commands.browser_commands import handle_browser
        handle_browser(args.command)
    elif args.command == 'doctor':
        from .commands.doctor_commands import handle_doctor
        handle_doctor()
    else:
        # If command is None but other args exist, show help
        show_help()


# Entry points for both 'co' and 'connectonion' commands
def main():
    """Main entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user.[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()