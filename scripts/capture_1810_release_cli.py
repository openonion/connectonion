"""Capture 1.8.10's new commands from their own help text.

    python scripts/capture_1810_release_cli.py

Each block is `co <command> --help` from this checkout, run in a disposable
HOME with colour off. No account, key or network is used.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from capture_186a2_release_cli import page, shoot

OUT = ROOT / "docs/releases/assets/v1.8.10"
RUN_CO = "import sys; from connectonion.cli.main import cli; sys.argv[0] = 'co'; cli()"


def help_of(*args: str) -> str:
    with tempfile.TemporaryDirectory(prefix="co-1810-capture-") as home:
        env = {**os.environ, "HOME": home, "NO_COLOR": "1", "COLUMNS": "92",
               "PYTHONPATH": str(ROOT)}
        env.pop("FORCE_COLOR", None)
        result = subprocess.run([sys.executable, "-c", RUN_CO, *args, "--help"],
                                capture_output=True, text=True, env=env, cwd=home, check=True)
    return result.stdout.rstrip()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    shots = {
        "linear-help.png": ("co linear --help", help_of("linear")),
        "canny-help.png": ("co canny --help", help_of("canny")),
        "slack-help.png": ("co slack --help", help_of("slack")),
    }
    for name, block in shots.items():
        shoot(page("", [block]), OUT / name)
    print(f"wrote {len(shots)} captures into {OUT}")
