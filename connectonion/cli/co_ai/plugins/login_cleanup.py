"""Cleanup for co ai login handoff browser sessions."""

from connectonion.core.events import on_complete
from connectonion.useful_tools.login_handoff import close_browser


@on_complete
def close_login_browser_on_complete(agent) -> None:
    """Close the server-side browser after a login handoff turn completes."""
    if not getattr(agent, "_login_handoff_active", False):
        return

    close_browser(agent)


login_cleanup = [close_login_browser_on_complete]
