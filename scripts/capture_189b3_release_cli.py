"""1.8.9b3's capture: `co outlook calendar teams --help` says what it needs (#1719).

    python scripts/capture_189b3_release_cli.py

A live run of this checkout's `co` in a throwaway HOME, nothing replayed and no
network: the help page names the account a Teams meeting needs, so a person
on a personal Microsoft account learns it before the command refuses.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

OUT = ROOT / "docs/releases/assets/v1.8.9b3"


def main() -> None:
    co = str(Path(sys.executable).parent / "co")
    env = {**os.environ, "HOME": tempfile.mkdtemp(prefix="b3-capture-"), "NO_COLOR": "1",
           "COLUMNS": "96", "PYTHONPATH": str(ROOT)}
    result = subprocess.run([co, "outlook", "calendar", "teams", "--help"], env=env,
                            capture_output=True, text=True, check=True)
    lines = result.stdout.splitlines()
    # The page above its options box: purpose, what it changes, the account note.
    end = next(i for i, line in enumerate(lines) if "Options" in line and "─" in line)
    shown = "\n".join(line.rstrip() for line in lines[:end]).strip("\n")
    assert "work or school" in shown, shown
    shoot(page("", [("co outlook calendar teams --help | sed '/Options/q'", shown)]), OUT / "teams-help.png")


if __name__ == "__main__":
    main()
