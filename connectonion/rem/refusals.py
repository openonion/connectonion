"""The refusal ledger: every refused page, with the material it was refused for (#2041).

One file, written by every path that can refuse a page: an investigation and
each of its rounds, a skill page, a project page, a one-page maintenance turn.
Only `investigate()` wrote it, so on the 2026-10-10 notebook it held one page
of the eight refused: job-followup and x-reply (init), startup, browser and
handoff (sync maintenance), and two refused rounds swallowed inside accepted
investigations (Corin Marsh, Briar). A refusal nobody records is material nobody
reads again.

A maintenance refusal also keeps the material itself: the sync's cursor moves
on, so the batch is not read twice, and the daily round retries the page from
what is held here.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import read_json, state_path, write_json

REFUSED = "refused-investigations.json"
# A refused page is retried at most this often: the same material refused
# again costs a turn, and new material reaches the page through its own path.
RETRY_HOURS = 20
# A page refused this many times on the same material waits for new material:
# a deterministic refusal (a page over the size limit) would otherwise cost a
# turn every day for ever.
MAX_RETRIES = 3


# A local path inside an error. What the night's line prints never carries one.
LOCAL_PATH = re.compile(r"""(?<![\w.<:/])/(?:[^\s/:;,)"']+/)+[^\s/:;,)"']*""")
DROPPED = (("Dropped source id the page had:", "source"), ("Dropped quote the page had:", "quote"))


def short_cause(why: str, refusal: str = "") -> str:
    """A parked reason for the night's line: how often it was refused, then the cause in a clause.

    2026-11-17: the line printed the stored reason, 300 characters of source ids cut
    mid-word. A rewrite that dropped what the page had is said with its counts, taken
    from `refusal` (the whole last refusal) when the caller has it, since `why` is cut;
    any other cause is its first clause. No ids and no local paths either way."""
    head, body = re.match(r"(?s)(?:(refused (?:\d+ times|twice for the same reason)): )?(.*)", why).groups()
    text = LOCAL_PATH.sub("<path>", refusal or body).removeprefix("Candidate rejected, kept at <path>: ")
    lost = [f"{count} {name}{'' if count == 1 else 's'}" for rule, name in DROPPED if (count := text.count(rule))]
    cause = (f"the rewrite dropped {' and '.join(lost)} the page had" if lost and text.startswith("Dropped ")
             else re.split(r":\s|;\s|\n", text, maxsplit=1)[0][:100])
    return f"{head}: {cause}" if head else cause


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
                     material: list[dict] | None = None, parked: bool = False,
                     candidate: str | None = None) -> None:
    """Add a refusal to the page's entry; what an earlier refusal held stays held.

    `parked`: the native round set the page aside (refused again and again, or
    its preparation hung). That note stays until the page is accepted.
    `candidate`: where the last page a parked task wrote is kept for the owner."""
    from .catchup import identity, number
    ledger = refused_pages(root)
    entry = ledger.get(record) or {}
    held = {item.get("source"): item for item in [*(entry.get("material") or []), *(material or [])]}
    new = set(sources) - set(entry.get("sources", []))
    revisions = {row.get("source"): row.get("feedback_revision") for row in entry.get("material", [])}
    revised = any(row.get("feedback_revision") and
                  revisions.get(row.get("source")) != row["feedback_revision"] for row in material or [])
    # Parked again in the same words from the same material: the next night would only
    # buy the same refusal. 2026-11-16 (#3083) one page was parked six times in a day.
    settled = parked and not new and not revised and _same_words(entry.get("parked"), why)
    ledger[record] = {"sources": sorted({*entry.get("sources", []), *sources}),
                      "at": datetime.now(timezone.utc).isoformat(), "why": why[:300], "stage": stage,
                      "retries": 0 if new or revised else MAX_RETRIES if settled else entry.get("retries", 0),
                      **identity(root),
                      **({"material": list(held.values())} if held else {}),
                      **({"parked": why[:300], "parked_at": datetime.now(timezone.utc).isoformat(),
                          "parked_night": number(root), **({"candidate": candidate} if candidate else {})} if parked
                         else {key: entry[key] for key in ("parked", "parked_at", "parked_night", "candidate")
                               if key in entry})}
    write_json(state_path(root, REFUSED), ledger)


def _same_words(before: str | None, why: str) -> bool:
    """Two park reasons for one problem differ in counts and citation numbers, not words."""
    import re
    plain = lambda text: re.sub(r"\d+", "#", text[:300])  # noqa: E731
    # A page whose preparation hung says so each time and is not a verdict on its material.
    return bool(before) and "refused" in why and plain(before) == plain(why)


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
    from .catchup import number
    night = number(root)
    entries = refused_pages(root).items()
    return dict(sorted(((record, entry) for record, entry in entries
                        if (max(entry.get("at", ""), entry.get("retried_at", "")) < cutoff if night is None
                            else night not in (entry.get('catchup_night'), entry.get('retried_night')))
                        and entry.get("retries", 0) < MAX_RETRIES),
                       key=lambda pair: pair[1].get("at", "")))


def mark_retried(root: Path, record: str) -> None:
    """Stamped before the retry: one that crashes is not tried again on every later run."""
    ledger = refused_pages(root)
    if record in ledger:
        from .catchup import number
        ledger[record]["retried_at"] = datetime.now(timezone.utc).isoformat()
        ledger[record]['retried_night'] = number(root)
        ledger[record]["retries"] = ledger[record].get("retries", 0) + 1
        write_json(state_path(root, REFUSED), ledger)


def parked_waiting(root: Path, *, now: datetime | None = None) -> dict:
    """Pages parked in the last RETRY_HOURS: kept out of the queue until they are due for retry."""
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(hours=RETRY_HOURS)).isoformat()
    from .catchup import number
    night = number(root)
    return {record: entry for record, entry in refused_pages(root).items()
            if (entry.get("parked_at", "") > cutoff if night is None else entry.get('parked_night') == night)}


def waiting_for_material(root: Path) -> dict:
    """Pages out of retries on the material they were refused for: {record: when they were last refused}.

    They are not due for retry, and nothing kept their own queue from listing them
    again the night after: a page stays unfinished while it is refused."""
    return {record: entry.get("at", "") for record, entry in refused_pages(root).items()
            if entry.get("retries", 0) >= MAX_RETRIES}
