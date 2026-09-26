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


# Whether anything in this process has already told the caller what to run.
#
# `_OneSuggestion.main` adds `Next: co <group> --help` to a bare exit 2, because
# Click's own usage errors never reach a handler and "Try --help" names a flag
# rather than a command. But exit 2 is also what a handler raises when it refuses
# on purpose, and those have already named something far better — so the net was
# firing on top of a good tip and printing two. An agent reading `2>&1` sees the
# generic one first and resolves the fork by guessing.
_NEXT_STEP_NAMED = False

# "Next:" is the whole contract — a message without one has named no command, so
# the net must still fire for it.
_NAMES_A_NEXT_STEP = re.compile(r"(?m)^\s*Next:|(?<=[.\s])Next: ")


def next_step_already_named() -> bool:
    """True once something in this run has printed a `Next:` line."""
    return _NEXT_STEP_NAMED


def mark_next_step_named() -> None:
    """Record that a handler named the next step itself, on a stream print_tip
    does not use (stderr, so --json stdout stays parseable). Without it the exit-2
    net adds a second, generic tip under the real one."""
    global _NEXT_STEP_NAMED
    _NEXT_STEP_NAMED = True


def forget_next_step_named() -> None:
    """Reset the flag. For tests, which run many commands in one process."""
    global _NEXT_STEP_NAMED
    _NEXT_STEP_NAMED = False


def print_tip(message: str) -> None:
    """Print a plain, unwrapped tip; markup in a user-supplied path stays literal."""
    global _NEXT_STEP_NAMED
    message = re.sub(r"\[/?(?:bold|dim|yellow|cyan|red|green)(?: [a-z]+)?\]", "", message)
    if _NAMES_A_NEXT_STEP.search(message):
        _NEXT_STEP_NAMED = True
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
    "co browser": HANDLER,            # rotating tip on stderr; `import` names its own go_to check; exits by raise
    "co claude run": 'Continue this Claude session:  co claude run "<next task>" --session <session-id>',
    "co call": HANDLER,               # prints the remote's own output; exits by raise
    "co commands": HANDLER,
    "co audit": HANDLER,              # names --review, or the rerun after a fix           # ends with the --help pointer itself
    "co copy": HANDLER,               # "co copy --list" after a copy; --list ends with usage
    "co create": HANDLER,             # "co deploy" after the resources block
    "co deploy": HANDLER,             # cloud: "co status"; --to: the journalctl line
    "co doctor": HANDLER,             # "run 'co auth'" only when not authenticated
    "co benchmark list": HANDLER,     # empty: the schema and "check"; else "check <first invalid>"
    "co benchmark check": HANDLER,    # valid: "co eval run <name> ..."; invalid: "check <name>" again
    "co eval run": HANDLER,           # "co eval report <name> --latest"
    "co eval report": HANDLER,        # the first failing case, or "add a harder case"
    "co eval legacy": HANDLER,        # the older evals print their own tip (LEGACY_EVAL_TIP in main.py)
    "co init": HANDLER,               # global: "co init ./"; project: "co deploy"
    "co keys": HANDLER,               # "co keys --reveal" / "co status" / "co keys --ssh --write"
    "co proxy": HANDLER,              # every verb ends with a co proxy command; exits by raise
    "co remote-browser": HANDLER,     # prints the remote's next_actions; exits by raise
    "co reset": "Confirm the new identity:  co status",
    "co setup": "Preview what would be published:  co announce --dry-run",
    "co status": HANDLER,             # rotating STATUS_TIPS
    "co transfer": HANDLER,           # "co transfer list" / "co transfer <address> <amount>"
    # -- groups --
    "co feishu listen": "co feishu receive --timeout 0",
    "co feishu receive": "co feishu reply <message-id>",
    "co feishu send": "co feishu receive --timeout 0",
    "co feishu reply": "co feishu receive --timeout 0",
    "co feishu done": "co feishu receive --timeout 0",
    "co feishu edit": "co feishu log",
    "co feishu delete": "co feishu log",
    "co feishu react": "co feishu log",
    "co feishu check": HANDLER,  # every branch of _report_connection names its own
    "co feishu ls": "co feishu receive --timeout 0",
    "co feishu chats": HANDLER,
    "co feishu log": "co feishu ls",
    "co feishu consume": "co feishu ls",
    "co lark listen": "co lark receive --timeout 0",
    "co lark receive": "co lark reply <message-id>",
    "co lark send": "co lark receive --timeout 0",
    "co lark reply": "co lark receive --timeout 0",
    "co lark done": "co lark receive --timeout 0",
    "co lark edit": "co lark log",
    "co lark delete": "co lark log",
    "co lark react": "co lark log",
    "co lark check": HANDLER,  # every branch of _report_connection names its own
    "co lark ls": "co lark receive --timeout 0",
    "co lark chats": HANDLER,
    "co lark log": "co lark ls",
    "co lark consume": "co lark ls",
    "co whatsapp listen": "co whatsapp receive --timeout 0",
    "co whatsapp receive": "co whatsapp reply <message-id>",
    "co whatsapp send": "co whatsapp receive --timeout 0",
    "co whatsapp reply": "co whatsapp receive --timeout 0",
    "co whatsapp done": "co whatsapp receive --timeout 0",
    "co whatsapp edit": "co whatsapp log",
    "co whatsapp delete": "co whatsapp log",
    "co whatsapp react": "co whatsapp log",
    "co whatsapp group create": HANDLER,  # names the new chat id in its own tip
    "co whatsapp group add": HANDLER,
    "co whatsapp check": HANDLER,  # every branch of _report_connection names its own
    "co whatsapp ls": "co whatsapp receive --timeout 0",
    "co whatsapp chats": HANDLER,
    "co whatsapp log": "co whatsapp ls",
    "co whatsapp consume": "co whatsapp ls",
    "co discord listen": "co discord receive --timeout 0",
    "co discord receive": "co discord reply <message-id>",
    "co discord send": "co discord receive --timeout 0",
    "co discord reply": "co discord receive --timeout 0",
    "co discord done": "co discord receive --timeout 0",
    "co discord edit": "co discord log",
    "co discord delete": "co discord log",
    "co discord react": "co discord log",
    "co discord check": HANDLER,  # every branch of _report_connection names its own
    "co discord ls": "co discord receive --timeout 0",
    "co discord chats": HANDLER,
    "co discord log": "co discord ls",
    "co discord consume": "co discord ls",
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
    "co env *": HANDLER,  # path/get intentionally remain bare values
    "co schedule list": "co schedule run <name>",
    "co schedule check": "co schedule list",
    "co schedule run": "co schedule list",
    "co schedule pause": HANDLER,  # names the resume for this entry
    "co schedule resume": "co schedule list",
    "co outlook calendar *": HANDLER,
    "co gcalendar *": HANDLER,
    "co gdrive *": HANDLER,
    "co gmail *": HANDLER,
    # Every wiki command already ends by naming one next command, chosen from what
    # it found: `list` points at the first page, `search` at the first hit, a failed
    # `show` back at the category. A static line here would contradict that.
    "co wiki *": HANDLER,
    "co outlook inbox": HANDLER,
    "co outlook read": HANDLER,
    "co outlook reply": HANDLER,  # 1.8.4 already emits a contextual next step
    "co outlook send": HANDLER,  # 1.8.4 already emits a contextual next step
    "co outlook sent": HANDLER,  # 1.8.4 already emits a contextual next step
    "co outlook search": HANDLER,
    "co outlook download": HANDLER,  # 1.8.4 already emits a contextual next step
    "co outlook scheduled": HANDLER,
    "co outlook cancel": HANDLER,  # 1.8.4 already emits a contextual next step
    "co outlook contact add": HANDLER,  # 1.8.4 already emits a contextual next step
    "co outlook contact list": HANDLER,  # 1.8.4 already emits a contextual next step
    "co outlook contact search": HANDLER,  # 1.8.4 already emits a contextual next step
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
    # The inbox verbs beside it: the same table as feishu, lark and whatsapp.
    "co telegram listen": "co telegram receive --timeout 0",
    "co telegram receive": "co telegram reply <message-id>",
    "co telegram reply": "co telegram receive --timeout 0",
    "co telegram done": "co telegram receive --timeout 0",
    "co telegram edit": "co telegram log",
    "co telegram delete": "co telegram log",
    "co telegram react": "co telegram log",
    "co telegram check": HANDLER,  # every branch of _report_connection names its own
    "co telegram ls": "co telegram receive --timeout 0",
    "co telegram chats": HANDLER,
    "co telegram log": "co telegram ls",
    "co telegram consume": "co telegram ls",
    "co trust list": "Check one address:  co trust level <address>",
    "co trust level": HANDLER,  # the next step depends on the level it printed
    "co trust add": "See every list:  co trust list",
    "co trust remove": "See every list:  co trust list",
    "co trust block": "See every list:  co trust list",
    "co trust unblock": "See every list:  co trust list",
    "co trust admin add": "See every list:  co trust list",
    "co trust admin remove": "See every list:  co trust list",
    "co youtube *": HANDLER,
    "co tiktok *": HANDLER,
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
