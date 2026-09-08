"""Copyable next commands retain the explicitly selected account in every shell.

Every tip printed by this CLI names a `co` command spelled out, because the
reader is usually an agent that has nothing but this output and will otherwise
invent a command name. tests/unit/test_cli_tips_name_real_commands.py sweeps
the source for tip strings and checks each named command against the register.
"""

import re
from pathlib import Path
from typing import Sequence

from ...environment import explicit_env_file, selected_command


def selected_tip(message: str) -> str:
    """Apply the selector to CLI-authored tips, never to provider text or content."""
    if explicit_env_file() is None:
        return message
    # A real command, because the tip sweep reads every `co …` string in this
    # package and would flag a made-up one.
    prefix = selected_command("co status").removesuffix("status")
    return re.sub(r"(?<![\w-])co (?!\-\-env-file\b)", lambda _: prefix, message)


def print_tip(message: str) -> None:
    """Print a plain, unwrapped tip; markup in a user-supplied path stays literal."""
    message = re.sub(r"\[/?(?:bold|dim|yellow|cyan|red|green)(?: [a-z]+)?\]", "", message)
    print(selected_tip(message))


def rotating_tip(group: str, tips: Sequence[str]) -> str:
    """The next tip from `tips`, advancing a per-group cursor kept in ~/.co.

    For commands with no single next step — `co status`, or any `co browser`
    verb — where the useful thing to teach is the rest of the surface, one
    tip per run. Rotation was written for the browser and lived there; a
    second caller is what made it a shared helper. The cursor file is
    ~/.co/.<group>_tip, so the browser keeps the path it already had.

    A garbled cursor (two commands racing the write) resets to the first tip
    rather than crashing the command it decorates.
    """
    state = Path.home() / ".co" / f".{group}_tip"
    raw = state.read_text(encoding="utf-8").strip() if state.exists() else ""
    idx = int(raw) if raw.isdigit() else 0
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(str((idx + 1) % len(tips)), encoding="utf-8")
    return selected_tip(tips[idx % len(tips)])


# What `co status` teaches, one per run. Each names a command, not a page:
# the purchase URL stays on the low-balance warning, where it is the fix.
STATUS_TIPS = [
    "Token expired or account changed? Re-authenticate:  co auth",
    "Something off with the install? Diagnose it:  co doctor",
    "See every command and subcommand, one per line:  co commands",
    "Show the keys behind this identity:  co keys",
    "Put an agent on a server you own:  co server ls",
]
