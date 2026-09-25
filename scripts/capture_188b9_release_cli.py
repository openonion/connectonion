"""1.8.8b9's capture: the top of `co --help` after the fixes (#1697, #1688).

    python scripts/capture_188b9_release_cli.py

A live run of this checkout's CLI, nothing replayed: the "Start here" block a
new user now meets first, before the guidance for building a skill. Only the
lines above the options box are shown; the picture says so.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

OUT = ROOT / "docs/releases/assets/v1.8.8b9"


def help_start_here() -> None:
    co = str(Path(sys.executable).parent / "co")   # the entry point, so Usage reads `co`
    result = subprocess.run([co, "--help"], cwd=ROOT,
                            env={**os.environ, "NO_COLOR": "1", "COLUMNS": "100", "PYTHONPATH": str(ROOT)},
                            capture_output=True, text=True, check=True)
    lines = result.stdout.splitlines()
    end = next(i for i, line in enumerate(lines) if "Options" in line and "─" in line)
    shown = "\n".join(line.rstrip() for line in lines[:end]).strip("\n")
    assert "Start here" in shown, shown
    shoot(page("", [("co --help | sed '/Options/q'   # the part above the options and commands", shown)]),
          OUT / "help-start-here.png")


if __name__ == "__main__":
    help_start_here()
