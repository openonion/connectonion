"""1.8.9b8's capture: `co audit co` and `co audit yt-dlp`, as released (#1748).

    python scripts/capture_189b8_release_cli.py

Help pages hold no personal data, so this is the command's own output, unedited.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

OUT = ROOT / "docs/releases/assets/v1.8.9b8"


def audit(*target):
    shown = subprocess.run([str(Path(sys.executable).with_name("co")), "audit", *target],
                           capture_output=True, text=True, timeout=900,
                           env={**os.environ, "NO_COLOR": "1", "COLUMNS": "96", "HOME": tempfile.mkdtemp()})
    return (shown.stdout + shown.stderr).rstrip()


if __name__ == "__main__":
    shoot(page("", [("co audit co", audit("co")), ("co audit yt-dlp", audit("yt-dlp"))]), OUT / "co-audit.png")
