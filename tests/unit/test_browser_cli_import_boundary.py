"""Direct browser RPCs must reach the daemon without importing its whole runtime."""

import json
import subprocess
import sys


def test_direct_browser_command_import_stays_lightweight():
    """Regression for #1248: every polling command used to load Agent/Playwright.

    This must run in a child interpreter because the browser daemon test suite
    intentionally imports those modules while collecting its server-side tests.
    """
    script = r"""
import json
import sys
import connectonion.cli.commands.browser_commands

heavy = (
    "connectonion.cli.browser_agent.daemon",
    "connectonion.cli.browser_agent.agent",
    "connectonion.useful_tools.browser_tools",
    "patchright.sync_api",
)
print(json.dumps({name: name in sys.modules for name in heavy}, sort_keys=True))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert json.loads(result.stdout) == {
        "connectonion.cli.browser_agent.agent": False,
        "connectonion.cli.browser_agent.daemon": False,
        "connectonion.useful_tools.browser_tools": False,
        "patchright.sync_api": False,
    }
