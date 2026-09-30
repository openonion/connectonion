"""1.9.0a5's capture: co rem as a terminal shows it (#1996, #1997).

    CO_CAPTURE_CHROMIUM=<chromium> python scripts/capture_190a5_release_cli.py

A throwaway notebook in a disposable HOME; the commands are this checkout's own
`co`, run unedited as a terminal would run them (FORCE_COLOR, 96 columns), so
the picture shows the colour the release adds.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page          # a2's renderer, which keeps ANSI colour
from capture_190a2_release_cli import shoot         # on whichever Chromium Playwright has

OUT = ROOT / "docs/releases/assets/v1.9.0a5"


def run(home: Path, *args) -> str:
    env = {key: value for key, value in os.environ.items() if key != "NO_COLOR"}
    result = subprocess.run([sys.executable, "-m", "connectonion.cli.main", *args], cwd=ROOT,
                            capture_output=True, text=True,
                            env={**env, "HOME": str(home), "FORCE_COLOR": "1", "TERM": "xterm-256color",
                                 "COLUMNS": "96", "PYTHONPATH": str(ROOT)})
    shown = (result.stderr.rstrip() + "\n" + result.stdout.rstrip()).strip()
    for path in (str(home.resolve()), str(home)):   # macOS temp dirs resolve under /private
        shown = shown.replace(path, "~")
    return shown


def main() -> None:
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook

    home = Path(tempfile.mkdtemp(prefix="190a5-capture-"))
    root = home / ".co" / "rem"
    prepare(root)
    for record in ("people/mia-chen.md", "people/sam-okafor.md", "projects/connectonion.md"):
        Notebook(root).write(record, f"# {Path(record).stem}\n")
    status = run(home, "rem", "status")
    helped = run(home, "rem", "--help")
    assert "\x1b[" in status and "\x1b[" in helped, "the capture must show the terminal's colour"
    assert "Next:" in status, status
    shoot(page("", [("co rem status", status)]), OUT / "rem-status-dashboard.png")
    shoot(page("", [("co rem --help", helped)]), OUT / "rem-help-in-colour.png")


if __name__ == "__main__":
    main()
