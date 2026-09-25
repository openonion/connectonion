"""1.8.9b4's capture: a managed web search against production (#1724).

    python scripts/capture_189b4_release_cli.py

Runs the real `co search --engine co` under the caller's own login, so the
answer and sources are what production returned; it spends one search of
credits. The output names no account, balance or key, so it is unedited.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

OUT = ROOT / "docs/releases/assets/v1.8.9b4"
QUERY = "latest stable rust version"


def managed_search():
    shown = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "search", QUERY, "--engine", "co", "-n", "3"],
                           cwd=ROOT, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "NO_COLOR": "1", "COLUMNS": "96", "PYTHONPATH": str(ROOT)})
    assert shown.returncode == 0, shown.stderr
    output = (shown.stdout.rstrip() + "\n" + shown.stderr.rstrip()).strip()
    shoot(page("", [(f'co search "{QUERY}" --engine co -n 3', output)]), OUT / "co-search-managed.png")


if __name__ == "__main__":
    managed_search()
