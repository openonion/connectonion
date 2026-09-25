"""1.8.9b2's capture: one command's help under the #1643 contract (#1721).

    python scripts/capture_189b2_release_cli.py

A help page holds no personal data, so this is the released command's own
output, unedited.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

OUT = ROOT / "docs/releases/assets/v1.8.9b2"


def trust_add_help():
    shown = subprocess.run([str(Path(sys.executable).with_name("co")), "trust", "add", "--help"],
                           cwd=ROOT, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "NO_COLOR": "1", "COLUMNS": "96", "PYTHONPATH": str(ROOT),
                                "HOME": tempfile.mkdtemp()})
    assert shown.returncode == 0, shown.stderr
    shoot(page("", [("co trust add --help", shown.stdout.rstrip())]), OUT / "co-trust-add-help.png")


if __name__ == "__main__":
    trust_add_help()
