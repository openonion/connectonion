"""One selected dotenv file, with provenance separate from inherited settings.

The default is $AGENT_CONFIG_PATH/keys.env (normally ~/.co/keys.env). Only the
CLI's explicit --env-file option selects another file; cwd never selects one.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from dotenv.main import resolve_variables
from dotenv.parser import parse_stream

PROVIDER_FIELDS = ("ACCESS_TOKEN", "REFRESH_TOKEN", "TOKEN_EXPIRES_AT", "SCOPES", "EMAIL")
PROVIDER_PREFIXES = ("GOOGLE", "MICROSOFT")
_selected: Path | None = None
_loaded: dict[str, str] = {}
# A selection that failed at CLI startup. Every other command exits on it;
# `co env` runs anyway, because it is the command that explains the failure.
_selection_error: "EnvironmentError | None" = None


class EnvironmentError(ValueError):
    """A selected configuration file cannot be used (never includes its contents).

    `path` and `line` are carried separately so `co env` can say which line to
    fix without the message ever quoting what is on it — the broken line of a
    credentials file is as likely as any other to hold a secret.
    """

    def __init__(self, message: str, *, path: Path | None = None, line: int | None = None):
        super().__init__(message)
        self.path = path
        self.line = line


def selection_error() -> "EnvironmentError | None":
    return _selection_error


def display_path(path: Path) -> str:
    """The path as people write it: ~ for the home directory, otherwise absolute."""
    resolved = Path(path).expanduser().resolve()
    try:
        # Both sides resolved: on macOS a temporary home is /var/... while the
        # file resolves to /private/var/..., and the two never match otherwise.
        return "~/" + resolved.relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return str(resolved)


def global_config_dir() -> Path:
    """Resolve the global directory from the process, never from a dotenv file."""
    return Path(os.environ.get("AGENT_CONFIG_PATH") or Path.home() / ".co").expanduser().resolve()


def selected_env_file() -> Path:
    """Return the sole env-file read/write destination for this invocation."""
    return _selected if _selected is not None else global_config_dir() / "keys.env"


def explicit_env_file() -> Path | None:
    return _selected


def selected_command(command: str) -> str:
    """Keep the explicitly chosen account in the next command's copyable tip."""
    import shlex
    if _selected is not None and command.startswith("co ") and not command.startswith("co --env-file "):
        return f"co --env-file {shlex.quote(str(_selected))} {command[3:]}"
    return command


def parse_env_file(path: Path) -> list:
    """Every binding in the file, or an EnvironmentError that names the first bad line.

    The error's tip is `co env`: the one command that still runs on a broken
    file, and the one that says which line to fix. It used to be `co --help`,
    which lists commands and repairs nothing.
    """
    if not path.exists():
        shown = display_path(path)
        raise EnvironmentError(f"Selected env file does not exist: {shown}. "
                               f"Next: {selected_command('co env set <KEY> <value>')} "
                               "(creates it owner-only)", path=path)
    try:
        with path.open(encoding="utf-8") as stream:
            bindings = list(parse_stream(stream))
    except (OSError, UnicodeError):
        raise EnvironmentError(f"Cannot read {display_path(path)}. No configuration was changed. "
                               f"Next: {selected_command('co env')}", path=path) from None
    for binding in bindings:
        if binding.error:
            # Measured with the text-only tip test: "invalid syntax on line 2.
            # Next: co env" made the model reply `cat -n ~/.co/keys.env`. The
            # tip has to say what `co env` does that cat does not.
            raise EnvironmentError(f"{display_path(path)}: invalid syntax on line "
                                   f"{binding.original.line}. Do not cat this file into a log; "
                                   f"it holds secrets. Next: {selected_command('co env')} "
                                   "(explains the line without printing it)",
                                   path=path, line=binding.original.line)
    return bindings


def read_env_file(path: Path, *, required: bool = False) -> dict[str, str]:
    """Parse without logging dotenv contents or interpolating other accounts."""
    if not path.exists() and not required:
        return {}
    bindings = parse_env_file(path)
    return {item.key: item.value for item in bindings if item.key and item.value is not None
            and item.key != "AGENT_CONFIG_PATH"}


def process_environment() -> dict[str, str]:
    """Exclude values inserted by us; later application overrides remain explicit."""
    return {key: value for key, value in os.environ.items() if _loaded.get(key) != value}


def provider_keys(provider: str) -> tuple[str, ...]:
    return tuple(f"{provider.upper()}_{field}" for field in PROVIDER_FIELDS)


def publish_values(values: dict[str, str], *, managed: bool = True) -> None:
    """Publish a saved record without making it look like inherited credentials."""
    os.environ.update(values)
    if managed:
        _loaded.update(values)


def publish_authorization(provider: str, values: dict[str, str]) -> None:
    """Explicit consent replaces the whole in-process account as well as its file."""
    for key in provider_keys(provider):
        os.environ.pop(key, None)
        _loaded.pop(key, None)
    publish_values(values)


def load_environment() -> None:
    """Fill ordinary settings and whole provider records from the selected file."""
    path = selected_env_file()
    values = read_env_file(path, required=_selected is not None)
    inherited = process_environment()
    blocked = {key for provider in PROVIDER_PREFIXES
               if any(key in inherited for key in provider_keys(provider))
               for key in provider_keys(provider)}
    # Ordinary application variables retain dotenv interpolation. Provider fields
    # stay literal so ${GOOGLE_*} cannot import fields from a different account.
    resolved = resolve_variables(values.items(), override=False)
    oauth_keys = {key for provider in PROVIDER_PREFIXES for key in provider_keys(provider)}
    for key, value in values.items():
        if key not in os.environ and key not in blocked:
            publish_values({key: value if key in oauth_keys else resolved[key]})
    if path.is_file() and (sys.stderr.isatty() or os.getenv("CO_DEBUG_ENV") == "1"):
        print(f"[env] {path}", file=sys.stderr)


def select_env_file(path: Path | None) -> None:
    """Switch files before command execution, preserving only explicit overrides.

    The selection is recorded before the file is read, so that when the read
    fails, `co env` and every tip still name the file the user asked for.
    """
    global _selected, _selection_error
    _selected = path.expanduser().resolve() if path is not None else None
    _selection_error = None
    try:
        read_env_file(selected_env_file(), required=_selected is not None)
    except EnvironmentError as error:
        _selection_error = error
        raise
    for key, value in _loaded.items():
        if os.environ.get(key) == value:
            os.environ.pop(key, None)
    _loaded.clear()
    load_environment()


def deployment_environment() -> dict[str, str]:
    """Export the selected app configuration without copying global personal accounts.

    Explicit --env-file is also the opt-in for deploying that file's accounts.
    Never export the entire OS environment (it can contain unrelated secrets).
    """
    values = read_env_file(selected_env_file(), required=_selected is not None)
    if _selected is None:
        from .cli.commands.env_inheritance import is_personal_account_credential, is_operator_identity
        values = {key: value for key, value in values.items()
                  if not is_personal_account_credential(key) and not is_operator_identity(key)}
    return {key: os.environ.get(key, value) for key, value in values.items()}
