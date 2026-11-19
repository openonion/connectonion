"""The page before its last investigation, and a whole-page rewrite waiting for the owner (#3105).

An append keeps every line, but the owner still asked for an Undo on the
reader's Investigate button, and a rewrite is the one step that may lose
lines, so it never replaces a page by itself. Both are one JSON file per page
under .state, keyed by the page path; both refuse once anything else has
changed the page, so an Undo or an accept never overwrites a later update.
"""

import hashlib
from pathlib import Path

from .files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json
from .service import now

WAIT_SECONDS = 600


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _path(root, kind: str, record: str) -> Path:
    if ".." in Path(record).parts or not record.endswith(".md"):
        raise RemError(f"{record} is not a notebook page path")
    return state_path(Path(root), f"{kind}/{Path(record).with_suffix('.json')}")


def keep_previous(root, record: str, before: str, after: str) -> None:
    """After an investigation changed a page: what it was, and the page the Undo applies to."""
    if before == after:
        return
    write_json(_path(root, "previous", record), {"record": record, "text": before, "after_sha256": _sha(after),
                                                  "at": now().isoformat()})


def previous(root, record: str) -> dict | None:
    saved = read_json(_path(root, "previous", record), {})
    return saved or None


def can_undo(root, record: str) -> bool:
    saved, book = previous(root, record), Notebook(root)
    return bool(saved) and book.exists(record) and _sha(book.read(record)) == saved["after_sha256"]


def undo(root, record: str) -> dict:
    with maintenance_lock(Path(root), wait=WAIT_SECONDS):
        saved, book = previous(root, record), Notebook(root)
        if not saved:
            raise RemError(f"Nothing to undo for {record}: no investigation has changed it since this was added")
        if _sha(book.read(record)) != saved["after_sha256"]:
            raise RemError(f"{record} has changed since its last investigation; undoing would lose that change. "
                           "Nothing was undone")
        book.write(record, saved["text"])
        _path(root, "previous", record).unlink()
    _refresh(root)
    return {"record": record, "undone": saved["at"]}


def hold_rewrite(root, record: str, before: str) -> dict:
    """A rewrite run has written the page: keep what it wrote as the draft and put the page back."""
    with maintenance_lock(Path(root), wait=WAIT_SECONDS):
        book = Notebook(root)
        drafted = book.read(record)
        if drafted == before:
            return {"record": record, "changed": False}
        write_json(_path(root, "rewrites", record), {"record": record, "text": drafted, "base_sha256": _sha(before),
                                                      "drafted_at": now().isoformat(),
                                                      "chars": [len(before), len(drafted)]})
        book.write(record, before)
    _refresh(root)
    return {"record": record, "changed": True, "draft": str(_path(root, "rewrites", record)),
            "chars": [len(before), len(drafted)]}


def waiting_rewrite(root, record: str) -> dict | None:
    saved = read_json(_path(root, "rewrites", record), {})
    return saved or None


def accept_rewrite(root, record: str) -> dict:
    with maintenance_lock(Path(root), wait=WAIT_SECONDS):
        saved, book = waiting_rewrite(root, record), Notebook(root)
        if not saved:
            raise RemError(f"No rewrite draft waits for {record}; make one with co rem investigate {record} --rewrite")
        current = book.read(record)
        if _sha(current) != saved["base_sha256"]:
            raise RemError(f"{record} changed after the draft was made; accepting it would lose that change. "
                           f"Make a new one with co rem investigate {record} --rewrite")
        book.write(record, saved["text"])
        keep_previous(root, record, current, saved["text"])
        _path(root, "rewrites", record).unlink()
    _refresh(root)
    return {"record": record, "accepted": saved["drafted_at"]}


def discard_rewrite(root, record: str) -> dict:
    path = _path(root, "rewrites", record)
    if not path.is_file():
        raise RemError(f"No rewrite draft waits for {record}")
    path.unlink()
    return {"record": record, "discarded": True}


def _refresh(root) -> None:
    from .store import refresh_safely
    refresh_safely(Path(root))
