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

    Falls back to ``start`` when there is no ``.co/`` above it — an agent hosted
    outside a project still works, its files just live where it was started.
    """
    start = Path(start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        if (directory / CO_DIR).is_dir():
            return directory
    return start


def project_co_dir(start: Optional[Union[str, Path]] = None) -> Path:
    """The project's ``.co/``. Does not create it."""
    return project_root(start) / CO_DIR
