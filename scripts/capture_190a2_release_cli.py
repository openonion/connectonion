"""1.9.0a2's capture: a co wiki notebook meets co rem for the first time (#1932).

    python scripts/capture_190a2_release_cli.py

A throwaway notebook at ~/.co/wiki in a disposable HOME, as 1.8.9 left it;
the commands are this checkout's own `co`, run unedited.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page          # a2's renderer

OUT = ROOT / "docs/releases/assets/v1.9.0a2"


def run(home: Path, *args) -> str:
    result = subprocess.run([sys.executable, "-m", "connectonion.cli.main", *args], cwd=ROOT,
                            capture_output=True, text=True,
                            env={**os.environ, "HOME": str(home), "NO_COLOR": "1", "COLUMNS": "96",
                                 "PYTHONPATH": str(ROOT)})
    shown = (result.stderr.rstrip() + "\n" + result.stdout.rstrip()).strip()
    for path in (str(home.resolve()), str(home)):   # macOS temp dirs resolve under /private
        shown = shown.replace(path, "~")
    return shown


def shoot(html: str, destination: Path) -> None:
    """The a2 renderer's screenshot, on whichever Chromium Playwright has."""
    from playwright.sync_api import sync_playwright

    destination.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as play:
        # CO_CAPTURE_CHROMIUM names a Chromium when Playwright's own build is not installed.
        browser = play.chromium.launch(executable_path=os.environ.get("CO_CAPTURE_CHROMIUM") or None)
        view = browser.new_page(viewport={"width": 1040, "height": 100}, device_scale_factor=2)
        view.set_content(f"<body style='margin:0;background:#1d1f21'>{html}</body>")
        view.screenshot(path=str(destination), full_page=True)
        browser.close()


def main() -> None:
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook

    home = Path(tempfile.mkdtemp(prefix="190a2-capture-"))
    old = home / ".co" / "wiki"
    prepare(old)
    for name in ("mia-chen", "sam-okafor"):
        Notebook(old).write(f"people/{name}.md", f"# {name}\n")
    tombstone = run(home, "wiki", "status")
    moved = run(home, "rem", "list", "people")
    assert "co wiki is now co rem." in tombstone and "Next: co rem status" in tombstone, tombstone
    assert "Moved your notebook from ~/.co/wiki to ~/.co/rem" in moved, moved
    assert not old.exists() and (home / ".co" / "rem" / "people" / "mia-chen.md").is_file()
    shoot(page("", [("co wiki status", tombstone), ("co rem list people", moved)]),
          OUT / "rem-moves-the-wiki-notebook.png")


if __name__ == "__main__":
    main()
