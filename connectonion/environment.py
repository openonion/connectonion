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


class EnvironmentError(ValueError):
    """A selected configuration file cannot be used (never includes its contents)."""


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


def read_env_file(path: Path, *, required: bool = False) -> dict[str, str]:
    """Parse without logging dotenv contents or interpolating other accounts."""
    if not path.exists() and not required:
        return {}
    try:
        with path.open(encoding="utf-8") as stream:
            bindings = list(parse_stream(stream))
    except (OSError, UnicodeError):
        raise EnvironmentError("Cannot read the selected env file. No configuration was changed. Run the following command to inspect --env-file before choosing a readable file:\nNext: co --help") from None
    if any(binding.error for binding in bindings):
        raise EnvironmentError("Invalid syntax in the selected env file. Next: co --help")
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
    """Switch files before command execution, preserving only explicit overrides."""
    global _selected
    selected = path.expanduser().resolve() if path is not None else None
    read_env_file(selected or global_config_dir() / "keys.env", required=selected is not None)
    for key, value in _loaded.items():
        if os.environ.get(key) == value:
            os.environ.pop(key, None)
    _loaded.clear()
    _selected = selected
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
