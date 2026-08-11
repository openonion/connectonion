"""
Purpose: `co telegram send` — put a message on Telegram from the terminal
LLM-Note:
  Dependencies: imports from [sys, rich.console, rich.text, useful_tools.telegram.send_telegram] | imported by [cli/main.py via telegram_send()] | tested by [tests/unit/test_telegram.py]
  Data flow: handle_telegram_send(chat, message) → send_telegram() → prints the outcome → exit 0 on success, 1 on failure
  State/Effects: one HTTP POST via the tool | no local state
  Integration: same shape as handle_email_send — a thin handler over the tool an agent already has
  Errors: a refused send or a missing token prints Telegram's own reason and exits 1
"""

import sys

from rich.console import Console
from rich.text import Text

from ...useful_tools.telegram import send_telegram

console = Console()


def handle_telegram_send(chat: str, message: str) -> int:
    """Send one message and say what happened."""
    result = send_telegram(chat, message)

    if not result["success"]:
        console.print(Text(str(result["error"]), style="red"))
        sys.exit(1)

    console.print(
        Text(f"Sent to {chat} (message {result['message_id']})", style="green")
    )
    return 0
