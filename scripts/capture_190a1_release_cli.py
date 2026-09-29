"""1.9.0a1's capture: `co wiki list people` in the order investigate works (#1670).

    python scripts/capture_190a1_release_cli.py

A throwaway notebook with invented people and the map's mail counts, in a
disposable HOME; the command is this checkout's own `co`, run unedited.
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

OUT = ROOT / "docs/releases/assets/v1.9.0a1"


def main() -> None:
    from connectonion.wiki.config import prepare
    from connectonion.wiki.files import Notebook, state_path, write_json

    home = Path(tempfile.mkdtemp(prefix="190a1-capture-"))
    root = home / "notebook"
    prepare(root)
    notebook = Notebook(root)
    people = [("people/0x3c3ae74550.md", 2), ("people/alex-rivera.md", 41), ("people/mia-chen.md", 186),
              ("people/sam-okafor.md", 97)]
    for record, _ in people:
        notebook.write(record, "# " + record.split("/")[1][:-3] + "\n")
    write_json(state_path(root, "map.json"), {"people": [{"record": r, "mails": n} for r, n in people]})
    result = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "wiki", "--root", str(root),
                             "list", "people"], cwd=ROOT, capture_output=True, text=True, check=True,
                            env={**os.environ, "HOME": str(home), "NO_COLOR": "1", "COLUMNS": "96",
                                 "PYTHONPATH": str(ROOT)})
    shown = (result.stdout.rstrip() + "\n" + result.stderr.rstrip()).strip()
    for path in (str(root.resolve()), str(root)):   # macOS temp dirs resolve under /private
        shown = shown.replace(path, "<notebook>")
    assert shown.index("mia-chen") < shown.index("sam-okafor") < shown.index("0x3c3ae74550"), shown
    shoot(page("", [("co wiki --root <notebook> list people", shown)]), OUT / "wiki-list-people.png")


if __name__ == "__main__":
    main()
