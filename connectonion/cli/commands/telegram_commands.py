"""
Purpose: `co telegram send` — put a message on Telegram from the terminal
LLM-Note:
  Dependencies: imports from [sys, rich.console, rich.text, useful_tools.telegram.send_telegram] | imported by [cli/main.py via telegram_send()] | tested by [tests/unit/test_telegram.py]
  Data flow: handle_telegram_send(chat, message) → send_telegram() → prints the outcome → exit 0 on success, 1 on failure
  State/Effects: one HTTP POST via the tool | no local state
  Integration: same shape as handle_email_send — a thin handler over the tool an agent already has
  Errors: a refused send prints Telegram's own reason and `Next: co telegram check`, exit 1 | a missing token exits 3, as on every inbox verb
"""

import sys

from rich.console import Console
from rich.text import Text

from ...useful_tools.telegram import NO_TOKEN, send_telegram

console = Console()


def handle_telegram_send(chat: str, message: str) -> int:
    """Send one message and say what happened."""
    result = send_telegram(chat, message)

    if not result["success"]:
        error = str(result["error"])
        if error == NO_TOKEN:
            # Exit 3, as on every other inbox verb: not configured is a thing a
            # person fixes, and a supervisor that retries on 1 would retry it.
            console.print(Text(error, style="red"))
            sys.exit(3)
        # Telegram's own words, and the command that tells a revoked token
        # from a chat the bot is not in — never a refusal with no way on.
        console.print(Text(f"{error.rstrip('. ')}. Next: co telegram check", style="red"))
        sys.exit(1)

    console.print(
        Text(f"Sent to {chat} (message {result['message_id']})", style="green")
    )
    return 0
