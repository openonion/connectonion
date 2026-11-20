"""Terminal scope selection; metadata only until normal REM consent."""
import sys
import typer
from .files import RemError


def pick(rows, label, *, key="id", title="name", multiple=False):
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RemError(f"Malformed {label} metadata; retry listing")
    if not rows:
        raise RemError(f"No accessible {label}; no source was connected")
    ids = [row.get(key) for row in rows]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise RemError(f"Malformed or ambiguous {label} metadata; retry the source listing")
    typer.echo(f"Choose {label} (q cancels):")
    for number, row in enumerate(rows, 1):
        text = f"{row.get(title) or '(untitled)'} [{row[key]}]"
        text = "".join(c if c.isprintable() else " " for c in text)[:180]
        typer.echo(f"  {number}. {text}")
    while True:
        answer = typer.prompt("Numbers separated by commas" if multiple else "Number").strip()
        if answer.lower() == "q":
            raise typer.Abort()
        try:
            indices = list(dict.fromkeys(int(v.strip()) - 1 for v in answer.split(",")))
            if not indices or (not multiple and len(indices) != 1) or any(i < 0 or i >= len(rows) for i in indices):
                raise ValueError()
        except ValueError:
            typer.echo("Choose only numbers shown above, or q to cancel.")
            continue
        chosen = [rows[i][key] for i in indices]
        return chosen if multiple else chosen[0]


def saved_credentials(kind):
    from .remote_sources import adapter, require_saved
    adapter(kind)
    try:
        require_saved("MICROSOFT_REFRESH_TOKEN")
    except RemError as error:
        if "missing" not in str(error):
            raise
        if not typer.confirm("Connect Microsoft using the existing browser authorization?", default=False):
            raise typer.Abort()
        from ..cli.commands.auth_commands import handle_microsoft_auth
        handle_microsoft_auth()
        require_saved("MICROSOFT_REFRESH_TOKEN")


def interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


def select_scope(kind):
    from .remote_sources import adapter, credentials, recovery
    from .. import environment
    if not interactive():
        raise RemError("Interactive connection needs a local terminal. Scripts: sources connect NAME --config FILE")
    provider = adapter(kind)
    typer.echo("List account/scope metadata only. No content or model calls before REM approval.")
    try:
        saved_credentials(kind)
        with credentials({"kind": kind, "remote": {
                "credential_file": str(environment.selected_env_file()),
                "credential_home": str(environment.global_config_dir())}}):
            return provider.choose_scope()
    except RemError:
        raise
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
        raise RemError(f"{kind.title()} scope listing failed ({type(error).__name__}). Retry {recovery(kind)}") from None
