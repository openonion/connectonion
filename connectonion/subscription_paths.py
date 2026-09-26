"""Active subscribed skill directories, keyed by their pinned local alias."""

from __future__ import annotations

import re
from pathlib import Path

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def active_subscription_skills(home: Path | None = None) -> list[tuple[str, Path]]:
    home = home or Path.home()
    co_home = home / ".co"
    list_path = co_home / "subscriptions.txt"
    if not list_path.is_file():
        return []
    bundles = []
    seen = set()
    for line in list_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or not _ADDRESS.fullmatch(parts[0]):
            continue
        alias = parts[1]
        if not _NAME.fullmatch(alias) or alias in seen:
            continue
        seen.add(alias)
        bundles.append((alias, co_home / "subs" / alias / "skills"))
    return bundles
