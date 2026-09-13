"""The pass after the sources: what the open web can add, through the browser.

The Codex runner's thread is read-only and has no network, on purpose -- it
reads untrusted mail. Enrichment needs the opposite: a browser. So it runs
under co ai, whose skills already include co-browser, with the `wiki-enrich`
Skill handed the page. This module only launches that and reads back what it
did; the judgement of what to look up is the Skill's.
"""

import json
import shutil
import subprocess
from pathlib import Path

from .files import Notebook, WikiError


def enrich(root: Path, record: str, *, runner=None, timeout: int = 900) -> dict:
    notebook = Notebook(root)
    if not notebook.path(record).is_file():
        raise WikiError(f"{record} does not exist; run `co wiki investigate` first")
    before = notebook.read(record)
    # A verb with a date, not the substring: the stub's own line reads
    # "not investigated yet", which contains "investigated ".
    import re
    if not re.search(r"(?<!not )investigated \d{4}-\d{2}-\d{2}", before):
        raise WikiError(f"{record} has not been investigated yet; the web fills what the sources could not, "
                        f"so the sources go first")
    envelope = (runner or _run_co_ai)(root, record, timeout)
    if envelope.get("error") or envelope.get("outcome") not in (None, "natural"):
        raise WikiError(f"Enrichment did not complete ({envelope.get('outcome')}): {str(envelope.get('error'))[:300]}")
    after = notebook.read(record)
    if after != before and "enriched " not in after.rsplit("Investigation:", 1)[-1]:
        notebook.note_pass(record, "enriched", "web")
    return {"record": record, "changed": after != before, "usage": envelope.get("usage"),
            "report": (envelope.get("result") or "")[:1000]}


def _run_co_ai(root: Path, record: str, timeout: int) -> dict:
    executable = shutil.which("co")
    if not executable:
        raise WikiError("`co` is not on PATH; enrichment runs the browser through co ai")
    prompt = (f"/wiki-enrich The page is {root / record}. Read it, fill only the Unknowns the open web "
              f"can answer, write back to that same file, and append `enriched <date> (web)` to its "
              f"Investigation line.")
    completed = subprocess.run([executable, "ai", "--json", prompt], cwd=str(root), capture_output=True,
                               text=True, timeout=timeout)
    for line in reversed(completed.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {"outcome": "error", "error": (completed.stderr or completed.stdout)[-500:] or f"exit {completed.returncode}"}
