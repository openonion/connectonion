"""Browser automation commands for ConnectOnion CLI."""

from rich.console import Console

console = Console()


def handle_browser(command: str):
    """Execute browser automation commands - guide browser to do something.

    This is an alternative to the -b flag. Both 'co -b' and 'co browser' are supported.

    Args:
        command: The browser command to execute
    """
    from ..browser_agent.browser import execute_browser_command
    result = execute_browser_command(command)
    console.print(result)