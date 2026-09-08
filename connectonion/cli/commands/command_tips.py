"""Copyable next commands retain the explicitly selected account in every shell.

Every tip printed by this CLI names a `co` command spelled out, because the
reader is usually an agent that has nothing but this output and will otherwise
invent a command name. tests/unit/test_cli_tips_name_real_commands.py sweeps
the source for tip strings and checks each named command against the register.
"""

import os
import re
import sys
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


HANDLER = None   # the handler prints its own, data-dependent tip (e.g. "co gmail read <#>")

# The next step after each command, printed by _OneSuggestion.invoke when the
# command returns normally. A value is the tip; HANDLER means the handler
# already prints one that depends on what it found — a listing that says
# "co gmail read <#>" only when there is something to read — and a static
# line here would be a second, contradicting tip. A key ending in " *"
# covers every command under that group (syno, gmail and the other Google
# surfaces all tip from one shared exit point).
#
# Audited 2026-09-08 over every command: which ended on a URL, a file path,
# `✓ done.` or nothing. Everything below that is not HANDLER was one of those.
NEXT = {
    # -- top level --
    "co ai": HANDLER,                 # the answer is the output
    "co announce": "Give subscribers the address they follow:  co keys",
    "co auth": HANDLER,               # every path ends "Next: co status" / "co outlook inbox"
    "co browser": HANDLER,            # rotating tip on stderr; exits by raise
    "co call": HANDLER,               # prints the remote's own output; exits by raise
    "co commands": HANDLER,           # ends with the --help pointer itself
    "co copy": HANDLER,               # "co copy --list" after a copy; --list ends with usage
    "co create": HANDLER,             # "co deploy" after the resources block
    "co deploy": HANDLER,             # cloud: "co status"; --to: the journalctl line
    "co doctor": HANDLER,             # "Run 'co auth' if you need to authenticate"
    "co eval": 'Fix what failed with the AI:  co ai "<what to fix>"',
    "co init": HANDLER,               # global: "co init ./"; project: "co deploy"
    "co keys": HANDLER,               # "co keys --reveal" / "co status" / "co keys --ssh --write"
    "co proxy": HANDLER,              # every verb ends with a co proxy command; exits by raise
    "co remote-browser": HANDLER,     # prints the remote's next_actions; exits by raise
    "co reset": "Confirm the new identity:  co status",
    "co setup": "Preview what would be published:  co announce --dry-run",
    "co status": HANDLER,             # rotating STATUS_TIPS
    "co transfer": HANDLER,           # "co transfer list" / "co transfer <address> <amount>"
    # -- groups --
    "co email send": HANDLER,
    "co email inbox": HANDLER,
    "co email read": 'Reply from this address:  co email send <sender> "<subject>" "<body>"',
    "co email sent read": "Back to the list:  co email sent",
    "co email addresses": HANDLER,
    "co email default": "See every address and which is default:  co email addresses",
    "co email name": HANDLER,
    "co email share": HANDLER,
    "co email unshare": "See remaining grants:  co email share --list",
    "co email upgrade": "See the new balance:  co status",
    "co gcalendar *": HANDLER,
    "co gdrive *": HANDLER,
    "co gmail *": HANDLER,
    "co outlook inbox": HANDLER,
    "co outlook read": HANDLER,
    "co outlook reply": "See it in sent mail:  co outlook sent",
    "co outlook send": "See it in sent mail:  co outlook sent",
    "co outlook sent": "Back to the inbox:  co outlook inbox",
    "co outlook search": HANDLER,
    "co outlook download": "Back to the inbox:  co outlook inbox",
    "co outlook scheduled": HANDLER,
    "co outlook cancel": "What is still scheduled:  co outlook scheduled",
    "co outlook contact add": "See every contact:  co outlook contact list",
    "co outlook contact list": 'Send to one:  co outlook send <email> "<subject>" "<body>"',
    "co outlook contact search": 'Send to one:  co outlook send <email> "<subject>" "<body>"',
    "co server add": HANDLER,
    "co server ls": HANDLER,
    "co server check": "Deploy to it:  co deploy --to <name>",
    "co server new": HANDLER,
    "co server ssh": "Deploy to it:  co deploy --to <name>",
    "co server fix-key": HANDLER,
    "co server forget": HANDLER,
    "co server destroy": "What you still have:  co server ls",
    "co skills discover": "Copy one into ~/.co/skills:  co skills copy <name from this index>",
    "co skills copy": "What is installed now:  co skills list",
    "co skills manifest": "Preview what would be published:  co announce --dry-run",
    "co skills list": "Link them into Claude Code and Codex:  co skills link",
    "co skills link": "What is linked now:  co skills list",
    "co sms pair": "Read what the phone uploads:  co sms inbox",
    "co sms inbox": "See paired phones:  co sms devices",
    "co sms devices revoke": "See remaining phones:  co sms devices",
    "co sub sync": HANDLER,
    "co sub list": HANDLER,
    "co sub remove": HANDLER,
    "co syno *": HANDLER,
    "co telegram send": 'Send another:  co telegram send <chat> "<message>"',
    "co trust list": "Check one address:  co trust level <address>",
    "co trust level": "Make it a contact:  co trust add <address>",
    "co trust add": "See every list:  co trust list",
    "co trust remove": "See every list:  co trust list",
    "co trust block": "See every list:  co trust list",
    "co trust unblock": "See every list:  co trust list",
    "co trust admin add": "See every list:  co trust list",
    "co trust admin remove": "See every list:  co trust list",
    "co youtube *": HANDLER,
}


def next_step_for(path: str):
    """The NEXT entry for a command path: exact key first, then the nearest
    `<group> *` wildcard. Missing → KeyError, which the coverage test turns
    into a named failure."""
    if path in NEXT:
        return NEXT[path]
    words = path.split()
    for n in range(len(words) - 1, 0, -1):
        key = " ".join(words[:n]) + " *"
        if key in NEXT:
            return NEXT[key]
    raise KeyError(path)


def tips_enabled() -> bool:
    """False when the user asked for no tips: `co --no-tips <command>` for one
    run, or CO_TIPS=off (also 0/false/no) in the environment for every run.
    Covers the Next: line and the rotating status/browser tips alike; error
    text is never a tip and is never suppressed."""
    if _SUPPRESSED:
        return False
    return os.environ.get("CO_TIPS", "").strip().lower() not in ("0", "off", "false", "no")


_SUPPRESSED = False


def suppress_tips() -> None:
    global _SUPPRESSED
    _SUPPRESSED = True


def print_next_step(path: str) -> None:
    """After a command returns normally, name the next command.

    Called from _OneSuggestion.invoke with the leaf's full path. Prints on
    stderr: stdout stays the command's data (a `--json` caller parses it),
    and stderr survives `| cat` and reaches a capturing agent all the same.
    Dim only when stderr is a terminal so a log file gets plain text.

    A path mapped to HANDLER prints nothing here — the handler already
    printed a tip that depends on what it found, which this table cannot
    know. A path missing from the table also prints nothing, and the test
    in tests/unit/test_every_command_has_a_next_step.py fails on it.
    """
    if not tips_enabled():
        return
    try:
        tip = next_step_for(path)
    except KeyError:
        return          # the coverage test, not the user, reports this
    if not tip:
        return
    line = f"Next: {selected_tip(tip)}"
    if sys.stderr.isatty():
        line = f"\033[2m{line}\033[0m"
    print(line, file=sys.stderr, flush=True)


# What `co status` teaches, one per run. Each names a command, not a page:
# the purchase URL stays on the low-balance warning, where it is the fix.
STATUS_TIPS = [
    "Token expired or account changed? Re-authenticate:  co auth",
    "Something off with the install? Diagnose it:  co doctor",
    "See every command and subcommand, one per line:  co commands",
    "Show the keys behind this identity:  co keys",
    "Put an agent on a server you own:  co server ls",
]
