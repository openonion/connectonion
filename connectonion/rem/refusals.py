"""The refusal ledger: every refused page, with the material it was refused for (#2041).

One file, written by every path that can refuse a page: an investigation and
each of its rounds, a skill page, a project page, a one-page maintenance turn.
Only `investigate()` wrote it, so on the 2026-10-10 notebook it held one page
of the eight refused: job-followup and x-reply (init), startup, browser and
handoff (sync maintenance), and two refused rounds swallowed inside accepted
investigations (Ody Zhou, Dora). A refusal nobody records is material nobody
reads again.

A maintenance refusal also keeps the material itself: the sync's cursor moves
on, so the batch is not read twice, and the daily round retries the page from
what is held here.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import read_json, state_path, write_json

REFUSED = "refused-investigations.json"
# A refused page is retried at most this often: the same material refused
# again costs a turn, and new material reaches the page through its own path.
RETRY_HOURS = 20


def refused_pages(root: Path) -> dict:
    return read_json(state_path(root, REFUSED), {})


def refused_for(root: Path, record: str) -> dict:
    return refused_pages(root).get(record) or {}


def material_sources(items: list[dict]) -> list[str]:
    """The ids of what a turn read about its subject: not the page, not our own reading guides."""
    found = []
    for item in items:
        if item.get("role") == "page":
            continue
        for source in [item.get("source"), *(item.get("sources") or [])]:
            if isinstance(source, str) and source and not source.startswith("investigation:"):
                found.append(source)
    return sorted(set(found))


def remember_refusal(root: Path, record: str, sources: list[str], why: str, *, stage: str,
                     material: list[dict] | None = None) -> None:
    """Add a refusal to the page's entry; what an earlier refusal held stays held."""
    ledger = refused_pages(root)
    entry = ledger.get(record) or {}
    held = {item.get("source"): item for item in [*(entry.get("material") or []), *(material or [])]}
    ledger[record] = {"sources": sorted({*entry.get("sources", []), *sources}),
                      "at": datetime.now(timezone.utc).isoformat(), "why": why[:300], "stage": stage,
                      **({"material": list(held.values())} if held else {})}
    write_json(state_path(root, REFUSED), ledger)


def forget_refusal(root: Path, record: str, sources: list[str] | None = None) -> None:
    """The page was accepted: drop its entry, or only the sources the accepted turn read.

    A refused round's material is not read by the rounds after it, so an
    accepted investigation clears the rest and keeps that round's entry."""
    ledger = refused_pages(root)
    entry = ledger.get(record)
    if entry is None:
        return
    left = [] if sources is None else sorted(set(entry.get("sources", [])) - set(sources))
    if left:
        held = [item for item in entry.get("material") or [] if item.get("source") in left]
        rest = {key: value for key, value in entry.items() if key != "material"}
        ledger[record] = {**rest, "sources": left, **({"material": held} if held else {})}
    else:
        ledger.pop(record)
    write_json(state_path(root, REFUSED), ledger)


def due_for_retry(root: Path, *, now: datetime | None = None) -> dict:
    """Ledger pages not tried in the last RETRY_HOURS, oldest refusal first."""
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(hours=RETRY_HOURS)).isoformat()
    entries = refused_pages(root).items()
    return dict(sorted(((record, entry) for record, entry in entries
                        if max(entry.get("at", ""), entry.get("retried_at", "")) < cutoff),
                       key=lambda pair: pair[1].get("at", "")))


def mark_retried(root: Path, record: str) -> None:
    """Stamped before the retry: one that crashes is not tried again on every later run."""
    ledger = refused_pages(root)
    if record in ledger:
        ledger[record]["retried_at"] = datetime.now(timezone.utc).isoformat()
        write_json(state_path(root, REFUSED), ledger)
