"""1.8.8b6's capture: the owner's own page, filled by the map (#1655).

    python scripts/capture_188b6_release_cli.py

The map runs in-process on synthetic mail and session metadata -- a real
owner's page names real correspondents, and a release image is public. Only
the mail and project enumeration is replaced; build_map, the owner fill and
`co wiki show` are the released code. Real-mailbox evidence is in PR #1658.
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

OUT = ROOT / "docs/releases/assets/v1.8.8b6"

PEOPLE = [
    {'name': 'Mei Lin', 'address': 'mei@harbourlabs.example', 'mails': 64, 'sent': 30, 'received': 34,
     'one_way': False, 'first': '2026-07-02', 'last': '2026-09-22', 'boxes': ['gmail']},
    {'name': 'Mei Lin', 'address': 'mei.lin@mail.example', 'mails': 9, 'sent': 4, 'received': 5,
     'one_way': False, 'first': '2026-08-10', 'last': '2026-09-01', 'boxes': ['outlook']},
    {'name': 'Jordan Park', 'address': 'jordan@northwind.example', 'mails': 41, 'sent': 19, 'received': 22,
     'one_way': False, 'first': '2026-06-30', 'last': '2026-09-20', 'boxes': ['outlook']},
    {'name': 'Priya Nair', 'address': 'priya@uni.example', 'mails': 17, 'sent': 8, 'received': 9,
     'one_way': False, 'first': '2026-07-15', 'last': '2026-09-18', 'boxes': ['outlook']},
    {'name': '', 'address': 'samrivera.home@mail.example', 'mails': 52, 'sent': 52, 'received': 0,
     'one_way': True, 'first': '2026-06-28', 'last': '2026-09-23', 'boxes': ['gmail']},
    {'name': 'Sam', 'address': 'notifications@github.com', 'mails': 80, 'sent': 1, 'received': 79,
     'one_way': False, 'first': '2026-06-26', 'last': '2026-09-23', 'boxes': ['gmail']},
]
PROJECTS = [
    {'origin': '', 'repo': '/work/tide-agent', 'path': '/work/tide-agent', 'sessions': 212,
     'first': '2026-07-01', 'last': '2026-09-23'},
    {'origin': '', 'repo': '/work/site', 'path': '/work/site', 'sessions': 37,
     'first': '2026-08-02', 'last': '2026-09-19'},
]


class Mailbox:
    def my_addresses(self):
        return {'sam@rivera.example'}

    def my_name(self):
        return 'Sam Rivera'


def owner_page():
    root = Path(tempfile.mkdtemp(prefix="wiki-b6-")) / "wiki"
    prepare(root)
    skills = root.parent / "skills"
    skills.mkdir()
    wiki_map._mail_rows = lambda *a: (PEOPLE, {'sam@rivera.example'})
    wiki_map.scan_projects = lambda *a: PROJECTS
    record = wiki_map.build_map(root, {}, {'gmail': Mailbox()}, days=90,
                                skill_directories=[skills])['owner']['record']
    shown = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "wiki", "--root", str(root),
                            "show", record], cwd=ROOT, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "NO_COLOR": "1", "COLUMNS": "96", "PYTHONPATH": str(ROOT)})
    assert shown.returncode == 0, shown.stderr
    text = "\n".join(line for line in shown.stdout.splitlines() if not line.startswith("Next:"))
    shoot(page("", [(f"co wiki show {record}", text)]), OUT / "owner-page-filled-by-the-map.png")


if __name__ == "__main__":
    owner_page()
