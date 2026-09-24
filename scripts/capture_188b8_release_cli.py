"""1.8.8b8's capture: `co wiki --help`, the agreed root page (#1656).

    python scripts/capture_188b8_release_cli.py

A help page holds no personal data, so this is the released command's own
output, unedited.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

OUT = ROOT / "docs/releases/assets/v1.8.8b8"


def root_help():
    shown = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "wiki", "--help"], cwd=ROOT,
                           capture_output=True, text=True, timeout=120,
                           env={**os.environ, "NO_COLOR": "1", "COLUMNS": "96", "PYTHONPATH": str(ROOT)})
    assert shown.returncode == 0, shown.stderr
    shoot(page("", [("co wiki --help", shown.stdout.rstrip())]), OUT / "co-wiki-help.png")


if __name__ == "__main__":
    root_help()
