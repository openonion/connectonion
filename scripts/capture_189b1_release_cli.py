"""1.8.9b1's capture: an upgraded notebook's owner page, rebuilt by the map (#1716).

    python scripts/capture_189b1_release_cli.py

The notebook is synthetic -- a real owner's page names real correspondents and
a release image is public. It starts the way an older map left real notebooks:
the owner's second address as a one-mail correspondent page. build_map, the
owner fill and `co wiki show` are the released code.
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

from connectonion.wiki import map as wiki_map
from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook

OUT = ROOT / "docs/releases/assets/v1.8.9b1"
OWNER = "sam@mail.rivera.example"


class Mailbox:
    def my_addresses(self):
        return {OWNER}

    def my_name(self):
        return ""


def upgraded_owner_page():
    root = Path(tempfile.mkdtemp(prefix="wiki-189b1-")) / "wiki"
    prepare(root)
    (root.parent / "skills").mkdir()
    notebook = Notebook(root)
    record = "people/sam-mail-rivera-example.md"
    notebook.stub_person(record, OWNER, [OWNER], email=OWNER)
    old = notebook.read(record).replace(
        "## History\n- Unknown — not investigated yet",
        "## History\n- Observed mail count: 1; first: 2026-09-04; last: 2026-09-04; mailboxes: outlook. [1]").replace(
        "## Uncertainties\n", "## Uncertainties\n- Correspondent classification unassessed; mapping does not "
        "establish a person or employer.\n").replace(
        "- (none yet)", "- [1] Enumeration metadata, observed 2026-09-20 — .state/map.json")
    notebook.write(record, old)
    wiki_map._mail_rows = lambda *a: ([
        {'name': 'Mei Lin', 'address': 'mei@harbourlabs.example', 'mails': 64, 'sent': 30, 'received': 34,
         'one_way': False, 'boxes': ['gmail']},
        {'name': 'Jordan Park', 'address': 'jordan@northwind.example', 'mails': 41, 'sent': 19, 'received': 22,
         'one_way': False, 'boxes': ['outlook']}], {OWNER})
    wiki_map.scan_projects = lambda *a: [{'origin': '', 'repo': '/work/tide-agent', 'path': '/work/tide-agent',
                                          'sessions': 212, 'first': '2026-07-01', 'last': '2026-09-23'}]
    wiki_map.build_map(root, {}, {'outlook': Mailbox()}, days=90, skill_directories=[root.parent / "skills"],
                       name="Sam Rivera")
    shown = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "wiki", "--root", str(root),
                            "show", record], cwd=ROOT, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "NO_COLOR": "1", "COLUMNS": "96", "PYTHONPATH": str(ROOT)})
    assert shown.returncode == 0, shown.stderr
    text = "\n".join(line for line in shown.stdout.splitlines()
                     if not line.startswith("Next:"))
    text = text.split("## Open threads")[0].rstrip()
    shoot(page("", [(f"co wiki show {record}", text)]), OUT / "upgraded-owner-page.png")


if __name__ == "__main__":
    upgraded_owner_page()
