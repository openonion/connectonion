"""Capture 1.8.9b13's Chrome import and local wiki snapshot from real CLI output.

    python scripts/capture_189b13_release_cli.py

Both run in a disposable HOME. The Chrome profile is the test fixture's fake
one (known password, example cookies), and a dry run reads no Keychain and
starts no browser; the notebook holds two synthetic pages. No private profile,
cookie value, or network request enters these images.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from capture_186a2_release_cli import page, shoot
from tests.fixtures.chrome_profile import cookie, make_profile

OUT = ROOT / "docs/releases/assets/v1.8.9b13"
YEAR = 365 * 24 * 3600


def cli(home: Path, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "connectonion.cli.main", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": str(ROOT), "NO_COLOR": "1",
             "COLUMNS": "100", "HOME": str(home)},
    )
    return (result.stdout + result.stderr).rstrip().replace(str(home), "~")


def example_chrome(home: Path) -> None:
    later = time.time() + YEAR
    chrome = home / "Library" / "Application Support" / "Google" / "Chrome"
    make_profile(chrome, "Default", [
        cookie(".github.com", "user_session", "example", expires=later),
        cookie(".github.com", "_octo", "example", expires=later, httponly=False),
        cookie(".linkedin.com", "li_at", "example", expires=later),
        cookie(".linkedin.com", "bcookie", "example", expires=later),
        cookie(".linkedin.com", "lidc", "example", expires=later),
    ], shown_name="Personal")


def snapshot_in_chrome(home: Path, destination: Path) -> str:
    """Open the file:// page `co wiki open` names, the way a reader would, and shoot it."""
    from playwright.sync_api import sync_playwright
    from connectonion.wiki.config import prepare
    from connectonion.wiki.files import Notebook

    root = home / "wiki"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice\n\nWorks on Project Aurora.\n")
    Notebook(root).write("projects/aurora.md", "# Aurora\n\nA synthetic project.\n")
    output = cli(home, "wiki", "--root", str(root), "--json", "open", "--no-launch")
    import json
    link = json.loads(output)["data"]["link"]
    with sync_playwright() as play:
        browser = play.chromium.launch(channel="chrome")
        view = browser.new_page(viewport={"width": 1200, "height": 720}, device_scale_factor=2)
        view.goto(link)
        view.wait_for_load_state("networkidle")
        view.screenshot(path=str(destination))
        browser.close()
    return link


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="co-189b13-capture-") as temporary:
        home = Path(temporary)
        example_chrome(home)
        shoot(page("", [("co browser import --dry-run",
                         cli(home, "browser", "import", "--dry-run"))]),
              OUT / "browser-import-dry-run.png")
        print(snapshot_in_chrome(home, OUT / "wiki-open-snapshot.png"))
    print(f"wrote 2 captures into {OUT}")
