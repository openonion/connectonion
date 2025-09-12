"""Main CLI entry point for ConnectOnion - Router for commands."""

import click
from typing import Optional

from .. import __version__


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option('-b', '--browser', help='Browser command - guide browser to do something (e.g., "screenshot localhost:3000")')
@click.pass_context
def cli(ctx, browser):
    """ConnectOnion - A simple Python framework for creating AI agents."""
    if browser:
        # Handle browser command immediately
        from .commands.browser_commands import handle_browser
        handle_browser(browser)
        ctx.exit()
    
    # If no command given, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option('--ai/--no-ai', default=None,
              help='Enable or disable AI features')
@click.option('--key', help='API key for AI provider')
@click.option('--template', '-t',
              type=click.Choice(['minimal', 'playwright', 'custom']),
              help='Template to use')
@click.option('--description', help='Description for custom template (requires AI)')
@click.option('--yes', '-y', is_flag=True, help='Skip all prompts, use defaults')
@click.option('--force', is_flag=True,
              help='Overwrite existing files')
def init(ai: Optional[bool], key: Optional[str], template: Optional[str],
         description: Optional[str], yes: bool, force: bool):
    """Initialize a ConnectOnion project in the current directory."""
    from .commands.project_commands import handle_init
    handle_init(ai, key, template, description, yes, force)


@cli.command()
@click.argument('name', required=False)
@click.option('--ai/--no-ai', default=None, 
              help='Enable or disable AI features')
@click.option('--key', help='API key for AI provider')
@click.option('--template', '-t',
              type=click.Choice(['minimal', 'playwright', 'custom']),
              help='Template to use')
@click.option('--description', help='Description for custom template (requires AI)')
@click.option('--yes', '-y', is_flag=True, help='Skip all prompts, use defaults')
def create(name: Optional[str], ai: Optional[bool], key: Optional[str], 
           template: Optional[str], description: Optional[str], yes: bool):
    """Create a new ConnectOnion project in a new directory."""
    from .commands.project_commands import handle_create
    handle_create(name, ai, key, template, description, yes)


@cli.command()
def auth():
    """Authenticate with OpenOnion for managed keys (co/ models).
    
    This command will:
    1. Load your agent's keys from .co/keys/
    2. Sign an authentication message
    3. Open your browser to complete authentication
    4. Save the token for future use
    """
    from .commands.auth_commands import handle_auth
    handle_auth()


@cli.command()
def register():
    """Register/authenticate in headless mode (no browser needed).
    
    This command will:
    1. Load your agent's keys from .co/keys/
    2. Sign an authentication message
    3. Directly authenticate with the backend
    4. Save the token for future use
    """
    from .commands.auth_commands import handle_register
    handle_register()


@cli.command()
@click.argument('command')
def browser(command):
    """Execute browser automation commands - guide browser to do something.
    
    This is an alternative to the -b flag. Both 'co -b' and 'co browser' are supported.
    """
    from .commands.browser_commands import handle_browser
    handle_browser(command)


# Entry points for both 'co' and 'connectonion' commands
def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()