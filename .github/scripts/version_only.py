"""Whether a diff changes nothing but the release metadata.

A release PR bumps the version and adds release notes; the code it ships is
the code main already tested. Running the full matrix on it again (45 jobs,
queued behind the org's concurrent-job limit) was most of a release's wait.
So Tests on a release PR, and the release gate on the release commit, ask this
first.

"Only release metadata" means every changed file is release notes, or a
version file whose every changed line is a version assignment or a comment.
A dependency change in pyproject.toml or a new package in uv.lock is code, and
runs the full matrix.

    python .github/scripts/version_only.py BASE HEAD   # prints true or false
"""

from __future__ import annotations

import re
import subprocess
import sys

NOTES = re.compile(r"^(VERSIONING\.md|docs/releases\.md|docs/releases/[^/]+\.md)$")
VERSION_LINES = {
    "pyproject.toml": re.compile(r'^version = "[^"]+"$'),
    "connectonion/_version.py": re.compile(r'^__version__ = "[^"]+"$'),
    "connectonion/handoff/replies.py": re.compile(r'^(MIN_VERSION = "[^"]+"|#.*)$'),
    "uv.lock": re.compile(r'^version = "[^"]+"$'),
}


def changed_lines(diff: str) -> dict[str, list[str]]:
    """{path: [added or removed line, ...]} from `git diff --unified=0`."""
    lines: dict[str, list[str]] = {}
    path = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[1]
            lines[path] = []
        elif line.startswith(("+++", "---")):
            continue
        elif line.startswith(("+", "-")) and path is not None:
            lines[path].append(line[1:])
    return lines


def version_only(diff: str, uv_lock_package: str = "connectonion") -> bool:
    files = changed_lines(diff)
    if not files:
        return False
    for path, lines in files.items():
        if NOTES.match(path):
            continue
        pattern = VERSION_LINES.get(path)
        if pattern is None or not all(pattern.match(line.strip()) for line in lines if line.strip()):
            return False
    return "uv.lock" not in files or _uv_lock_bump_is_ours(diff, uv_lock_package)


def _uv_lock_bump_is_ours(diff: str, package: str) -> bool:
    """A uv.lock `version =` line is ours only inside our own package block."""
    sections = [part for part in diff.split("diff --git ") if part.startswith("a/uv.lock ")]
    hunks = [hunk for section in sections for hunk in section.split("\n@@")
             if re.search(r"^[+-]version = ", hunk, re.M)]
    return all(f'name = "{package}"' in hunk for hunk in hunks)


def main() -> int:
    base, head = sys.argv[1], sys.argv[2]
    # Three lines of context put `name = "connectonion"` in the uv.lock hunk.
    diff = subprocess.check_output(["git", "diff", "--unified=3", base, head], text=True)
    print("true" if version_only(diff) else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
