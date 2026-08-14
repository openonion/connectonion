"""
Purpose: `co discord send` — post to Discord from the terminal
LLM-Note:
  Dependencies: imports from [sys, rich.console, rich.text, useful_tools.discord.send_discord] | imported by [cli/main.py via discord_send()] | tested by [tests/unit/test_discord.py]
  Data flow: handle_discord_send(channel, message) → send_discord() → prints the outcome → exit 0 on success, 1 on failure
  State/Effects: one HTTP POST via the tool | no local state
  Integration: same shape as handle_telegram_send — a thin handler over the tool an agent already has
  Errors: a refused post or a missing token prints Discord's own reason and exits 1
"""

import sys

from rich.console import Console
from rich.text import Text

from ...useful_tools.discord import send_discord

console = Console()


def handle_discord_send(channel: str, message: str) -> int:
    """Post one message and say what happened."""
    result = send_discord(channel, message)

    if not result["success"]:
        console.print(Text(str(result["error"]), style="red"))
        sys.exit(1)

    console.print(Text(f"Posted to {result['channel']}", style="green"))
    return 0
