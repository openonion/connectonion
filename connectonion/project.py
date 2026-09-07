"""Where the project is.

The directory that owns ``.co/`` is the project, not wherever the process was
started. An agent run from a subdirectory is the same agent, with the same
skills, the same trust lists and the same ``host.yaml``.

This walk was written five times before it had a home — in the dashboard, the
logger, the host config, the trust lists — and each copy was added by a separate
bug where something resolved against the bare cwd instead. Two of those bugs
failed open: a project configured ``trust: strict`` ran as ``careful``, and an
address on the blocklist read back as a stranger.

Nothing here creates a directory. Creating ``.co/`` wherever you happen to be
standing is the other half of the same bug: the walk stops at the *nearest*
``.co/``, so a stray one shadows the project's own for everything that comes
after it.
"""

from pathlib import Path
from typing import Optional, Union

CO_DIR = ".co"


def project_root(start: Optional[Union[str, Path]] = None) -> Path:
    """The directory that owns ``.co/``, found by walking up from ``start``.

    The walk stops where the project must stop: at the repository, and at
    ``$HOME``. A ``.co/`` reached only by climbing out of those belongs to
    something else — most often ``~/.co``, which is the *global* config
    directory and sits above every directory the user owns. Without the bound,
    ``co`` run from anywhere under ``$HOME`` outside a project resolved to
    ``$HOME`` and read the machine's own config as that project's, trust list
    included: the silent, fail-open case this module's history is made of.

    The global ``~/.co`` is still read where it is genuinely global — see
    ``project_identity()``, which falls back to it by name. What it no longer
    does is stand in for a project nobody created.

    Falls back to ``start`` when there is no ``.co/`` above it — an agent hosted
    outside a project still works, its files just live where it was started.
    """
    start = Path(start or Path.cwd()).resolve()
    home = Path.home().resolve()

    for directory in (start, *start.parents):
        # $HOME/.co is the machine's config, not a project's.
        if (directory / CO_DIR).is_dir() and directory != home:
            return directory
        if directory == home or _is_repository(directory):
            break
    return start


def _is_repository(directory: Path) -> bool:
    """A checkout boundary. ``.git`` is a directory in a clone, a file in a worktree."""
    return (directory / ".git").exists()


def project_co_dir(start: Optional[Union[str, Path]] = None) -> Path:
    """The project's ``.co/``. Does not create it."""
    return project_root(start) / CO_DIR


def selected_identity_dir() -> Path:
    """Global identity by default; an explicitly selected env can use its adjacent .co."""
    from . import address
    from .environment import explicit_env_file, global_config_dir
    selected = explicit_env_file()
    if selected is not None:
        local = selected.parent / CO_DIR
        if address.load(local):
            return local
    return global_config_dir()


def project_identity(co_dir=None):
    """Load the selected identity; a supplied directory is an explicit SDK choice."""
    from . import address
    from .environment import global_config_dir
    directory = Path(co_dir) if co_dir is not None else selected_identity_dir()
    return address.load(directory) or address.load(global_config_dir())
