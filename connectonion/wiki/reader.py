"""Disposable HTML view of the notebook. Markdown stays the store; this is a snapshot.

A page opened from file:// cannot read the Markdown next to it (browsers block
fetch from file URLs), so the notebook is embedded into one self-contained HTML
file at render time. The template is a plain client of that embedded object; a
served site later would hand it the same object over HTTP instead.
"""

import hashlib
import json
import os
import tempfile
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from .files import CATEGORIES, Notebook
from .service import run_logs, status, subscriptions

TEMPLATE = Path(__file__).with_name("reader.html")
PLACEHOLDER = "/*__WIKI_DATA__*/null"


def _title(record: str, text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip() or record
    return Path(record).stem.replace("-", " ")


def snapshot(root: Path) -> dict:
    """Everything the page shows, read once; no model, no writes into the notebook."""
    notebook = Notebook(root)
    records = []
    for record in notebook.list():
        text = notebook.read(record)
        records.append({"path": record, "category": record.split("/")[0],
                        "title": _title(record, text), "text": text})
    return {"as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "root": str(root), "categories": list(CATEGORIES), "records": records,
            "status": status(root), "subscriptions": subscriptions(root),
            "logs": run_logs(root)[:20]}


def render(root: Path) -> str:
    data = json.dumps(snapshot(root), ensure_ascii=False)
    # Inside a script block only "</script" and the U+2028/9 terminators can break
    # out. Escaping "<" as \u003c keeps the JSON valid and makes note text inert.
    data = data.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise RuntimeError("reader.html has lost its data placeholder")
    return template.replace(PLACEHOLDER, data, 1)


def reader_path(root: Path) -> Path:
    """Outside the notebook, so nothing under root changes and no collector meets it."""
    digest = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"co-wiki-{digest}.html"


def write_reader(root: Path) -> Path:
    page = render(root)
    path = reader_path(root)
    # The name is predictable; refuse to write through a link someone planted there.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(page)
    os.chmod(path, 0o600)
    return path


def open_reader(root: Path, *, launch: bool = True) -> Path:
    path = write_reader(root)
    if launch:
        webbrowser.open(path.as_uri())
    return path
