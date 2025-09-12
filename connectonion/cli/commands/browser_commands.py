"""Browser automation commands for ConnectOnion CLI."""

import click


def handle_browser(command: str):
    """Execute browser automation commands - guide browser to do something.
    
    This is an alternative to the -b flag. Both 'co -b' and 'co browser' are supported.
    
    Args:
        command: The browser command to execute
    """
    from ..browser_agent.browser import execute_browser_command
    result = execute_browser_command(command)
    click.echo(result)