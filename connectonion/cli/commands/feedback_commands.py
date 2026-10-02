"""Direct feedback channels and a read-only collector for the agent mailbox."""

import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import typer

from ..typer_groups import _OneSuggestion

EMAIL = "aaron.xie@mail.openonion.ai"
SUBJECT = "[ConnectOnion feedback]"
ISSUES = "https://github.com/openonion/connectonion/issues/new"
DISCORD = "https://discord.gg/4xfD9k8AUF"
feedback_app = typer.Typer(
    cls=_OneSuggestion,
    no_args_is_help=False,
    help="Feedback channels and an agent-mail collector. Read-only on your mailbox; listen writes feedback copies locally. "
    "No message is submitted automatically.",
    epilog="Example: co feedback  |  co feedback report --command 'co gsheets read'  |  co feedback listen --once",
)


def print_feedback_footer() -> None:
    """One stderr line per CLI invocation; provider JSON on stdout stays intact."""
    print(f"Feedback: {ISSUES} | Discord: {DISCORD} | Email: {EMAIL} (subject: {SUBJECT})", file=sys.stderr)


def channels(command: str = "") -> dict:
    from ..._version import __version__

    body = (
        f"co version: {__version__}\nPython: {platform.python_version()}\nOS: {platform.system()}\nCommand: {command}\n\n"
        "Expected:\n\nActual / error (remove credentials before pasting):\n"
    )
    return {
        "issue": ISSUES + "?" + urlencode({"title": "CLI feedback", "body": body}),
        "discord": DISCORD,
        "email": EMAIL,
        "mailto": "mailto:" + EMAIL + "?" + urlencode({"subject": SUBJECT, "body": body}),
    }


@feedback_app.callback(invoke_without_command=True)
def feedback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        print(json.dumps(channels(), ensure_ascii=False))


@feedback_app.command("report", epilog="Example: co feedback report --command 'co gsheets read'")
def report(
    command: str = typer.Option("", help="Command name to include in a user-submitted report; do not include secrets"),
):
    """Read-only: print GitHub and email report links with version context; nothing is sent."""
    print(json.dumps(channels(command), ensure_ascii=False))


def feedback_folder() -> Path:
    from ...environment import global_config_dir

    return global_config_dir() / "feedback"


def collect(folder: Path) -> int:
    """Save matching mail before advancing the newest-seen marker; never mark mail read."""
    from ...useful_tools.get_emails import get_emails

    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = folder / "cursor.json"
    previous = json.loads(state.read_text()) if state.exists() else {}
    watermark = previous.get("newest")
    newest, count, offset = None, 0, 0
    while True:
        messages = get_emails(last=100, offset=offset, address=EMAIL)
        if not messages:
            break
        newest = newest or str(messages[0]["id"])
        for message in messages:
            identifier = str(message["id"])
            if identifier == watermark:
                return finish_collection(state, newest, count)
            if SUBJECT.casefold() not in (message.get("subject") or "").casefold():
                continue
            if (message.get("to") or "").casefold() != EMAIL.casefold():
                continue
            filename = hashlib.sha256(identifier.encode()).hexdigest() + ".json"
            target = folder / filename
            if not target.exists():
                temporary = target.with_suffix(".tmp")
                with temporary.open("w", encoding="utf-8") as receipt:
                    temporary.chmod(0o600)
                    json.dump(message, receipt, ensure_ascii=False)
                temporary.replace(target)
                count += 1
        if len(messages) < 100:
            break
        offset += len(messages)
    return finish_collection(state, newest, count)


def finish_collection(state: Path, newest: str | None, count: int) -> int:
    if newest:
        temporary = state.with_suffix(".tmp")
        temporary.write_text(json.dumps({"newest": newest}), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(state)
    return count


@feedback_app.command("listen", epilog="Example: co feedback listen --once  |  co feedback listen --interval 60")
def listen(
    once: bool = typer.Option(False, help="Collect once and exit instead of polling"),
    interval: int = typer.Option(60, min=30, help="Seconds between mailbox reads"),
):
    """Writes matching feedback emails to ~/.co/feedback; mailbox reads stay Read-only. No replies or issue creation."""
    from ...environment import load_environment

    load_environment()
    folder = feedback_folder()
    while True:
        count = collect(folder)
        print(json.dumps({"collected": count, "folder": str(folder), "address": EMAIL}), flush=True)
        if once:
            return
        time.sleep(interval)


@feedback_app.command("inbox", epilog="Example: co feedback inbox")
def inbox():
    """Read collected local feedback messages as JSON lines. Read-only."""
    folder = feedback_folder()
    if folder.exists():
        for path in sorted(folder.glob("*.json")):
            if path.name != "cursor.json":
                print(path.read_text(encoding="utf-8"))
