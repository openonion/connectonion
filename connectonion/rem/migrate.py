"""The move from co wiki to co rem, for notebooks made before 1.9.0 (#1932).

1.8.8 and 1.8.9 kept the notebook in ~/.co/wiki and scheduled `co wiki sync`.
The first `co rem` moves the folder -- moves, so there is one notebook and not
two drifting apart -- and replaces a schedule that would otherwise run the old
command every night and fail. Removed in 1.10 with the `co wiki` tombstone.
"""

import os
from pathlib import Path

from .files import RemError

OLD_ENV = "CO_WIKI_PROGRAM"


def old_root() -> Path:
    return Path.home() / ".co" / "wiki"


def move_notebook(root: Path) -> str:
    """Move ~/.co/wiki to the default root once; the line to print, or ''.

    An explicit --root is used as given. With both folders present nothing is
    merged: the user decides which one is the notebook. os.rename within ~/.co
    is one step, so a move that fails leaves the old folder whole.
    """
    old = old_root()
    if not old.is_dir():
        return ""
    if root.exists():
        raise RemError(f"Both {old} (co wiki) and {root} (co rem) exist; they are never merged. "
                       f"Keep the one you want at {root} and move the other away")
    root.parent.mkdir(parents=True, exist_ok=True)
    os.rename(old, root)
    return f"Moved your notebook from {old} to {root} (co wiki is now co rem)."


def replace_schedule(root: Path, old: Path, scheduler=None) -> str:
    """Reinstall a schedule that still runs `co wiki` for this notebook; the line to print, or ''."""
    from .schedule import default_scheduler
    scheduler = scheduler or default_scheduler()
    if not hasattr(scheduler, "remove_old") or not scheduler.remove_old(old):
        return ""
    from .config import read_config
    scheduler.install(root, read_config(root))
    return "Your daily update now runs co rem sync."


def program() -> str:
    """How the user invokes co rem, for Next lines; CO_WIKI_PROGRAM still counts in 1.9.x."""
    if os.environ.get("CO_REM_PROGRAM"):
        return os.environ["CO_REM_PROGRAM"]
    if os.environ.get(OLD_ENV):
        return os.environ[OLD_ENV]
    return "co rem"


def old_program_notice() -> str:
    """One line when only the old variable is set, so a wrapper gets renamed before 1.10."""
    if os.environ.get(OLD_ENV) and not os.environ.get("CO_REM_PROGRAM"):
        return f"{OLD_ENV} is deprecated; set CO_REM_PROGRAM instead (read until 1.10)."
    return ""
