"""Main CLI entry point for ConnectOnion - Router for commands."""

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
    parser = argparse.ArgumentParser(
        prog='co',
        description='ConnectOnion - A simple Python framework for creating AI agents.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    parser.add_argument(
        '-b', '--browser',
        help='Browser command - guide browser to do something (e.g., "screenshot localhost:3000")'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Init command
    init_parser = subparsers.add_parser('init', help='Initialize a ConnectOnion project in the current directory')
    init_parser.add_argument('--ai', '--no-ai', dest='ai', action='store', nargs='?', const=True, default=None,
                           help='Enable or disable AI features')
    init_parser.add_argument('--key', help='API key for AI provider')
    init_parser.add_argument('--template', '-t',
                           choices=['minimal', 'playwright', 'custom'],
                           help='Template to use')
    init_parser.add_argument('--description', help='Description for custom template (requires AI)')
    init_parser.add_argument('--yes', '-y', action='store_true', help='Skip all prompts, use defaults')
    init_parser.add_argument('--force', action='store_true', help='Overwrite existing files')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new ConnectOnion project in a new directory')
    create_parser.add_argument('name', nargs='?', help='Project name')
    create_parser.add_argument('--ai', '--no-ai', dest='ai', action='store', nargs='?', const=True, default=None,
                             help='Enable or disable AI features')
    create_parser.add_argument('--key', help='API key for AI provider')
    create_parser.add_argument('--template', '-t',
                             choices=['minimal', 'playwright', 'custom'],
                             help='Template to use')
    create_parser.add_argument('--description', help='Description for custom template (requires AI)')
    create_parser.add_argument('--yes', '-y', action='store_true', help='Skip all prompts, use defaults')

    # Auth command
    auth_parser = subparsers.add_parser(
        'auth',
        help='Authenticate with OpenOnion for managed keys (co/ models)',
        description="""Authenticate with OpenOnion for managed keys (co/ models).

This command will:
1. Load your agent's keys from .co/keys/
2. Sign an authentication message
3. Authenticate directly with the backend
4. Save the token for future use"""
    )

    # Reset command
    reset_parser = subparsers.add_parser(
        'reset',
        help='Reset account and create new one',
        description="""Reset your ConnectOnion account.

WARNING: This will delete all your data and create a new account.
You will lose your balance and transaction history."""
    )

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Check account status and balance',
        description="""Check your ConnectOnion account status.

Shows your balance, usage, and account information without re-authenticating."""
    )

    # Browser command
    browser_parser = subparsers.add_parser('browser', help='Execute browser automation commands')
    browser_parser.add_argument('command', help='Browser command to execute')

    return parser


def show_help():
    """Display help information using Rich formatting."""
    title = Text("🧅 ConnectOnion CLI", style="bold cyan")

    content = """
A simple Python framework for creating AI agents.

[bold cyan]Commands:[/bold cyan]
  [green]init[/green]      Initialize a ConnectOnion project in current directory
  [green]create[/green]    Create a new ConnectOnion project in a new directory
  [green]auth[/green]      Authenticate with OpenOnion for managed keys
  [green]status[/green]    Check account status and balance
  [green]reset[/green]     Reset account and create new one
  [green]browser[/green]   Execute browser automation commands

[bold cyan]Options:[/bold cyan]
  [yellow]-h, --help[/yellow]     Show this help message
  [yellow]--version[/yellow]      Show version number
  [yellow]-b, --browser[/yellow]  Quick browser command

[bold cyan]Examples:[/bold cyan]
  [dim]# Initialize a new project[/dim]
  co init

  [dim]# Create a new project with a name[/dim]
  co create my-agent

  [dim]# Authenticate with OpenOnion[/dim]
  co auth

  [dim]# Take a screenshot[/dim]
  co -b "screenshot localhost:3000"

[bold cyan]Learn more:[/bold cyan]
  Docs: https://github.com/openonion/connectonion
  Discord: https://discord.gg/4xfD9k8AUF
"""

    panel = Panel(
        content,
        title=title,
        border_style="cyan",
        padding=(1, 2),
        expand=False
    )
    console.print(panel)


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