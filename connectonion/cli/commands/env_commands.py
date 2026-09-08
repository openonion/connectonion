"""
Purpose: `co env` — show, read, set and remove settings in the selected env file, and explain a broken one
LLM-Note:
  Dependencies: imports from [re, pathlib, typer, rich, environment, env_file, command_tips] | imported by [cli/main.py via handle_env_*] | tested by [tests/unit/test_co_env.py]
  Data flow: handle_env_show() → selected_env_file() + read_env_file() → one row per setting with a masked value and its source (file / process override / ignored provider record) | handle_env_get(key) → process value, else file value, printed bare for $(...) | handle_env_set(key, value) → name/record checks → env_file.upsert_env() (lock, atomic replace, 0600) | handle_env_unset(key) → upsert_env(remove=...) — a provider record field removes the whole record
  State/Effects: reads and writes only the selected env file (global ~/.co/keys.env unless --env-file was given) | never rewrites a file that fails to parse | never prints a secret unless --reveal | never touches os.environ
  Integration: the one command that still runs when the selected file is broken — every other command exits 2 and names it | tips keep the --env-file selector through command_tips.print_tip
  Performance: one file read per command; no network
  Errors: exit 2 for a bad name, a protected key (AGENT_CONFIG_PATH, provider record fields), a missing explicitly selected file, or a file that does not parse | exit 1 when `get`/`unset` names a setting that is not there | every failure names the next command
"""

import re
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ...environment import (
    PROVIDER_PREFIXES,
    EnvironmentError,
    display_path,
    explicit_env_file,
    process_environment,
    provider_keys,
    read_env_file,
    selected_env_file,
    selection_error,
)
from .command_tips import print_tip

console = Console()

# What a dotenv parser accepts as a key. Anything else would be written as a
# line the next read refuses, and `co env` is the command that fixes those.
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# A value is masked when its name says it is a secret. Names are the only
# signal available: an API key and a model name are both opaque strings.
_SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSPHRASE", "PHRASE", "CREDENTIAL", "PRIVATE")

_PROVIDER_AUTH = {"GOOGLE": "co auth google", "MICROSOFT": "co auth microsoft"}
_PROVIDER_LABEL = {"GOOGLE": "Google", "MICROSOFT": "Microsoft"}


def _provider_of(key: str) -> str | None:
    """The provider whose account record this field belongs to, if any."""
    return next((prefix for prefix in PROVIDER_PREFIXES if key in provider_keys(prefix)), None)


def _is_secret(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in _SECRET_MARKERS)


def _mask(value: str) -> str:
    """A fixed-width mask; the prefix identifies which key it is, not what it is."""
    if len(value) <= 10:
        return "*" * 8
    return f"{value[:6]}…{'*' * 8}"


def _file_label() -> str:
    return "global" if explicit_env_file() is None else "selected with --env-file"


def _fail(message: str, code: int) -> None:
    print_tip(message)
    raise typer.Exit(code)


def _valid_name(key: str) -> None:
    if not _NAME.match(key):
        _fail(f"'{key}' is not a setting name: use letters, digits and underscores, "
              "starting with a letter or underscore. Next: co env set <KEY> <value>", 2)


def _writable_file() -> Path:
    """The selected file, once it is safe to rewrite.

    A missing file is fine to create. A file that does not parse is not
    rewritten around the bad line: dropping that line silently is exactly the
    kind of change nobody can explain afterwards.
    """
    error = selection_error()
    path = selected_env_file()
    if error is not None and path.exists():
        print(str(error))
        raise typer.Exit(2)
    return path


def handle_env_show(reveal: bool = False) -> None:
    """Every setting in the selected file, where it wins or loses, and what to run next."""
    path = selected_env_file()
    error = selection_error()
    print(f"Env file: {display_path(path)} ({_file_label()})")
    if error is not None:
        if error.line is not None:
            print(f"✗ Invalid syntax on line {error.line}. Fix that line in an editor "
                  "(it is not printed here: it may hold a secret), then check the file again.")
            _fail("Next: co env", 2)
        if not path.exists():
            _fail("✗ Not found. Create it by saving the first setting. Next: co env set <KEY> <value>", 2)
        _fail(str(error), 2)
    if not path.exists():
        print("✗ Not found. Global setup creates it together with the machine identity.")
        _fail("Next: co init", 0)

    values = read_env_file(path)
    inherited = process_environment()
    blocked = {prefix for prefix in PROVIDER_PREFIXES
               if any(key in inherited for key in provider_keys(prefix))}
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("SETTING")
    table.add_column("VALUE")
    table.add_column("SOURCE")
    for key, value in values.items():
        shown = value if reveal or not _is_secret(key) else _mask(value)
        provider = _provider_of(key)
        if key in inherited and inherited[key] != value:
            source = "process overrides file"
        elif provider in blocked:
            source = f"file, ignored: the process supplies the {_PROVIDER_LABEL[provider]} record"
        else:
            source = "file"
        table.add_row(key, shown, source)
    for prefix in sorted(blocked):
        for key in provider_keys(prefix):
            if key in inherited and key not in values:
                shown = inherited[key] if reveal or not _is_secret(key) else _mask(inherited[key])
                table.add_row(key, shown, "process")
    if values or blocked:
        console.print(table)
    else:
        print("(no settings yet)")
    if not reveal and any(_is_secret(key) for key in values):
        print("Secrets are masked; add --reveal to see them. Keep --reveal out of shared logs.")
    print_tip("Next: co env set <KEY> <value>")


def handle_env_path() -> None:
    """The selected file's path and nothing else, for $(co env path)."""
    print(selected_env_file())


def handle_env_get(key: str) -> None:
    """The value a command would see: the process wins, then the file. Bare, for $(...)."""
    _valid_name(key)
    error = selection_error()
    if error is not None:
        print(str(error))
        raise typer.Exit(2)
    inherited = process_environment()
    if key in inherited:
        print(inherited[key])
        return
    path = selected_env_file()
    values = read_env_file(path)
    if key in values:
        print(values[key])
        return
    _fail(f"{key} is not set in the process environment or {display_path(path)}. "
          f"Next: co env set {key} <value>", 1)


def handle_env_set(key: str, value: str) -> None:
    """Save one setting to the selected file, preserving everything else in it."""
    _valid_name(key)
    if key == "AGENT_CONFIG_PATH":
        _fail("AGENT_CONFIG_PATH chooses which global directory is read, so a file inside it "
              "cannot set it. Export it in your shell instead:\n"
              "  export AGENT_CONFIG_PATH=/path/to/.co\nNext: co env", 2)
    provider = _provider_of(key)
    if provider is not None:
        auth = _PROVIDER_AUTH[provider]
        _fail(f"{provider}_* account fields are written only by {auth}, as one record, so a single "
              f"field can never describe a different account than the rest. Next: {auth}", 2)
    path = _writable_file()
    from ...env_file import upsert_env
    try:
        upsert_env(path, {key: value})
    except EnvironmentError as error:
        print(str(error))
        raise typer.Exit(2)
    print(f"✓ {key} saved to {display_path(path)}")
    inherited = process_environment()
    if key in inherited and inherited[key] != value:
        print(f"! Your shell exports {key} with a different value, and process values win. "
              f"Commands in this shell keep the shell's value until you run: unset {key}")
    print_tip(f"Next: co env get {key}")


def handle_env_unset(key: str) -> None:
    """Remove one setting; a provider account field removes its whole record."""
    _valid_name(key)
    path = _writable_file()
    if not path.exists():
        _fail(f"{display_path(path)} does not exist, so there is nothing to remove. Next: co env", 1)
    values = read_env_file(path)
    from ...env_file import upsert_env
    provider = _provider_of(key)
    if provider is not None:
        label, auth = _PROVIDER_LABEL[provider], _PROVIDER_AUTH[provider]
        present = [name for name in provider_keys(provider) if name in values]
        if not present:
            _fail(f"No {label} account record in {display_path(path)}. Next: co env", 1)
        upsert_env(path, {}, remove=set(provider_keys(provider)))
        console.print(f"✓ Removed the {label} account record ({len(present)} fields) from "
                      f"{display_path(path)}. Records are all-or-nothing: one field never outlives "
                      "the rest to be mixed with another account.", markup=False)
        print_tip(f"Next: {auth}")
        return
    if key not in values:
        _fail(f"{key} is not in {display_path(path)}. Next: co env", 1)
    upsert_env(path, {}, remove={key})
    print(f"✓ {key} removed from {display_path(path)}")
    # "Next: co env" alone measured as `cat ~/.co/keys.env` in the tip test;
    # the tip must say why the command beats cat.
    print_tip("Next: co env (lists what the file holds now, secrets masked)")
